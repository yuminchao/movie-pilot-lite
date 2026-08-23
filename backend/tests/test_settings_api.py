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
    assert loaded.json()["configured"] is True
    assert loaded.json()["masked"] == "••••••••"
    assert "secret" not in str(saved.json())
    assert "secret" not in str(loaded.json())


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
