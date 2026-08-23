import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, status

from app.api import auth, downloads, search, settings
from app.auth.session import AuthService
from app.config.repository import ConfigKey, ConfigRepository
from app.config.vault import SecretVault
from app.db.session import Database
from app.integrations.mteam import MTeamClient
from app.integrations.qbittorrent import QbittorrentClient, QbittorrentConfig
from app.services.downloads import DownloadService
from app.services.search import SearchService
from app.services.tokens import SourceTokenCodec


def create_app(database_url: str | None = None) -> FastAPI:
    """创建带独立数据库和认证服务的 FastAPI 应用。"""
    url = database_url or "sqlite:///./data/movie-pilot-lite.db"
    if url.startswith("sqlite:///./data/"):
        Path("data").mkdir(parents=True, exist_ok=True)
    database = Database(url)
    database.create_schema()
    vault = SecretVault()
    service = AuthService(database, on_unlock=vault.unlock)
    token_codec = SourceTokenCodec(secrets.token_bytes(32))
    application = FastAPI(title="movie-pilot-lite")
    application.state.auth_service = service
    application.state.database = database
    application.state.secret_vault = vault
    application.dependency_overrides[auth.get_auth_service] = lambda: service

    def repository() -> ConfigRepository:
        """使用当前登录解锁的密钥构造配置仓库。"""
        return ConfigRepository(database.session_factory, vault.cipher)

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

    @application.get("/api/health")
    def health() -> dict[str, str]:
        """返回不依赖外部服务的进程健康状态。"""
        return {"status": "ok"}

    application.include_router(auth.router)
    application.include_router(search.router)
    application.include_router(downloads.router)
    application.include_router(settings.router)
    return application


app = create_app()
