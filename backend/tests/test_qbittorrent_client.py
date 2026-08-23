from app.integrations.qbittorrent import QbittorrentClient, QbittorrentConfig


class FakeQbClient:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.login_calls = 0
        self.add_calls: list[dict] = []

    def auth_log_in(self) -> None:
        self.login_calls += 1

    def torrents_add(self, **kwargs):
        self.add_calls.append(kwargs)
        return {"added_torrent_ids": ["HASH-7"]}

    def torrents_info(self):
        return [
            {
                "hash": "HASH-7",
                "name": "Movie",
                "state": "downloading",
                "progress": 0.5,
                "dlspeed": 1024,
                "eta": 60,
                "save_path": "/downloads/movies",
            }
        ]


def test_password_authentication_logs_in() -> None:
    fake = FakeQbClient()
    client = QbittorrentClient(
        QbittorrentConfig(base_url="http://qb:8080", username="admin", password="secret"),
        client_factory=lambda **_: fake,
    )

    client.test_connection()

    assert fake.login_calls == 1


def test_add_torrent_forwards_download_options() -> None:
    fake = FakeQbClient()
    client = QbittorrentClient(
        QbittorrentConfig(base_url="http://qb:8080", username="admin", password="secret"),
        client_factory=lambda **_: fake,
    )

    torrent_hash = client.add_torrent(
        "https://download.test/file.torrent",
        category="movies",
        save_path="/downloads/movies",
        paused=True,
    )

    assert torrent_hash == "HASH-7"
    assert fake.add_calls == [
        {
            "urls": "https://download.test/file.torrent",
            "category": "movies",
            "save_path": "/downloads/movies",
            "is_paused": True,
        }
    ]


def test_list_torrents_normalizes_status() -> None:
    fake = FakeQbClient()
    client = QbittorrentClient(
        QbittorrentConfig(base_url="http://qb:8080", username="admin", password="secret"),
        client_factory=lambda **_: fake,
    )

    task = client.list_torrents()[0]

    assert task.status == "downloading"
    assert task.progress == 0.5
    assert task.download_speed == 1024
