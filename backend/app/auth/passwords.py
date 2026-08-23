from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """生成管理员密码的 Argon2id 哈希。"""
    if len(password) < 12:
        raise ValueError("管理员密码至少需要 12 个字符")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码并将错误哈希视为认证失败。"""
    try:
        return _hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False

