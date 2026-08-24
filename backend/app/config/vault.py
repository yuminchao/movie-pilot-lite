import logging
import threading
from collections.abc import Callable

from app.config.crypto import SecretCipher


logger = logging.getLogger(__name__)


class SecretVault:
    """保存当前进程中已解锁的敏感配置加密器。"""

    def __init__(self) -> None:
        self._cipher: SecretCipher | None = None
        self._unlock_listeners: list[Callable[[], None]] = []
        self._listener_lock = threading.Lock()

    def add_unlock_listener(self, callback: Callable[[], None]) -> None:
        """注册解锁成功后的去重回调。

        Args:
            callback: 解锁成功后调用的无参数函数。
        """
        with self._listener_lock:
            if callback not in self._unlock_listeners:
                self._unlock_listeners.append(callback)

    def unlock(self, password: str) -> None:
        """使用已验证的管理员密码解锁配置并通知监听器。

        Args:
            password: 已通过身份验证的管理员密码。
        """
        self._cipher = SecretCipher.from_password(password)
        with self._listener_lock:
            listeners = tuple(self._unlock_listeners)
        for listener in listeners:
            try:
                listener()
            except Exception as error:
                logger.warning("保险库解锁监听器异常类型: %s", type(error).__name__)

    @property
    def is_unlocked(self) -> bool:
        """判断当前进程是否已经通过管理员登录解锁。"""
        return self._cipher is not None

    @property
    def cipher(self) -> SecretCipher:
        """返回当前加密器；未登录时拒绝访问。"""
        if self._cipher is None:
            raise RuntimeError("敏感配置尚未解锁")
        return self._cipher
