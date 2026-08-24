from typing import Any

from app.config.repository import ConfigKey, ConfigRepository
from app.config.vault import SecretVault
from app.db.session import Database
from app.integrations.mteam import MTeamClient
from app.integrations.qbittorrent import QbittorrentClient, QbittorrentConfig

MTEAM_SECRET_MASK = "••••••••"
MTEAM_DEFAULTS: dict[str, Any] = {
    "base_url": "https://kp.m-team.cc",
    "headers": {},
    "cookie": None,
    "user_agent": "movie-pilot-lite/0.1",
    "timeout": 15,
}


class SettingsService:
    """加密保存第三方配置并执行连接测试。"""

    def __init__(self, database: Database, vault: SecretVault) -> None:
        self._database = database
        self._vault = vault

    def save_mteam(self, value: dict[str, Any]) -> dict[str, Any]:
        """加密保存 M-Team 连接配置。"""
        repository = self._repository()
        previous = repository.get_secret(ConfigKey.MTEAM_CONNECTION)
        previous_headers = previous["headers"] if previous is not None else {}
        headers: dict[str, str] = {}
        for key, header_value in value["headers"].items():
            if header_value == MTEAM_SECRET_MASK:
                if key not in previous_headers:
                    raise ValueError(f"Header {key} 没有可保留的旧值")
                headers[key] = previous_headers[key]
            else:
                headers[key] = header_value

        cookie = value["cookie"]
        if cookie == MTEAM_SECRET_MASK:
            if previous is None or not previous.get("cookie"):
                raise ValueError("Cookie 没有可保留的旧值")
            cookie = previous["cookie"]

        saved_value = {**value, "headers": headers, "cookie": cookie}
        repository.set_secret(ConfigKey.MTEAM_CONNECTION, saved_value)
        return self._mteam_view(repository, saved_value)

    def get_mteam(self) -> dict[str, Any]:
        """返回 M-Team 配置的掩码状态。"""
        repository = self._repository()
        return self._mteam_view(
            repository,
            repository.get_secret(ConfigKey.MTEAM_CONNECTION),
        )

    def save_qbittorrent(self, value: dict[str, Any]) -> dict[str, Any]:
        """加密保存 qBittorrent 连接配置。"""
        repository = self._repository()
        repository.set_secret(ConfigKey.QBITTORRENT_CONNECTION, value)
        return repository.get_masked_status(ConfigKey.QBITTORRENT_CONNECTION)

    def get_qbittorrent(self) -> dict[str, Any]:
        """返回 qBittorrent 配置的掩码状态。"""
        return self._repository().get_masked_status(ConfigKey.QBITTORRENT_CONNECTION)

    def test_mteam(self) -> dict[str, Any]:
        """使用已保存配置验证 M-Team 连接。"""
        value = self._required(ConfigKey.MTEAM_CONNECTION)
        MTeamClient(**value).test_connection()
        return {"success": True, "message": "M-Team 连接成功"}

    def test_qbittorrent(self) -> dict[str, Any]:
        """使用已保存配置验证 qBittorrent 连接。"""
        value = self._required(ConfigKey.QBITTORRENT_CONNECTION)
        QbittorrentClient(QbittorrentConfig(**value)).test_connection()
        return {"success": True, "message": "qBittorrent 连接成功"}

    def save_download_defaults(self, value: dict[str, Any]) -> dict[str, Any]:
        """保存搜索结果展开表单使用的 qBittorrent 默认值。"""
        self._repository().set_secret(ConfigKey.DOWNLOAD_DEFAULTS, value)
        return value

    def get_download_defaults(self) -> dict[str, Any]:
        """返回下载默认值或安全的首次使用值。"""
        value = self._repository().get_secret(ConfigKey.DOWNLOAD_DEFAULTS)
        if value is None:
            return {
                "category": "downloads",
                "save_paths": {
                    "movie": "/downloads",
                    "tv": "/downloads",
                    "music": "/downloads",
                    "other": "/downloads",
                },
                "start": True,
            }
        if "save_paths" in value:
            return value

        legacy_path = value["save_path"]
        return {
            "category": value["category"],
            "save_paths": {
                "movie": legacy_path,
                "tv": legacy_path,
                "music": legacy_path,
                "other": legacy_path,
            },
            "start": value["start"],
        }

    def _required(self, key: ConfigKey) -> dict[str, Any]:
        value = self._repository().get_secret(key)
        if value is None:
            raise ValueError("连接尚未配置")
        return value

    def _repository(self) -> ConfigRepository:
        return ConfigRepository(self._database.session_factory, self._vault.cipher)

    @staticmethod
    def _mteam_view(
        repository: ConfigRepository,
        value: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """组装仅暴露公开字段和统一掩码的 M-Team 配置视图。"""
        status = repository.get_masked_status(ConfigKey.MTEAM_CONNECTION)
        if value is None:
            return {**status, **MTEAM_DEFAULTS}

        normalized = {**MTEAM_DEFAULTS, **value}
        return {
            "configured": True,
            "masked": MTEAM_SECRET_MASK,
            "updated_at": status["updated_at"],
            "base_url": normalized["base_url"],
            "headers": {
                key: MTEAM_SECRET_MASK for key in normalized["headers"]
            },
            "cookie": MTEAM_SECRET_MASK if normalized["cookie"] else None,
            "user_agent": normalized["user_agent"],
            "timeout": normalized["timeout"],
        }
