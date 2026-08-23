from app.auth.session import SESSION_COOKIE


def test_setup_then_login(client) -> None:
    setup = client.post(
        "/api/auth/setup",
        json={"password": "correct horse battery"},
    )
    assert setup.status_code == 201

    login = client.post(
        "/api/auth/login",
        json={"password": "correct horse battery"},
    )
    assert login.status_code == 204
    assert SESSION_COOKIE in login.cookies


def test_setup_is_only_available_without_admin(client) -> None:
    payload = {"password": "correct horse battery"}

    assert client.post("/api/auth/setup", json=payload).status_code == 201
    assert client.post("/api/auth/setup", json=payload).status_code == 409


def test_protected_endpoint_requires_session(client) -> None:
    response = client.get("/api/settings/mteam")

    assert response.status_code == 401


def test_wrong_password_does_not_create_session(client) -> None:
    client.post("/api/auth/setup", json={"password": "correct horse battery"})

    response = client.post("/api/auth/login", json={"password": "wrong"})

    assert response.status_code == 401
    assert SESSION_COOKIE not in response.cookies
