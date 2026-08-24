import os
import secrets
from pathlib import Path
from threading import RLock
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, downloads, search, settings
from app.auth.session import AuthService
from app.config.repository import ConfigKey, ConfigRepository
from app.config.vault import SecretVault
from app.db.session import Database
from app.integrations.mteam import IntegrationError, MTeamClient
from app.integrations.qbittorrent import (
    QbittorrentClient,
    QbittorrentConfig,
    QbittorrentError,
)
from app.services.checkin import CheckinService
from app.services.downloads import DownloadService
from app.services.search import SearchService
from app.services.tokens import SourceTokenCodec


def create_app(
    database_url: str | None = None,
    frontend_dir: Path | None = None,
) -> FastAPI:
    """创建带独立数据库和认证服务的 FastAPI 应用。"""
    url = database_url or os.getenv(
        "DATABASE_URL",
        "sqlite:///./data/movie-pilot-lite.db",
    )
    if url.startswith("sqlite:///./data/"):
        Path("data").mkdir(parents=True, exist_ok=True)
    database = Database(url)
    database.create_schema()
    vault = SecretVault()
    service = AuthService(
        database,
        on_unlock=vault.unlock,
        is_unlocked=lambda: vault.is_unlocked,
    )
    token_codec = SourceTokenCodec(secrets.token_bytes(32))
    application = FastAPI(title="movie-pilot-lite")
    application.state.auth_service = service
    application.state.database = database
    application.state.secret_vault = vault
    application.dependency_overrides[auth.get_auth_service] = lambda: service

    def repository() -> ConfigRepository:
        """使用当前登录解锁的密钥构造配置仓库。"""
        return ConfigRepository(database.session_factory, vault.cipher)

    checkin_instance: CheckinService | None = None
    checkin_init_lock = RLock()

    def checkin_service() -> CheckinService:
        """返回应用级共享签到模块，并在首次使用时完成初始化。

        Returns:
            当前应用唯一的签到模块实例。

        Raises:
            RuntimeError: 敏感配置密钥库尚未解锁。
            zoneinfo.ZoneInfoNotFoundError: 应用时区配置无效。
        """
        nonlocal checkin_instance
        with checkin_init_lock:
            if checkin_instance is None:
                checkin_instance = CheckinService(
                    repository(),
                    lambda value: MTeamClient(**value),
                    ZoneInfo(os.getenv("TZ", "Asia/Shanghai")),
                )
            return checkin_instance

    application.state.get_checkin_service = checkin_service

    def mteam_client() -> MTeamClient:
        """从加密配置构造 M-Team 客户端。"""
        value = repository().get_secret(ConfigKey.MTEAM_CONNECTION)
        if value is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="M-Team 尚未配置",
            )
        return MTeamClient(**value)

    def search_service() -> SearchService:
        """组装请求所需的搜索服务。"""
        return SearchService(
            mteam_client(),
            lambda result: token_codec.encode(result.source_id, result.title),
        )

    def download_service() -> DownloadService:
        """从加密配置组装下载服务。"""
        value = repository().get_secret(ConfigKey.QBITTORRENT_CONNECTION)
        if value is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="qBittorrent 尚未配置",
            )
        qb_client = QbittorrentClient(QbittorrentConfig(**value))
        return DownloadService(database, token_codec, mteam_client(), qb_client)

    application.dependency_overrides[search.get_search_service] = search_service
    application.dependency_overrides[downloads.get_download_service] = download_service
    application.dependency_overrides[settings.get_checkin_service] = checkin_service

    async def integration_error_handler(
        _: Request,
        error: IntegrationError | QbittorrentError,
    ) -> JSONResponse:
        """将脱敏第三方错误转换为稳定的 502 响应。"""
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": str(error)},
        )

    async def request_validation_error_handler(
        _: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        """返回不包含请求原值和校验上下文的 422 响应。"""
        detail = [
            {
                "type": item["type"],
                "loc": item["loc"],
                "msg": item["msg"],
            }
            for item in error.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": detail},
        )

    application.add_exception_handler(IntegrationError, integration_error_handler)
    application.add_exception_handler(QbittorrentError, integration_error_handler)
    application.add_exception_handler(
        RequestValidationError,
        request_validation_error_handler,
    )

    @application.get("/api/health")
    def health() -> dict[str, str]:
        """返回不依赖外部服务的进程健康状态。"""
        return {"status": "ok"}

    application.include_router(auth.router)
    application.include_router(search.router)
    application.include_router(downloads.router)
    application.include_router(settings.router)

    static_root = frontend_dir or Path(__file__).resolve().parents[2] / "frontend" / "dist"
    index_file = static_root / "index.html"
    assets_dir = static_root / "assets"
    if assets_dir.is_dir():
        application.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    if index_file.is_file():

        @application.get("/{path:path}", include_in_schema=False)
        def frontend_fallback(path: str) -> FileResponse:
            """为非 API 前端路由返回 Vite 入口文件。"""
            if path == "api" or path.startswith("api/"):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
            requested = static_root / path
            if path and requested.is_file() and static_root in requested.resolve().parents:
                return FileResponse(requested)
            return FileResponse(index_file)
    return application


app = create_app()
