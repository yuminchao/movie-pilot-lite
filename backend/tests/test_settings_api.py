from unittest.mock import Mock

import app.services.settings as settings_module


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

    saved = client.put(
        "/api/settings/downloads",
        json={
            "category": "media",
            "save_path": "/downloads/media",
            "start": False,
        },
    )
    loaded = client.get("/api/settings/downloads")

    assert saved.status_code == 200
    assert loaded.json() == {
        "category": "media",
        "save_path": "/downloads/media",
        "start": False,
    }
