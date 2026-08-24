from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.config.crypto import SecretCipher
from app.config.repository import ConfigKey, ConfigRepository
from app.db.session import Database


@pytest.fixture
def repository(tmp_path: Path) -> ConfigRepository:
    database = Database(f"sqlite:///{tmp_path / 'test.db'}")
    database.create_schema()
    return ConfigRepository(
        session_factory=database.session_factory,
        cipher=SecretCipher.from_password("admin-password"),
    )


def test_repository_round_trips_structured_secret(repository: ConfigRepository) -> None:
    repository.set_secret(
        ConfigKey.MTEAM_CONNECTION,
        {"headers": {"x-api-key": "secret"}, "cookie": "tp=secret"},
    )

    assert repository.get_secret(ConfigKey.MTEAM_CONNECTION) == {
        "headers": {"x-api-key": "secret"},
        "cookie": "tp=secret",
    }


def test_masked_status_never_contains_plaintext(repository: ConfigRepository) -> None:
    repository.set_secret(
        ConfigKey.MTEAM_CONNECTION,
        {"headers": {"x-api-key": "secret"}, "cookie": "tp=secret"},
    )

    status = repository.get_masked_status(ConfigKey.MTEAM_CONNECTION)

    assert status["configured"] is True
    assert status["masked"] == "••••••••"
    assert "secret" not in str(status)


@pytest.mark.parametrize(
    "key",
    [ConfigKey.MTEAM_CONNECTION, ConfigKey.QBITTORRENT_CONNECTION],
)
def test_masked_status_updated_at_is_utc_instant(
    repository: ConfigRepository,
    key: ConfigKey,
) -> None:
    before = datetime.now(UTC)
    repository.set_secret(key, {"credential": "secret"})

    status = repository.get_masked_status(key)
    after = datetime.now(UTC)
    updated_at = datetime.fromisoformat(status["updated_at"])

    assert updated_at.utcoffset() == timedelta(0)
    assert before <= updated_at <= after


def test_repository_rejects_unknown_key(repository: ConfigRepository) -> None:
    with pytest.raises(ValueError):
        repository.set_secret("arbitrary.key", {"value": "secret"})  # type: ignore[arg-type]
