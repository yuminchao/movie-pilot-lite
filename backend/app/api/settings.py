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
    return service.save_mteam(
        {
            **payload.model_dump(exclude_none=True),
            "base_url": str(payload.base_url).rstrip("/"),
        }
    )


@router.post("/mteam/test")
def test_mteam(
    _: str = Depends(require_session),
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, Any]:
    """验证已保存的 M-Team 连接。"""
    return service.test_mteam()


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
    return service.test_qbittorrent()

