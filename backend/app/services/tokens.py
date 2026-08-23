import base64
import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta


class InvalidSourceToken(ValueError):
    """搜索结果下载标识无效或已经过期。"""


class SourceTokenCodec:
    """签发和验证短期搜索结果下载标识。"""

    def __init__(
        self,
        secret: bytes,
        ttl: timedelta = timedelta(minutes=15),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if len(secret) < 8:
            raise ValueError("签名密钥过短")
        self._secret = secret
        self._ttl = ttl
        self._clock = clock or (lambda: datetime.now(UTC))

    def encode(self, source_id: str, title: str) -> str:
        """签发包含来源 ID、标题和过期时间的标识。"""
        payload = json.dumps(
            {
                "source_id": source_id,
                "title": title,
                "exp": int((self._clock() + self._ttl).timestamp()),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        encoded = self._encode(payload)
        signature = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        return f"{encoded}.{self._encode(signature)}"

    def decode(self, token: str) -> dict[str, str]:
        """验证标识并返回下载所需的最小来源信息。"""
        try:
            encoded, encoded_signature = token.split(".", 1)
            expected = hmac.new(
                self._secret,
                encoded.encode("ascii"),
                hashlib.sha256,
            ).digest()
            signature = self._decode(encoded_signature)
            if not hmac.compare_digest(signature, expected):
                raise InvalidSourceToken("下载标识无效")
            payload = json.loads(self._decode(encoded))
            if int(payload["exp"]) < int(self._clock().timestamp()):
                raise InvalidSourceToken("下载标识已经过期")
            source_id = str(payload["source_id"])
            title = str(payload["title"])
            if not source_id or not title:
                raise InvalidSourceToken("下载标识无效")
            return {"source_id": source_id, "title": title}
        except InvalidSourceToken:
            raise
        except (ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
            raise InvalidSourceToken("下载标识无效") from error

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.b64decode(
            f"{value}{padding}".encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
