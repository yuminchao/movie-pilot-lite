from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import qbittorrentapi


class QbittorrentError(RuntimeError):
    """qBittorrent 认证、连接或操作失败。"""


@dataclass(frozen=True, slots=True)
class QbittorrentConfig:
    """qBittorrent Web API 连接配置。"""

    base_url: str
    username: str | None = None
    password: str | None = None
    api_key: str | None = None


@dataclass(frozen=True, slots=True)
class TorrentTask:
    """规范化后的 qBittorrent 任务状态。"""

    torrent_hash: str
    name: str
    status: str
    progress: float
    download_speed: int
    eta: int
    save_path: str


class QbittorrentClient:
    """qBittorrent Web API 的最小安全适配器。"""

    def __init__(
        self,
        config: QbittorrentConfig,
        client_factory: Callable[..., Any] = qbittorrentapi.Client,
    ) -> None:
        self._config = config
        self._client_factory = client_factory
        self._client: Any | None = None

    def test_connection(self) -> None:
        """连接并验证 qBittorrent 凭据。"""
        self._connect()

    def add_torrent(
        self,
        url: str,
        category: str | None,
        save_path: str,
        paused: bool,
    ) -> str | None:
        """添加 URL 种子并尽量返回新任务 hash。"""
        client = self._connect()
        try:
            response = client.torrents_add(
                urls=url,
                category=category,
                save_path=save_path,
                is_paused=paused,
            )
            if isinstance(response, dict):
                identifiers = response.get("added_torrent_ids") or []
                return str(identifiers[0]) if identifiers else None
            if response and "Ok" in str(response):
                return None
            raise QbittorrentError("qBittorrent 未确认任务添加成功")
        except QbittorrentError:
            raise
        except Exception as error:
            raise QbittorrentError("qBittorrent 添加任务失败") from error

    def list_torrents(self) -> list[TorrentTask]:
        """读取并规范化全部 qBittorrent 任务。"""
        client = self._connect()
        try:
            return [self._normalize_task(item) for item in client.torrents_info()]
        except Exception as error:
            raise QbittorrentError("qBittorrent 任务查询失败") from error

    def _connect(self) -> Any:
        """惰性创建并验证客户端连接。"""
        if self._client is not None:
            return self._client
        headers = (
            {"Authorization": f"Bearer {self._config.api_key}"}
            if self._config.api_key
            else None
        )
        try:
            client = self._client_factory(
                host=self._config.base_url,
                username=self._config.username,
                password=self._config.password,
                EXTRA_HEADERS=headers,
                VERIFY_WEBUI_CERTIFICATE=False,
                REQUESTS_ARGS={"timeout": (15, 60)},
            )
            if self._config.api_key:
                client.app_version()
            else:
                client.auth_log_in()
            self._client = client
            return client
        except Exception as error:
            raise QbittorrentError("qBittorrent 连接失败") from error

    @classmethod
    def _normalize_task(cls, item: Any) -> TorrentTask:
        progress = float(cls._value(item, "progress") or 0)
        return TorrentTask(
            torrent_hash=str(cls._value(item, "hash") or ""),
            name=str(cls._value(item, "name") or ""),
            status=cls._normalize_status(str(cls._value(item, "state") or ""), progress),
            progress=progress,
            download_speed=int(cls._value(item, "dlspeed") or 0),
            eta=int(cls._value(item, "eta") or 0),
            save_path=str(cls._value(item, "save_path") or ""),
        )

    @staticmethod
    def _value(item: Any, key: str) -> Any:
        return item.get(key) if isinstance(item, dict) else getattr(item, key, None)

    @staticmethod
    def _normalize_status(state: str, progress: float) -> str:
        lowered = state.lower()
        if "error" in lowered or "missing" in lowered:
            return "error"
        if lowered.startswith(("paused", "stopped")):
            return "paused"
        if progress >= 1 or lowered in {"uploading", "stalledup", "queuedup", "forcedup"}:
            return "completed"
        if lowered in {
            "downloading",
            "stalleddl",
            "queueddl",
            "forceddl",
            "metadl",
            "checkingdl",
        }:
            return "downloading"
        return "unknown"
