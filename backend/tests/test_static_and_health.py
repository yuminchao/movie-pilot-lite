from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_is_public_and_frontend_fallback_is_served(tmp_path: Path) -> None:
    frontend = tmp_path / "dist"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        "<!doctype html><title>movie-pilot-lite</title>",
        encoding="utf-8",
    )
    app = create_app(
        f"sqlite:///{tmp_path / 'test.db'}",
        frontend_dir=frontend,
    )

    with TestClient(app) as client:
        assert client.get("/mpl/api/health").json() == {"status": "ok"}
        assert "movie-pilot-lite" in client.get("/mpl/").text
        assert "movie-pilot-lite" in client.get("/mpl/settings").text


def test_unknown_api_path_does_not_return_frontend(tmp_path: Path) -> None:
    frontend = tmp_path / "dist"
    frontend.mkdir()
    (frontend / "index.html").write_text("frontend", encoding="utf-8")

    with TestClient(
        create_app(f"sqlite:///{tmp_path / 'test.db'}", frontend_dir=frontend)
    ) as client:
        assert client.get("/mpl/api/unknown").status_code == 404
