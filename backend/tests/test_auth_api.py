import threading
from unittest.mock import Mock

from app.auth.session import SESSION_COOKIE
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import create_app


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


def test_auth_status_recognizes_existing_session(client) -> None:
    client.post("/api/auth/setup", json={"password": "correct horse battery"})
    client.post("/api/auth/login", json={"password": "correct horse battery"})

    response = client.get("/api/auth/status")

    assert response.status_code == 200
    assert response.json() == {"setup_required": False, "authenticated": True}


def test_restart_requires_login_to_unlock_persisted_secrets(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'restart.db'}"
    with TestClient(create_app(database_url)) as first_client:
        first_client.post("/api/auth/setup", json={"password": "correct horse battery"})
        first_client.post("/api/auth/login", json={"password": "correct horse battery"})
        session_cookie = first_client.cookies[SESSION_COOKIE]

    with TestClient(create_app(database_url)) as restarted_client:
        restarted_client.cookies.set(SESSION_COOKIE, session_cookie)
        response = restarted_client.get("/api/auth/status")

    assert response.json() == {"setup_required": False, "authenticated": False}


def test_new_login_invalidates_previous_session(client) -> None:
    client.post("/api/auth/setup", json={"password": "correct horse battery"})
    client.post("/api/auth/login", json={"password": "correct horse battery"})
    previous_cookie = client.cookies[SESSION_COOKIE]

    client.post("/api/auth/login", json={"password": "correct horse battery"})
    client.cookies.set(SESSION_COOKIE, previous_cookie)

    assert client.get("/api/auth/status").json()["authenticated"] is False


def test_repeated_login_failures_are_rate_limited(client) -> None:
    client.post("/api/auth/setup", json={"password": "correct horse battery"})
    for _ in range(10):
        assert client.post("/api/auth/login", json={"password": "wrong-password"}).status_code == 401

    response = client.post("/api/auth/login", json={"password": "wrong-password"})

    assert response.status_code == 429
    assert response.json() == {"detail": "登录尝试过于频繁，请稍后重试"}


def test_application_lifespan_starts_and_stops_checkin_scheduler(tmp_path) -> None:
    application = create_app(f"sqlite:///{tmp_path / 'lifespan.db'}")
    scheduler = application.state.checkin_scheduler

    assert scheduler.is_running is False
    with TestClient(application):
        assert scheduler.is_running is True
    assert scheduler.is_running is False


def test_successful_login_wakes_locked_checkin_scheduler(tmp_path, monkeypatch) -> None:
    run_called = threading.Event()
    checkin_service = Mock()
    checkin_service.run_due.side_effect = lambda _: run_called.set()
    checkin_service.seconds_until_next.return_value = 3600
    constructor = Mock(return_value=checkin_service)
    monkeypatch.setattr(main_module, "CheckinService", constructor)
    application = create_app(f"sqlite:///{tmp_path / 'unlock.db'}")

    with TestClient(application) as test_client:
        test_client.post(
            "/api/auth/setup",
            json={"password": "correct horse battery"},
        )
        response = test_client.post(
            "/api/auth/login",
            json={"password": "correct horse battery"},
        )
        assert response.status_code == 204
        assert run_called.wait(timeout=1)

    constructor.assert_called_once()
