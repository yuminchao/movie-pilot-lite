from typing import Any

from app.config.repository import ConfigKey, ConfigRepository
from app.config.vault import SecretVault
from app.db.session import Database
from app.integrations.mteam import MTeamClient
from app.integrations.qbittorrent import QbittorrentClient, QbittorrentConfig


class SettingsService:
    """加密保存第三方配置并执行连接测试。"""

    def __init__(self, database: Database, vault: SecretVault) -> None:
        self._database = database
        self._vault = vault

    def save_mteam(self, value: dict[str, Any]) -> dict[str, Any]:
        """加密保存 M-Team 连接配置。"""
        repository = self._repository()
        repository.set_secret(ConfigKey.MTEAM_CONNECTION, value)
        return repository.get_masked_status(ConfigKey.MTEAM_CONNECTION)

    def get_mteam(self) -> dict[str, Any]:
        """返回 M-Team 配置的掩码状态。"""
        return self._repository().get_masked_status(ConfigKey.MTEAM_CONNECTION)

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
        return self._repository().get_secret(ConfigKey.DOWNLOAD_DEFAULTS) or {
            "category": "downloads",
            "save_path": "/downloads",
            "start": True,
        }

    def _required(self, key: ConfigKey) -> dict[str, Any]:
        value = self._repository().get_secret(key)
        if value is None:
            raise ValueError("连接尚未配置")
        return value

    def _repository(self) -> ConfigRepository:
        return ConfigRepository(self._database.session_factory, self._vault.cipher)
