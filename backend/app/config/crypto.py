import base64
import os

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VERSION = 1
_SALT_SIZE = 16
_NONCE_SIZE = 12


class InvalidSecret(ValueError):
    """密文格式、版本或认证标签无效。"""


class SecretCipher:
    """使用管理员密码派生的密钥加密敏感配置。"""

    def __init__(self, password: bytes) -> None:
        self._password = password

    @classmethod
    def from_password(cls, password: str) -> "SecretCipher":
        """从非空管理员密码创建加密器。"""
        if not password:
            raise ValueError("管理员密码不能为空")
        return cls(password.encode("utf-8"))

    def encrypt(self, plaintext: str) -> str:
        """使用独立 salt 和 nonce 生成带认证的密文。"""
        salt = os.urandom(_SALT_SIZE)
        nonce = os.urandom(_NONCE_SIZE)
        key = self._derive_key(salt)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
        payload = bytes([_VERSION]) + salt + nonce + ciphertext
        return base64.urlsafe_b64encode(payload).decode("ascii")

    def decrypt(self, token: str) -> str:
        """验证并解密配置密文。

        Raises:
            InvalidSecret: 密文损坏、版本不支持或密码不匹配。
        """
        try:
            payload = base64.b64decode(token.encode("ascii"), altchars=b"-_", validate=True)
            minimum_size = 1 + _SALT_SIZE + _NONCE_SIZE + 16
            if len(payload) < minimum_size or payload[0] != _VERSION:
                raise InvalidSecret("敏感配置密文无效")
            salt_start = 1
            nonce_start = salt_start + _SALT_SIZE
            ciphertext_start = nonce_start + _NONCE_SIZE
            salt = payload[salt_start:nonce_start]
            nonce = payload[nonce_start:ciphertext_start]
            plaintext = AESGCM(self._derive_key(salt)).decrypt(
                nonce,
                payload[ciphertext_start:],
                None,
            )
            return plaintext.decode("utf-8")
        except (ValueError, UnicodeError, InvalidTag) as error:
            if isinstance(error, InvalidSecret):
                raise
            raise InvalidSecret("敏感配置密文无效") from error

    def _derive_key(self, salt: bytes) -> bytes:
        """使用 Argon2id 派生 AES-256 密钥。"""
        return hash_secret_raw(
            secret=self._password,
            salt=salt,
            time_cost=2,
            memory_cost=19_456,
            parallelism=1,
            hash_len=32,
            type=Type.ID,
        )

