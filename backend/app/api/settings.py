from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import AnyHttpUrl, BaseModel, Field, model_validator

from app.api.auth import require_session
from app.services.settings import SettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])


class MTeamSettingsRequest(BaseModel):
    """M-Team 连接配置请求。"""

    base_url: AnyHttpUrl
    headers: dict[str, str] = Field(default_factory=dict)
    cookie: str | None = Field(default=None, max_length=16_384)
    user_agent: str | None = Field(default=None, max_length=500)
    timeout: float = Field(default=15, ge=1, le=60)


class QbittorrentSettingsRequest(BaseModel):
    """qBittorrent 连接配置请求。"""

    base_url: AnyHttpUrl
    username: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_credentials(self) -> "QbittorrentSettingsRequest":
        """要求 API Key 或完整用户名密码。"""
        if self.api_key or (self.username and self.password):
            return self
        raise ValueError("请提供 qBittorrent API Key 或用户名和密码")


class DownloadDefaultsRequest(BaseModel):
    """qBittorrent 任务默认参数。"""

    category: str = Field(min_length=1, max_length=100)
    save_path: str = Field(min_length=1, max_length=1000)
    start: bool = True

    @model_validator(mode="after")
    def validate_save_path(self) -> "DownloadDefaultsRequest":
        """要求保存路径适用于 Unix 或 Windows qBittorrent。"""
        if PurePosixPath(self.save_path).is_absolute() or PureWindowsPath(
            self.save_path
        ).is_absolute():
            return self
        raise ValueError("保存路径必须是绝对路径")


def get_settings_service(request: Request) -> SettingsService:
    """从应用状态组装当前设置服务。"""
    try:
        return SettingsService(request.app.state.database, request.app.state.secret_vault)
    except AttributeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="设置服务尚未初始化",
        ) from error


@router.get("/mteam")
def get_mteam(
    _: str = Depends(require_session),
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, Any]:
    """返回 M-Team 配置掩码状态。"""
    return service.get_mteam()


@router.put("/mteam")
def save_mteam(
    payload: MTeamSettingsRequest,
    _: str = Depends(require_session),
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, Any]:
    """加密保存 M-Team 连接配置。"""
    try:
        return service.save_mteam(
            {
                **payload.model_dump(),
                "base_url": str(payload.base_url).rstrip("/"),
            }
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.post("/mteam/test")
def test_mteam(
    _: str = Depends(require_session),
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, Any]:
    """验证已保存的 M-Team 连接。"""
    try:
        return service.test_mteam()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.get("/qbittorrent")
def get_qbittorrent(
    _: str = Depends(require_session),
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, Any]:
    """返回 qBittorrent 配置掩码状态。"""
    return service.get_qbittorrent()


@router.put("/qbittorrent")
def save_qbittorrent(
    payload: QbittorrentSettingsRequest,
    _: str = Depends(require_session),
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, Any]:
    """加密保存 qBittorrent 连接配置。"""
    return service.save_qbittorrent(
        {
            **payload.model_dump(exclude_none=True),
            "base_url": str(payload.base_url).rstrip("/"),
        }
    )


@router.post("/qbittorrent/test")
def test_qbittorrent(
    _: str = Depends(require_session),
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, Any]:
    """验证已保存的 qBittorrent 连接。"""
    try:
        return service.test_qbittorrent()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.get("/downloads")
def get_download_defaults(
    _: str = Depends(require_session),
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, Any]:
    """返回搜索结果使用的 qBittorrent 默认参数。"""
    return service.get_download_defaults()


@router.put("/downloads")
def save_download_defaults(
    payload: DownloadDefaultsRequest,
    _: str = Depends(require_session),
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, Any]:
    """保存搜索结果使用的 qBittorrent 默认参数。"""
    return service.save_download_defaults(payload.model_dump())
