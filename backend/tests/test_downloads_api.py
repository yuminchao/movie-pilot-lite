from pathlib import Path

import pytest

from app.api.downloads import get_download_service
from app.db.session import Database
from app.services.downloads import DownloadService
from app.services.tokens import SourceTokenCodec


class MTeamStub:
    def __init__(self) -> None:
        self.calls = 0

    def get_download_url(self, source_id: str) -> str:
        self.calls += 1
        return f"https://download.test/{source_id}.torrent"


class QbStub:
    def __init__(self) -> None:
        self.add_calls = 0

    def add_torrent(self, url: str, category: str, save_path: str, paused: bool) -> str:
        self.add_calls += 1
        return "HASH-7"

    def list_torrents(self) -> list:
        return []


@pytest.fixture
def download_service(tmp_path: Path) -> tuple[DownloadService, SourceTokenCodec, QbStub]:
    database = Database(f"sqlite:///{tmp_path / 'downloads.db'}")
    database.create_schema()
    codec = SourceTokenCodec(b"download-test-secret")
    qb = QbStub()
    service = DownloadService(database, codec, MTeamStub(), qb)
    return service, codec, qb


def test_add_download_is_idempotent(download_service) -> None:
    service, codec, qb = download_service
    token = codec.encode("7", "Movie")

    first, first_created = service.add(token, "movies", "/downloads/movies", True)
    second, second_created = service.add(token, "movies", "/downloads/movies", True)

    assert first_created is True
    assert second_created is False
    assert first["id"] == second["id"]
    assert qb.add_calls == 1


def test_add_download_rejects_relative_save_path(download_service) -> None:
    service, codec, _ = download_service

    with pytest.raises(ValueError, match="绝对路径"):
        service.add(codec.encode("7", "Movie"), "movies", "downloads/movies", True)


class DownloadServiceStub:
    def add(self, source_token: str, category: str, save_path: str, start: bool):
        assert source_token == "source-7"
        return {"id": 1, "title": "Movie", "status": "queued"}, True

    def list(self):
        return {"items": [], "stale": False, "refreshed_at": "2026-08-23T10:00:00Z"}


def _login(client) -> None:
    client.post("/api/auth/setup", json={"password": "correct horse battery"})
    client.post("/api/auth/login", json={"password": "correct horse battery"})


def test_download_api_creates_task(client) -> None:
    _login(client)
    client.app.dependency_overrides[get_download_service] = lambda: DownloadServiceStub()

    response = client.post(
        "/api/downloads",
        json={
            "source_token": "source-7",
            "category": "movies",
            "save_path": "/downloads/movies",
            "start": True,
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "queued"


def test_download_api_does_not_expose_delete(client) -> None:
    _login(client)

    response = client.delete("/api/downloads/1")

    assert response.status_code == 405
