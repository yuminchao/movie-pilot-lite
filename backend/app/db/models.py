from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RecordMixin


class AdminUser(RecordMixin, Base):
    """单一管理员账户。"""

    __tablename__ = "admin_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionRecord(RecordMixin, Base):
    """服务端管理员会话。"""

    __tablename__ = "session"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AppConfig(RecordMixin, Base):
    """使用固定 key 保存的加密配置。"""

    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)


class DownloadRecord(RecordMixin, Base):
    """已提交到 qBittorrent 的下载记录。"""

    __tablename__ = "download_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    qb_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    category: Mapped[str | None] = mapped_column(String(100))
    save_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

