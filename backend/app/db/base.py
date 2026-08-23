from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """SQLAlchemy 声明基类。"""


class RecordMixin:
    """所有持久化记录共享的有效性和审计字段。"""

    isvalid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ctime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    mtime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

