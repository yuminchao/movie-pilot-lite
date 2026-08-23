import json
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.crypto import SecretCipher
from app.db.models import AppConfig


class ConfigKey(StrEnum):
    """允许持久化的配置键。"""

    MTEAM_CONNECTION = "mteam.connection"
    QBITTORRENT_CONNECTION = "qbittorrent.connection"
    DOWNLOAD_DEFAULTS = "download.defaults"


class ConfigRepository:
    """加密读写结构化应用配置。"""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        cipher: SecretCipher,
    ) -> None:
        self._session_factory = session_factory
        self._cipher = cipher

    def set_secret(self, key: ConfigKey, value: dict[str, Any]) -> None:
        """加密并更新一个固定配置键。"""
        checked_key = self._validate_key(key)
        plaintext = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        encrypted_value = self._cipher.encrypt(plaintext)
        with self._session_factory() as session:
            record = session.scalar(select(AppConfig).where(AppConfig.key == checked_key.value))
            if record is None:
                record = AppConfig(key=checked_key.value, encrypted_value=encrypted_value)
                session.add(record)
            else:
                record.encrypted_value = encrypted_value
            session.commit()

    def get_secret(self, key: ConfigKey) -> dict[str, Any] | None:
        """解密并解析一个固定配置键。"""
        checked_key = self._validate_key(key)
        with self._session_factory() as session:
            record = session.scalar(select(AppConfig).where(AppConfig.key == checked_key.value))
            if record is None:
                return None
            value = json.loads(self._cipher.decrypt(record.encrypted_value))
            if not isinstance(value, dict):
                raise ValueError("配置值必须是对象")
            return value

    def get_masked_status(self, key: ConfigKey) -> dict[str, Any]:
        """返回不泄露密文或明文的配置状态。"""
        checked_key = self._validate_key(key)
        with self._session_factory() as session:
            record = session.scalar(select(AppConfig).where(AppConfig.key == checked_key.value))
            if record is None:
                return {"configured": False, "masked": None, "updated_at": None}
            return {
                "configured": True,
                "masked": "••••••••",
                "updated_at": record.mtime.isoformat(),
            }

    @staticmethod
    def _validate_key(key: ConfigKey) -> ConfigKey:
        if not isinstance(key, ConfigKey):
            raise ValueError("不允许的配置键")
        return key

