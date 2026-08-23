import secrets
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from app.auth.passwords import hash_password, verify_password
from app.db.models import AdminUser, SessionRecord
from app.db.session import Database

SESSION_COOKIE = "movie_pilot_lite_session"
SESSION_TTL = timedelta(hours=12)
LOGIN_WINDOW_SECONDS = 60
LOGIN_FAILURE_LIMIT = 10


class RateLimitExceeded(RuntimeError):
    """登录失败次数超过短时窗口限制。"""


def _as_utc(value: datetime) -> datetime:
    """将 SQLite 返回的 naive 时间按 UTC 解释。"""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class AuthService:
    """管理单一管理员账户和服务端会话。"""

    def __init__(
        self,
        database: Database,
        on_unlock: Callable[[str], None] | None = None,
        is_unlocked: Callable[[], bool] | None = None,
    ) -> None:
        self._database = database
        self._on_unlock = on_unlock
        self._is_unlocked = is_unlocked or (lambda: True)
        self._login_failures: dict[str, list[float]] = {}
        self._failure_lock = threading.Lock()

    def has_admin(self) -> bool:
        """判断管理员账户是否已经初始化。"""
        with self._database.session_factory() as session:
            return session.scalar(select(func.count(AdminUser.id))) > 0

    def setup(self, password: str) -> None:
        """创建首次管理员账户。"""
        password_hash = hash_password(password)
        with self._database.session_factory() as session:
            if session.scalar(select(func.count(AdminUser.id))) > 0:
                raise RuntimeError("管理员已经初始化")
            session.add(AdminUser(password_hash=password_hash))
            session.commit()

    def login(self, password: str, source: str = "unknown") -> str | None:
        """验证管理员密码并创建服务端会话。"""
        now_monotonic = time.monotonic()
        with self._failure_lock:
            failures = [
                timestamp
                for timestamp in self._login_failures.get(source, [])
                if now_monotonic - timestamp < LOGIN_WINDOW_SECONDS
            ]
            self._login_failures[source] = failures
            if len(failures) >= LOGIN_FAILURE_LIMIT:
                raise RateLimitExceeded("登录尝试过于频繁，请稍后重试")
        with self._database.session_factory() as session:
            admin = session.scalar(select(AdminUser).order_by(AdminUser.id))
            if admin is None or not verify_password(password, admin.password_hash):
                with self._failure_lock:
                    self._login_failures[source].append(now_monotonic)
                return None
            now = datetime.now(UTC)
            admin.last_login_at = now
            session_id = secrets.token_urlsafe(32)
            session.execute(update(SessionRecord).values(isvalid=False))
            session.add(
                SessionRecord(
                    id=session_id,
                    expires_at=now + SESSION_TTL,
                    last_seen_at=now,
                )
            )
            session.commit()
            with self._failure_lock:
                self._login_failures.pop(source, None)
            if self._on_unlock:
                self._on_unlock(password)
            return session_id

    def is_valid(self, session_id: str | None) -> bool:
        """判断会话是否存在、有效且未过期。"""
        if not session_id or not self._is_unlocked():
            return False
        now = datetime.now(UTC)
        with self._database.session_factory() as session:
            record = session.get(SessionRecord, session_id)
            if record is None or not record.isvalid or _as_utc(record.expires_at) <= now:
                return False
            record.last_seen_at = now
            session.commit()
            return True

    def logout(self, session_id: str | None) -> None:
        """使当前会话失效。"""
        if not session_id:
            return
        with self._database.session_factory() as session:
            record = session.get(SessionRecord, session_id)
            if record:
                record.isvalid = False
                session.commit()
