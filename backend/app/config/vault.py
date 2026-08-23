from app.config.crypto import SecretCipher


class SecretVault:
    """保存当前进程中已解锁的敏感配置加密器。"""

    def __init__(self) -> None:
        self._cipher: SecretCipher | None = None

    def unlock(self, password: str) -> None:
        """使用已验证的管理员密码解锁配置。"""
        self._cipher = SecretCipher.from_password(password)

    @property
    def cipher(self) -> SecretCipher:
        """返回当前加密器；未登录时拒绝访问。"""
        if self._cipher is None:
            raise RuntimeError("敏感配置尚未解锁")
        return self._cipher

