from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from pathlib import Path
from threading import Event, Lock
from zoneinfo import ZoneInfo

import pytest

from app.config.repository import ConfigKey, ConfigRepository
from app.config.vault import SecretVault
from app.db.session import Database
from app.integrations.mteam import IntegrationError
from app.services.checkin import CheckinService


TZ = ZoneInfo("Asia/Shanghai")


class FakeMTeamClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def check_in(self) -> None:
        self.calls += 1
        if self.error is not None:
            raise self.error


@pytest.fixture
def repository(tmp_path: Path) -> ConfigRepository:
    database = Database(f"sqlite:///{tmp_path / 'checkin.db'}")
    database.create_schema()
    vault = SecretVault()
    vault.unlock("admin-password")
    return ConfigRepository(database.session_factory, vault.cipher)


def _configured_service(
    repository: ConfigRepository,
    client: FakeMTeamClient,
    execution_time: time = time(9, 0),
) -> CheckinService:
    repository.set_secret(
        ConfigKey.MTEAM_CONNECTION,
        {"base_url": "https://m-team.test", "headers": {"x-api-key": "secret"}},
    )
    service = CheckinService(repository, lambda _: client, TZ)
    service.save_settings(True, execution_time)
    return service


def test_defaults_and_save_preserve_existing_runtime_state(
    repository: ConfigRepository,
) -> None:
    service = CheckinService(repository, lambda _: FakeMTeamClient(), TZ)

    assert service.read_settings() == {
        "enabled": False,
        "execution_time": "09:00",
        "last_attempt_at": None,
        "last_success_date": None,
        "success": None,
        "message": None,
    }
    repository.set_secret(
        ConfigKey.MTEAM_CHECKIN,
        {
            "enabled": True,
            "execution_time": "08:15",
            "last_attempt_at": "2026-08-24T08:15:00+08:00",
            "last_success_date": "2026-08-24",
            "attempt_date": "2026-08-24",
            "attempts_on_date": 1,
            "success": True,
            "message": "签到成功",
        },
    )

    saved = service.save_settings(False, time(10, 30))

    assert saved["enabled"] is False
    assert saved["execution_time"] == "10:30"
    assert saved["last_attempt_at"] == "2026-08-24T08:15:00+08:00"
    assert saved["last_success_date"] == "2026-08-24"
    persisted = repository.get_secret(ConfigKey.MTEAM_CHECKIN)
    assert persisted is not None
    assert persisted["attempt_date"] == "2026-08-24"
    assert persisted["attempts_on_date"] == 1


@pytest.mark.parametrize(
    ("enabled", "now"),
    [
        (False, datetime(2026, 8, 24, 10, 0, tzinfo=TZ)),
        (True, datetime(2026, 8, 24, 8, 59, tzinfo=TZ)),
    ],
)
def test_run_due_skips_disabled_or_early_execution(
    repository: ConfigRepository,
    enabled: bool,
    now: datetime,
) -> None:
    client = FakeMTeamClient()
    service = _configured_service(repository, client)
    service.save_settings(enabled, time(9, 0))

    assert service.run_due(now) is False
    assert client.calls == 0
    assert service.read_settings()["last_attempt_at"] is None


def test_success_runs_once_per_local_date(repository: ConfigRepository) -> None:
    client = FakeMTeamClient()
    service = _configured_service(repository, client)
    now = datetime(2026, 8, 24, 9, 0, tzinfo=TZ)

    assert service.run_due(now) is True
    assert service.run_due(now + timedelta(hours=2)) is False

    assert client.calls == 1
    assert service.read_settings() == {
        "enabled": True,
        "execution_time": "09:00",
        "last_attempt_at": "2026-08-24T09:00:00+08:00",
        "last_success_date": "2026-08-24",
        "success": True,
        "message": "签到成功",
    }


def test_failure_retries_after_30_minutes_and_stops_after_two_attempts(
    repository: ConfigRepository,
) -> None:
    client = FakeMTeamClient(IntegrationError("upstream secret detail"))
    service = _configured_service(repository, client)
    first = datetime(2026, 8, 24, 9, 0, tzinfo=TZ)

    assert service.run_due(first) is True
    assert service.run_due(first + timedelta(minutes=29, seconds=59)) is False
    assert service.run_due(first + timedelta(minutes=30)) is True
    assert service.run_due(first + timedelta(hours=2)) is False

    assert client.calls == 2
    status = service.read_settings()
    assert status["last_attempt_at"] == "2026-08-24T09:30:00+08:00"
    assert status["success"] is False
    assert status["message"] == "签到失败"
    assert "secret" not in str(status)


def test_new_local_date_resets_attempt_count(repository: ConfigRepository) -> None:
    client = FakeMTeamClient(IntegrationError("failure"))
    service = _configured_service(repository, client)
    first = datetime(2026, 8, 24, 9, 0, tzinfo=TZ)
    service.run_due(first)
    service.run_due(first + timedelta(minutes=30))

    client.error = None
    assert service.run_due(datetime(2026, 8, 25, 9, 0, tzinfo=TZ)) is True

    assert client.calls == 3
    assert service.read_settings()["last_success_date"] == "2026-08-25"


def test_missing_mteam_configuration_records_sanitized_failure(
    repository: ConfigRepository,
) -> None:
    factory_calls = 0

    def factory(_: dict) -> FakeMTeamClient:
        nonlocal factory_calls
        factory_calls += 1
        return FakeMTeamClient()

    service = CheckinService(repository, factory, TZ)
    service.save_settings(True, time(9, 0))

    assert service.run_due(datetime(2026, 8, 24, 9, 0, tzinfo=TZ)) is True

    assert factory_calls == 0
    status = service.read_settings()
    assert status["success"] is False
    assert status["message"] == "站点尚未配置"


def test_client_factory_failure_is_sanitized(repository: ConfigRepository) -> None:
    repository.set_secret(ConfigKey.MTEAM_CONNECTION, {"invalid": "sensitive"})

    def factory(_: dict) -> FakeMTeamClient:
        raise ValueError("sensitive configuration detail")

    service = CheckinService(repository, factory, TZ)
    service.save_settings(True, time(9, 0))

    service.run_due(datetime(2026, 8, 24, 9, 0, tzinfo=TZ))

    status = service.read_settings()
    assert status["success"] is False
    assert status["message"] == "签到失败"
    assert "sensitive" not in str(status)


@pytest.mark.parametrize("failure_source", ["factory", "client"])
def test_unexpected_third_party_exception_is_sanitized_and_retried(
    repository: ConfigRepository,
    failure_source: str,
) -> None:
    repository.set_secret(
        ConfigKey.MTEAM_CONNECTION,
        {"base_url": "https://m-team.test", "headers": {"x-api-key": "secret"}},
    )
    client = FakeMTeamClient(RuntimeError("secret-runtime-detail"))

    def factory(_: dict) -> FakeMTeamClient:
        if failure_source == "factory":
            raise RuntimeError("secret-runtime-detail")
        return client

    service = CheckinService(repository, factory, TZ)
    service.save_settings(True, time(9, 0))
    first = datetime(2026, 8, 24, 9, 0, tzinfo=TZ)

    assert service.run_due(first) is True
    assert service.run_due(first + timedelta(minutes=29)) is False
    assert service.run_due(first + timedelta(minutes=30)) is True

    status = service.read_settings()
    persisted = repository.get_secret(ConfigKey.MTEAM_CHECKIN)
    assert persisted is not None
    assert status["success"] is False
    assert status["message"] == "签到失败"
    assert persisted["attempts_on_date"] == 2
    assert "secret-runtime-detail" not in str(status)
    assert "secret-runtime-detail" not in str(persisted)


def test_seconds_until_next_covers_execution_retry_and_next_day(
    repository: ConfigRepository,
) -> None:
    client = FakeMTeamClient(IntegrationError("failure"))
    service = _configured_service(repository, client)

    assert service.seconds_until_next(datetime(2026, 8, 24, 8, 45, tzinfo=TZ)) == 900

    first = datetime(2026, 8, 24, 9, 0, tzinfo=TZ)
    service.run_due(first)
    assert service.seconds_until_next(first + timedelta(minutes=10)) == 1200

    service.run_due(first + timedelta(minutes=30))
    assert service.seconds_until_next(first + timedelta(hours=1)) == 82_800


def test_seconds_until_next_is_positive_when_due_and_finite_when_disabled(
    repository: ConfigRepository,
) -> None:
    client = FakeMTeamClient()
    service = _configured_service(repository, client)
    due = datetime(2026, 8, 24, 9, 0, tzinfo=TZ)

    assert service.seconds_until_next(due) == 1
    service.save_settings(False, time(9, 0))
    assert service.seconds_until_next(due) == 86_400


def test_retry_crossing_midnight_waits_for_next_day_execution(
    repository: ConfigRepository,
) -> None:
    client = FakeMTeamClient(IntegrationError("failure"))
    service = _configured_service(repository, client, time(23, 30))
    first = datetime(2026, 8, 24, 23, 40, tzinfo=TZ)
    service.run_due(first)

    assert service.seconds_until_next(first + timedelta(minutes=10)) == 85_200


def test_concurrent_runs_consume_only_one_attempt(repository: ConfigRepository) -> None:
    class BlockingClient(FakeMTeamClient):
        def __init__(self) -> None:
            self.calls = 0
            self.started = Event()
            self.second_call = Event()
            self.release = Event()
            self.lock = Lock()

        def check_in(self) -> None:
            with self.lock:
                self.calls += 1
                call_number = self.calls
            if call_number == 1:
                self.started.set()
                assert self.release.wait(timeout=2)
            else:
                self.second_call.set()

    client = BlockingClient()
    first_service = _configured_service(repository, client)
    second_service = CheckinService(repository, lambda _: client, TZ)
    now = datetime(2026, 8, 24, 9, 0, tzinfo=TZ)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(first_service.run_due, now)
        assert client.started.wait(timeout=2)
        second = executor.submit(second_service.run_due, now)
        try:
            assert not client.second_call.wait(timeout=0.2)
        finally:
            client.release.set()

        assert first.result(timeout=2) is True
        assert second.result(timeout=2) is False
    assert client.calls == 1


def test_seconds_until_next_uses_elapsed_time_across_dst(
    repository: ConfigRepository,
) -> None:
    timezone = ZoneInfo("America/New_York")
    service = CheckinService(repository, lambda _: FakeMTeamClient(), timezone)
    service.save_settings(True, time(3, 30))
    before_spring_jump = datetime(2026, 3, 8, 1, 30, tzinfo=timezone)

    assert service.seconds_until_next(before_spring_jump) == 3_600


def test_run_due_compares_ambiguous_execution_time_as_utc_instant(
    repository: ConfigRepository,
) -> None:
    timezone = ZoneInfo("America/New_York")
    client = FakeMTeamClient()
    repository.set_secret(
        ConfigKey.MTEAM_CONNECTION,
        {"base_url": "https://m-team.test", "headers": {"x-api-key": "secret"}},
    )
    service = CheckinService(repository, lambda _: client, timezone)
    service.save_settings(True, time(1, 30))
    after_first_occurrence = datetime(2026, 11, 1, 1, 15, fold=1, tzinfo=timezone)

    assert service.run_due(after_first_occurrence) is True
    assert client.calls == 1


def test_retry_delay_uses_real_elapsed_time_across_dst_fallback(
    repository: ConfigRepository,
) -> None:
    timezone = ZoneInfo("America/New_York")
    client = FakeMTeamClient(IntegrationError("failure"))
    repository.set_secret(
        ConfigKey.MTEAM_CONNECTION,
        {"base_url": "https://m-team.test", "headers": {"x-api-key": "secret"}},
    )
    service = CheckinService(repository, lambda _: client, timezone)
    service.save_settings(True, time(1, 0))
    first = datetime(2026, 11, 1, 1, 50, fold=0, tzinfo=timezone)
    before_retry = datetime(2026, 11, 1, 1, 19, fold=1, tzinfo=timezone)
    retry_at = datetime(2026, 11, 1, 1, 20, fold=1, tzinfo=timezone)

    assert service.run_due(first) is True
    assert service.run_due(before_retry) is False
    assert service.seconds_until_next(before_retry) == 60
    assert service.run_due(retry_at) is True
    assert client.calls == 2
