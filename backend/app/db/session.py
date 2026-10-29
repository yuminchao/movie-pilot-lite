from typing import Any
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base


def ensure_database(url: str) -> None:
    """MySQL：确保目标数据库存在，不存在则按 utf8mb4 创建。

    SQLite 等其他数据库不执行任何操作。应用启动和 Alembic 迁移前都会调用，
    部署时无需手动执行 CREATE DATABASE。

    Args:
        url: SQLAlchemy 数据库连接地址。
    """
    if not url.startswith("mysql"):
        return
    parsed = urlparse(url)
    database = (parsed.path or "/").lstrip("/")
    if not database:
        return
    server_url = parsed._replace(path="/").geturl()
    engine = create_engine(server_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE DATABASE IF NOT EXISTS "
                    f"`{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    finally:
        engine.dispose()


class Database:
    """拥有 SQLAlchemy 引擎和同步会话工厂。"""

    def __init__(self, url: str) -> None:
        if url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
            pool_kwargs: dict[str, Any] = {}
        else:
            connect_args = {}
            # MySQL 连接可能被服务端或网络中断，pre_ping 与 recycle 保持连接健康。
            pool_kwargs = {"pool_pre_ping": True, "pool_recycle": 3600}
            ensure_database(url)
        self.engine = create_engine(url, connect_args=connect_args, **pool_kwargs)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    def create_schema(self) -> None:
        """为测试和首次启动创建当前模型结构。"""
        Base.metadata.create_all(self.engine)
