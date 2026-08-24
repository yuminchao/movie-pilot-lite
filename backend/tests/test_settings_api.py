from unittest.mock import Mock

import pytest

import app.services.settings as settings_module
from app.api import settings as settings_api
from app.config.repository import ConfigKey, ConfigRepository


MASKED_VALUE = "••••••••"


def _login(client) -> None:
    client.post("/api/auth/setup", json={"password": "correct horse battery"})
    response = client.post("/api/auth/login", json={"password": "correct horse battery"})
    assert response.status_code == 204


def test_settings_require_session(client) -> None:
    response = client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test",
            "headers": {"x-api-key": "secret"},
            "cookie": "tp=secret",
        },
    )

    assert response.status_code == 401


def test_mteam_settings_are_encrypted_and_masked(client) -> None:
    _login(client)

    saved = client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test",
            "headers": {"x-api-key": "secret"},
            "cookie": "tp=secret",
            "user_agent": "movie-pilot-lite",
            "timeout": 15,
        },
    )
    loaded = client.get("/api/settings/mteam")

    assert saved.status_code == 200
    assert loaded.status_code == 200
    assert loaded.json() == {
        "configured": True,
        "masked": MASKED_VALUE,
        "updated_at": loaded.json()["updated_at"],
        "base_url": "https://m-team.test",
        "headers": {"x-api-key": MASKED_VALUE},
        "cookie": MASKED_VALUE,
        "user_agent": "movie-pilot-lite",
        "timeout": 15,
    }
    assert "secret" not in str(saved.json())
    assert "secret" not in str(loaded.json())


def test_unconfigured_mteam_settings_return_safe_defaults(client) -> None:
    _login(client)

    response = client.get("/api/settings/mteam")

    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "masked": None,
        "updated_at": None,
        "base_url": "https://kp.m-team.cc",
        "headers": {},
        "cookie": None,
        "user_agent": "movie-pilot-lite/0.1",
        "timeout": 15,
    }


def test_masked_mteam_values_preserve_saved_secrets(client, monkeypatch) -> None:
    _login(client)
    client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test/",
            "headers": {"x-api-key": "api-secret", "x-extra": "remove-me"},
            "cookie": "tp=cookie-secret",
            "user_agent": "custom-agent",
            "timeout": 20,
        },
    )
    saved = client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test/",
            "headers": {"x-api-key": MASKED_VALUE},
            "cookie": MASKED_VALUE,
            "user_agent": "custom-agent",
            "timeout": 20,
        },
    )
    mteam_client = Mock()
    monkeypatch.setattr(settings_module, "MTeamClient", mteam_client)

    tested = client.post("/api/settings/mteam/test")

    assert saved.status_code == 200
    assert saved.json()["headers"] == {"x-api-key": MASKED_VALUE}
    assert tested.status_code == 200
    mteam_client.assert_called_once_with(
        base_url="https://m-team.test",
        headers={"x-api-key": "api-secret"},
        cookie="tp=cookie-secret",
        user_agent="custom-agent",
        timeout=20.0,
    )
    mteam_client.return_value.test_connection.assert_called_once_with()


def test_first_mteam_save_rejects_masked_secrets(client) -> None:
    _login(client)

    header_response = client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test",
            "headers": {"x-api-key": MASKED_VALUE},
            "cookie": None,
            "user_agent": "agent",
            "timeout": 15,
        },
    )
    cookie_response = client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test",
            "headers": {},
            "cookie": MASKED_VALUE,
            "user_agent": "agent",
            "timeout": 15,
        },
    )

    assert header_response.status_code == 422
    assert cookie_response.status_code == 422


def test_mteam_validation_error_does_not_echo_oversized_cookie(client) -> None:
    _login(client)
    sensitive_cookie = "unique-cookie-secret-" + "x" * 16_384

    response = client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test",
            "headers": {},
            "cookie": sensitive_cookie,
            "user_agent": "agent",
            "timeout": 15,
        },
    )

    assert response.status_code == 422
    assert "unique-cookie-secret" not in response.text


def test_mteam_validation_error_does_not_echo_invalid_header_value(client) -> None:
    _login(client)
    sensitive_header = 987_654_321

    response = client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test",
            "headers": {"x-api-key": sensitive_header},
            "cookie": None,
            "user_agent": "agent",
            "timeout": 15,
        },
    )

    assert response.status_code == 422
    assert str(sensitive_header) not in response.text


def test_empty_cookie_and_missing_header_delete_saved_values(client, monkeypatch) -> None:
    _login(client)
    client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test",
            "headers": {"x-api-key": "secret", "x-extra": "extra"},
            "cookie": "tp=secret",
            "user_agent": "agent",
            "timeout": 15,
        },
    )
    saved = client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test",
            "headers": {"x-api-key": MASKED_VALUE},
            "cookie": "",
            "user_agent": "agent",
            "timeout": 15,
        },
    )
    mteam_client = Mock()
    monkeypatch.setattr(settings_module, "MTeamClient", mteam_client)

    tested = client.post("/api/settings/mteam/test")

    assert saved.status_code == 200
    assert saved.json()["headers"] == {"x-api-key": MASKED_VALUE}
    assert saved.json()["cookie"] is None
    assert tested.status_code == 200
    mteam_client.assert_called_once_with(
        base_url="https://m-team.test",
        headers={"x-api-key": "secret"},
        cookie="",
        user_agent="agent",
        timeout=15.0,
    )


def test_qbittorrent_settings_are_masked(client) -> None:
    _login(client)

    response = client.put(
        "/api/settings/qbittorrent",
        json={
            "base_url": "http://qb:8080",
            "username": "admin",
            "password": "secret-password",
            "api_key": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert "secret-password" not in str(response.json())


def test_qbittorrent_settings_require_credentials(client) -> None:
    _login(client)

    response = client.put(
        "/api/settings/qbittorrent",
        json={"base_url": "http://qb:8080"},
    )

    assert response.status_code == 422


def test_connection_test_requires_saved_configuration(client) -> None:
    _login(client)

    response = client.post("/api/settings/mteam/test")

    assert response.status_code == 422
    assert response.json() == {"detail": "连接尚未配置"}


def test_download_defaults_can_be_configured(client) -> None:
    _login(client)

    expected = {
        "category": "media",
        "save_paths": {
            "movie": "/downloads/movies",
            "tv": "/downloads/tv",
            "music": "D:\\downloads\\music",
            "other": "/downloads/other",
        },
        "start": False,
    }
    saved = client.put(
        "/api/settings/downloads",
        json=expected,
    )
    loaded = client.get("/api/settings/downloads")

    assert saved.status_code == 200
    assert saved.json() == expected
    assert loaded.json() == expected


@pytest.mark.parametrize("path_key", ["movie", "tv", "music", "other"])
def test_download_defaults_reject_relative_path(client, path_key: str) -> None:
    _login(client)
    save_paths = {
        "movie": "/downloads/movies",
        "tv": "/downloads/tv",
        "music": "/downloads/music",
        "other": "/downloads/other",
    }
    save_paths[path_key] = "relative/downloads"

    response = client.put(
        "/api/settings/downloads",
        json={
            "category": "media",
            "save_path": "/downloads",
            "save_paths": save_paths,
            "start": True,
        },
    )

    assert response.status_code == 422


def test_legacy_download_defaults_fill_all_save_paths(client) -> None:
    _login(client)
    repository = ConfigRepository(
        client.app.state.database.session_factory,
        client.app.state.secret_vault.cipher,
    )
    repository.set_secret(
        ConfigKey.DOWNLOAD_DEFAULTS,
        {"category": "legacy", "save_path": "/legacy/downloads", "start": False},
    )

    response = client.get("/api/settings/downloads")

    assert response.status_code == 200
    assert response.json() == {
        "category": "legacy",
        "save_paths": {
            "movie": "/legacy/downloads",
            "tv": "/legacy/downloads",
            "music": "/legacy/downloads",
            "other": "/legacy/downloads",
        },
        "start": False,
    }


def test_unconfigured_download_defaults_return_safe_defaults(client) -> None:
    _login(client)

    response = client.get("/api/settings/downloads")

    assert response.status_code == 200
    assert response.json() == {
        "category": "downloads",
        "save_paths": {
            "movie": "/downloads",
            "tv": "/downloads",
            "music": "/downloads",
            "other": "/downloads",
        },
        "start": True,
    }


def test_checkin_settings_require_session(client) -> None:
    response = client.get("/api/settings/mteam/checkin")

    assert response.status_code == 401


def test_checkin_dependency_returns_application_singleton(client) -> None:
    _login(client)
    provider = client.app.dependency_overrides[settings_api.get_checkin_service]

    assert provider() is provider()


def test_unconfigured_checkin_settings_return_defaults(client) -> None:
    _login(client)

    response = client.get("/api/settings/mteam/checkin")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "execution_time": "09:00",
        "last_attempt_at": None,
        "last_success_date": None,
        "success": None,
        "message": None,
    }


def test_checkin_settings_can_be_saved_and_loaded(client) -> None:
    _login(client)

    saved = client.put(
        "/api/settings/mteam/checkin",
        json={"enabled": True, "execution_time": "07:05"},
    )
    loaded = client.get("/api/settings/mteam/checkin")

    expected = {
        "enabled": True,
        "execution_time": "07:05",
        "last_attempt_at": None,
        "last_success_date": None,
        "success": None,
        "message": None,
    }
    assert saved.status_code == 200
    assert saved.json() == expected
    assert loaded.json() == expected


def test_checkin_settings_reject_invalid_time_without_echoing_value(client) -> None:
    _login(client)
    invalid_time = "sensitive-invalid-time"

    response = client.put(
        "/api/settings/mteam/checkin",
        json={"enabled": True, "execution_time": invalid_time},
    )

    assert response.status_code == 422
    assert invalid_time not in response.text


def test_updating_checkin_settings_preserves_runtime_status(client) -> None:
    _login(client)
    repository = ConfigRepository(
        client.app.state.database.session_factory,
        client.app.state.secret_vault.cipher,
    )
    repository.set_secret(
        ConfigKey.MTEAM_CHECKIN,
        {
            "enabled": True,
            "execution_time": "09:00",
            "last_attempt_at": "2026-08-24T09:00:00+08:00",
            "last_success_date": "2026-08-24",
            "attempt_date": "2026-08-24",
            "attempts_on_date": 1,
            "success": True,
            "message": "签到成功",
        },
    )

    response = client.put(
        "/api/settings/mteam/checkin",
        json={"enabled": False, "execution_time": "10:30"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "execution_time": "10:30",
        "last_attempt_at": "2026-08-24T09:00:00+08:00",
        "last_success_date": "2026-08-24",
        "success": True,
        "message": "签到成功",
    }
    persisted = repository.get_secret(ConfigKey.MTEAM_CHECKIN)
    assert persisted is not None
    assert persisted["attempt_date"] == "2026-08-24"
    assert persisted["attempts_on_date"] == 1


def test_successful_mteam_save_wakes_checkin_scheduler(client) -> None:
    _login(client)
    scheduler = Mock()
    client.app.state.checkin_scheduler = scheduler

    response = client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test",
            "headers": {"x-api-key": "secret"},
            "cookie": "tp=secret",
        },
    )

    assert response.status_code == 200
    scheduler.wake.assert_called_once_with()


def test_failed_mteam_save_does_not_wake_checkin_scheduler(client) -> None:
    _login(client)
    scheduler = Mock()
    client.app.state.checkin_scheduler = scheduler

    response = client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test",
            "headers": {"x-api-key": MASKED_VALUE},
        },
    )

    assert response.status_code == 422
    scheduler.wake.assert_not_called()


def test_successful_checkin_save_wakes_checkin_scheduler(client) -> None:
    _login(client)
    scheduler = Mock()
    client.app.state.checkin_scheduler = scheduler

    response = client.put(
        "/api/settings/mteam/checkin",
        json={"enabled": True, "execution_time": "07:05"},
    )

    assert response.status_code == 200
    scheduler.wake.assert_called_once_with()


def test_failed_checkin_save_does_not_wake_checkin_scheduler(client) -> None:
    _login(client)
    scheduler = Mock()
    client.app.state.checkin_scheduler = scheduler

    response = client.put(
        "/api/settings/mteam/checkin",
        json={"enabled": True, "execution_time": "invalid"},
    )

    assert response.status_code == 422
    scheduler.wake.assert_not_called()
