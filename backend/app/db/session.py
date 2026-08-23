from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base


class Database:
    """拥有 SQLAlchemy 引擎和同步会话工厂。"""

    def __init__(self, url: str) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=connect_args)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    def create_schema(self) -> None:
        """为测试和首次启动创建当前模型结构。"""
        Base.metadata.create_all(self.engine)

