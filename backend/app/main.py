import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from threading import RLock
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, downloads, search, settings, video
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
from app.services.checkin_scheduler import CheckinScheduler
from app.services.downloads import DownloadService
from app.services.search import SearchService
from app.services.tokens import SourceTokenCodec


def create_app(
    database_url: str | None = None,
    frontend_dir: Path | None = None,
) -> FastAPI:
    """创建并装配数据库、认证、签到调度与 API 路由。

    Args:
        database_url: 数据库连接地址；未提供时读取环境变量或使用默认值。
        frontend_dir: 前端静态构建目录；未提供时使用仓库默认目录。

    Returns:
        已配置依赖、异常处理器和生命周期的 FastAPI 应用。

    Raises:
        sqlalchemy.exc.SQLAlchemyError: 数据库初始化或建表失败。
    """
    url = database_url or os.getenv(
        "DATABASE_URL",
        "sqlite:///./data/movie-pilot-lite.db",
    )
    if url.startswith("sqlite:///./data/"):
        Path("data").mkdir(parents=True, exist_ok=True)
    database = Database(url)
    database.create_schema()
    vault = SecretVault()
    token_codec = SourceTokenCodec(secrets.token_bytes(32))

    def repository() -> ConfigRepository:
        """使用当前登录解锁的密钥构造配置仓库。

        Returns:
            可读写加密配置的仓库。

        Raises:
            RuntimeError: 敏感配置保险库尚未解锁。
        """
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

    checkin_scheduler = CheckinScheduler(
        checkin_service,
        lambda: vault.is_unlocked,
    )
    vault.add_unlock_listener(checkin_scheduler.wake)
    service = AuthService(
        database,
        on_unlock=vault.unlock,
        is_unlocked=lambda: vault.is_unlocked,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """在应用生命周期内启动并完整停止签到调度器。

        Args:
            _: 当前 FastAPI 应用。

        Yields:
            应用处理请求的生命周期控制权。

        Raises:
            RuntimeError: 启动时没有正在运行的事件循环。
        """
        checkin_scheduler.start()
        try:
            yield
        finally:
            await checkin_scheduler.stop()

    application = FastAPI(title="movie-pilot-lite", lifespan=lifespan)
    application.state.auth_service = service
    application.state.database = database
    application.state.secret_vault = vault
    application.state.get_checkin_service = checkin_service
    application.state.checkin_scheduler = checkin_scheduler
    application.dependency_overrides[auth.get_auth_service] = lambda: service

    def mteam_client() -> MTeamClient:
        """从加密配置构造 M-Team 客户端。

        Returns:
            使用已保存连接配置的 M-Team 客户端。

        Raises:
            HTTPException: M-Team 连接尚未配置。
            RuntimeError: 敏感配置保险库尚未解锁。
            ValueError: 已保存配置无效。
        """
        value = repository().get_secret(ConfigKey.MTEAM_CONNECTION)
        if value is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="M-Team 尚未配置",
            )
        return MTeamClient(**value)

    def search_service() -> SearchService:
        """组装请求所需的搜索服务。

        Returns:
            使用当前 M-Team 配置和临时令牌编码器的搜索服务。

        Raises:
            HTTPException: M-Team 连接尚未配置。
            RuntimeError: 敏感配置保险库尚未解锁。
            ValueError: 已保存配置无效。
        """
        return SearchService(
            mteam_client(),
            lambda result: token_codec.encode(result.source_id, result.title),
        )

    def download_service() -> DownloadService:
        """从加密配置组装下载服务。

        Returns:
            使用当前站点和下载器配置的下载服务。

        Raises:
            HTTPException: M-Team 或 qBittorrent 连接尚未配置。
            RuntimeError: 敏感配置保险库尚未解锁。
            ValueError: 已保存配置无效。
        """
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
        """将脱敏第三方错误转换为稳定的 502 响应。

        Args:
            _: 当前 HTTP 请求。
            error: 已脱敏的第三方集成异常。

        Returns:
            包含公开错误消息的 502 JSON 响应。
        """
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": str(error)},
        )

    async def request_validation_error_handler(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        """按请求路径返回默认或凭据脱敏的 422 响应。

        Args:
            request: 发生请求校验错误的 HTTP 请求。
            error: FastAPI 请求校验异常。

        Returns:
            凭据端点返回移除原始输入的错误；其他端点返回 FastAPI 默认错误。
        """
        if request.url.path not in {
            "/mpl/api/auth/login",
            "/mpl/api/auth/setup",
            "/mpl/api/settings/mteam",
            "/mpl/api/settings/qbittorrent",
        }:
            return await request_validation_exception_handler(request, error)
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

    @application.get("/mpl/api/health")
    def health() -> dict[str, str]:
        """返回不依赖外部服务的进程健康状态。

        Returns:
            固定的健康状态对象。
        """
        return {"status": "ok"}

    application.include_router(auth.router, prefix="/mpl")
    application.include_router(search.router, prefix="/mpl")
    application.include_router(downloads.router, prefix="/mpl")
    application.include_router(settings.router, prefix="/mpl")
    application.include_router(video.router, prefix="/mpl")

    static_root = frontend_dir or Path(__file__).resolve().parents[2] / "frontend" / "dist"
    index_file = static_root / "index.html"
    assets_dir = static_root / "assets"
    if assets_dir.is_dir():
        application.mount("/mpl/assets", StaticFiles(directory=assets_dir), name="assets")
    if index_file.is_file():

        @application.get("/mpl/{path:path}", include_in_schema=False)
        def frontend_fallback(path: str) -> FileResponse:
            """为非 API 前端路由返回静态文件或 Vite 入口文件。

            Args:
                path: 请求的应用内相对路径（相对 /mpl 前缀）。

            Returns:
                匹配的静态文件或单页应用入口文件。

            Raises:
                HTTPException: 路径属于不存在的 API。
            """
            if path == "api" or path.startswith("api/"):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
            requested = static_root / path
            if path and requested.is_file() and static_root in requested.resolve().parents:
                return FileResponse(requested)
            return FileResponse(index_file)
    return application


app = create_app()
