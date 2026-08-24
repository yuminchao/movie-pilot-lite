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
        """初始化设置服务。

        Args:
            database: 应用数据库连接。
            vault: 当前进程的敏感配置保险库。
        """
        self._database = database
        self._vault = vault

    def save_mteam(self, value: dict[str, Any]) -> dict[str, Any]:
        """合并掩码占位符并加密保存 M-Team 连接配置。

        Args:
            value: 包含公开字段和敏感字段占位符的完整连接配置。

        Returns:
            不包含 Header 和 Cookie 明文的配置视图。

        Raises:
            ValueError: 掩码字段没有可保留的旧值。
            RuntimeError: 敏感配置保险库尚未解锁。
            sqlalchemy.exc.SQLAlchemyError: 配置仓库读写失败。
        """
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
        """读取 M-Team 配置并返回敏感字段掩码视图。

        Returns:
            配置状态、公开连接字段和敏感字段掩码。

        Raises:
            RuntimeError: 敏感配置保险库尚未解锁。
            ValueError: 已保存的加密配置无法解析。
            sqlalchemy.exc.SQLAlchemyError: 配置仓库读取失败。
        """
        repository = self._repository()
        return self._mteam_view(
            repository,
            repository.get_secret(ConfigKey.MTEAM_CONNECTION),
        )

    def save_qbittorrent(self, value: dict[str, Any]) -> dict[str, Any]:
        """加密保存 qBittorrent 连接配置。

        Args:
            value: 已通过请求模型校验的连接配置。

        Returns:
            不包含凭据明文的配置状态。

        Raises:
            RuntimeError: 敏感配置保险库尚未解锁。
            sqlalchemy.exc.SQLAlchemyError: 配置仓库写入失败。
        """
        repository = self._repository()
        repository.set_secret(ConfigKey.QBITTORRENT_CONNECTION, value)
        return repository.get_masked_status(ConfigKey.QBITTORRENT_CONNECTION)

    def get_qbittorrent(self) -> dict[str, Any]:
        """返回 qBittorrent 配置的掩码状态。

        Returns:
            不包含凭据明文的配置状态。

        Raises:
            RuntimeError: 敏感配置保险库尚未解锁。
            sqlalchemy.exc.SQLAlchemyError: 配置仓库读取失败。
        """
        return self._repository().get_masked_status(ConfigKey.QBITTORRENT_CONNECTION)

    def test_mteam(self) -> dict[str, Any]:
        """使用已保存配置验证 M-Team 连接。

        Returns:
            包含成功状态和公开消息的结果。

        Raises:
            ValueError: M-Team 连接尚未配置。
            RuntimeError: 敏感配置保险库尚未解锁。
            app.integrations.mteam.IntegrationError: 连接验证失败。
        """
        value = self._required(ConfigKey.MTEAM_CONNECTION)
        MTeamClient(**value).test_connection()
        return {"success": True, "message": "M-Team 连接成功"}

    def test_qbittorrent(self) -> dict[str, Any]:
        """使用已保存配置验证 qBittorrent 连接。

        Returns:
            包含成功状态和公开消息的结果。

        Raises:
            ValueError: qBittorrent 连接尚未配置。
            RuntimeError: 敏感配置保险库尚未解锁。
            app.integrations.qbittorrent.QbittorrentError: 连接验证失败。
        """
        value = self._required(ConfigKey.QBITTORRENT_CONNECTION)
        QbittorrentClient(QbittorrentConfig(**value)).test_connection()
        return {"success": True, "message": "qBittorrent 连接成功"}

    def save_download_defaults(self, value: dict[str, Any]) -> dict[str, Any]:
        """加密保存搜索结果展开表单使用的下载默认值。

        Args:
            value: 已通过请求模型校验的下载默认值。

        Returns:
            保存后的下载默认值。

        Raises:
            RuntimeError: 敏感配置保险库尚未解锁。
            sqlalchemy.exc.SQLAlchemyError: 配置仓库写入失败。
        """
        self._repository().set_secret(ConfigKey.DOWNLOAD_DEFAULTS, value)
        return value

    def get_download_defaults(self) -> dict[str, Any]:
        """读取下载默认值并兼容旧版单路径配置。

        Returns:
            按资源类型归一化后的下载默认值。

        Raises:
            RuntimeError: 敏感配置保险库尚未解锁。
            ValueError: 已保存的加密配置无法解析。
            sqlalchemy.exc.SQLAlchemyError: 配置仓库读取失败。
        """
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
        """读取必须存在的加密连接配置。

        Args:
            key: 需要读取的固定配置键。

        Returns:
            解密后的结构化配置。

        Raises:
            ValueError: 指定连接尚未配置或配置无法解析。
            RuntimeError: 敏感配置保险库尚未解锁。
            sqlalchemy.exc.SQLAlchemyError: 配置仓库读取失败。
        """
        value = self._repository().get_secret(key)
        if value is None:
            raise ValueError("连接尚未配置")
        return value

    def _repository(self) -> ConfigRepository:
        """使用当前解锁密钥构造配置仓库。

        Returns:
            可读写加密配置的仓库。

        Raises:
            RuntimeError: 敏感配置保险库尚未解锁。
        """
        return ConfigRepository(self._database.session_factory, self._vault.cipher)

    @staticmethod
    def _mteam_view(
        repository: ConfigRepository,
        value: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """组装仅暴露公开字段和统一掩码的 M-Team 配置视图。

        Args:
            repository: 用于读取配置更新时间的加密配置仓库。
            value: 解密后的 M-Team 配置；未配置时为 None。

        Returns:
            包含公开字段、状态和敏感字段掩码的配置视图。

        Raises:
            sqlalchemy.exc.SQLAlchemyError: 配置状态读取失败。
        """
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
