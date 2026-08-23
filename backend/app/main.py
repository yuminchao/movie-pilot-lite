from pathlib import Path

from fastapi import Depends, FastAPI

from app.api import auth, search
from app.auth.session import AuthService
from app.db.session import Database


def create_app(database_url: str | None = None) -> FastAPI:
    """创建带独立数据库和认证服务的 FastAPI 应用。"""
    url = database_url or "sqlite:///./data/movie-pilot-lite.db"
    if url.startswith("sqlite:///./data/"):
        Path("data").mkdir(parents=True, exist_ok=True)
    database = Database(url)
    database.create_schema()
    service = AuthService(database)
    application = FastAPI(title="movie-pilot-lite")
    application.state.auth_service = service
    application.dependency_overrides[auth.get_auth_service] = lambda: service

    @application.get("/api/health")
    def health() -> dict[str, str]:
        """返回不依赖外部服务的进程健康状态。"""
        return {"status": "ok"}

    @application.get("/api/settings/mteam")
    def mteam_settings(_: str = Depends(auth.require_session)) -> dict[str, bool]:
        """返回受保护的设置占位状态。"""
        return {"configured": False}

    application.include_router(auth.router)
    application.include_router(search.router)
    return application


app = create_app()
