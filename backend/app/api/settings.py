import os
from datetime import time
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import AnyHttpUrl, BaseModel, Field, model_validator

from app.api.auth import require_session
from app.config.repository import ConfigRepository
from app.integrations.mteam import MTeamClient
from app.services.checkin import CheckinService
from app.services.settings import SettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])


class MTeamSettingsRequest(BaseModel):
    """M-Team 连接配置请求。"""

    base_url: AnyHttpUrl
    headers: dict[str, str] = Field(default_factory=dict)
    cookie: str | None = Field(default=None, max_length=16_384)
    user_agent: str | None = Field(default=None, max_length=500)
    timeout: float = Field(default=15, ge=1, le=60)


class MTeamCheckinSettingsRequest(BaseModel):
    """M-Team 每日签到设置请求。"""

    enabled: bool
    execution_time: time


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


class DownloadPathsRequest(BaseModel):
    """按资源类型配置的 qBittorrent 保存路径。"""

    movie: str = Field(min_length=1, max_length=1000)
    tv: str = Field(min_length=1, max_length=1000)
    music: str = Field(min_length=1, max_length=1000)
    other: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_save_paths(self) -> "DownloadPathsRequest":
        """要求所有保存路径均为 Unix 或 Windows 绝对路径。"""
        for save_path in (self.movie, self.tv, self.music, self.other):
            if not (
                PurePosixPath(save_path).is_absolute()
                or PureWindowsPath(save_path).is_absolute()
            ):
                raise ValueError("保存路径必须是绝对路径")
        return self


class DownloadDefaultsRequest(BaseModel):
    """qBittorrent 任务默认参数。"""

    category: str = Field(min_length=1, max_length=100)
    save_paths: DownloadPathsRequest
    start: bool = True


def get_settings_service(request: Request) -> SettingsService:
    """从应用状态组装当前设置服务。

    Args:
        request: 当前 HTTP 请求。

    Returns:
        使用应用数据库和密钥保险库的设置服务。

    Raises:
        HTTPException: 数据库或密钥保险库尚未初始化。
    """
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
    """返回 M-Team 公开配置和敏感字段掩码。

    Args:
        _: 已认证的管理员会话标识。
        service: 当前设置服务。

    Returns:
        M-Team 配置状态与安全回显字段。
    """
    return service.get_mteam()


@router.put("/mteam")
def save_mteam(
    payload: MTeamSettingsRequest,
    request: Request,
    _: str = Depends(require_session),
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, Any]:
    """加密保存 M-Team 连接配置并唤醒签到调度器。

    Args:
        payload: 已校验的完整 M-Team 连接表单。
        request: 当前 HTTP 请求。
        _: 已认证的管理员会话标识。
        service: 当前设置服务。

    Returns:
        保存后的安全配置视图。

    Raises:
        HTTPException: 掩码字段没有可保留的旧值。
    """
    try:
        result = service.save_mteam(
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
    request.app.state.checkin_scheduler.wake()
    return result


def get_checkin_service(request: Request) -> CheckinService:
    """从应用状态组装签到模块。

    Args:
        request: 当前 HTTP 请求。

    Returns:
        使用加密配置仓库和应用时区的签到模块。

    Raises:
        HTTPException: 数据库或密钥保险库尚未初始化。
    """
    try:
        repository = ConfigRepository(
            request.app.state.database.session_factory,
            request.app.state.secret_vault.cipher,
        )
        timezone = ZoneInfo(os.getenv("TZ", "Asia/Shanghai"))
    except AttributeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="签到服务尚未初始化",
        ) from error
    return CheckinService(repository, lambda value: MTeamClient(**value), timezone)


@router.post("/mteam/test")
def test_mteam(
    _: str = Depends(require_session),
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, Any]:
    """验证已保存的 M-Team 连接。

    Args:
        _: 已认证的管理员会话标识。
        service: 当前设置服务。

    Returns:
        连接成功状态和公开消息。

    Raises:
        HTTPException: M-Team 连接尚未配置。
        app.integrations.mteam.IntegrationError: 第三方连接验证失败。
    """
    try:
        return service.test_mteam()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.get("/mteam/checkin")
def get_mteam_checkin(
    _: str = Depends(require_session),
    service: CheckinService = Depends(get_checkin_service),
) -> dict[str, Any]:
    """返回 M-Team 每日签到设置和运行状态。

    Args:
        _: 已认证的管理员会话标识。
        service: 当前签到服务。

    Returns:
        公开签到设置和最近运行状态。
    """
    return service.read_settings()


@router.put("/mteam/checkin")
def save_mteam_checkin(
    payload: MTeamCheckinSettingsRequest,
    request: Request,
    _: str = Depends(require_session),
    service: CheckinService = Depends(get_checkin_service),
) -> dict[str, Any]:
    """保存 M-Team 每日签到设置并在成功后唤醒调度器。

    Args:
        payload: 已校验的签到开关和每日执行时间。
        request: 当前 HTTP 请求。
        _: 已认证的管理员会话标识。
        service: 当前签到服务。

    Returns:
        保存后的公开签到设置和运行状态。
    """
    result = service.save_settings(payload.enabled, payload.execution_time)
    request.app.state.checkin_scheduler.wake()
    return result


@router.get("/qbittorrent")
def get_qbittorrent(
    _: str = Depends(require_session),
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, Any]:
    """返回 qBittorrent 配置掩码状态。

    Args:
        _: 已认证的管理员会话标识。
        service: 当前设置服务。

    Returns:
        不包含凭据明文的配置状态。
    """
    return service.get_qbittorrent()


@router.put("/qbittorrent")
def save_qbittorrent(
    payload: QbittorrentSettingsRequest,
    _: str = Depends(require_session),
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, Any]:
    """加密保存 qBittorrent 连接配置。

    Args:
        payload: 已校验的 qBittorrent 连接配置。
        _: 已认证的管理员会话标识。
        service: 当前设置服务。

    Returns:
        不包含凭据明文的配置状态。
    """
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
    """验证已保存的 qBittorrent 连接。

    Args:
        _: 已认证的管理员会话标识。
        service: 当前设置服务。

    Returns:
        连接成功状态和公开消息。

    Raises:
        HTTPException: qBittorrent 连接尚未配置。
        app.integrations.qbittorrent.QbittorrentError: 第三方连接验证失败。
    """
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
    """返回搜索结果使用的 qBittorrent 默认参数。

    Args:
        _: 已认证的管理员会话标识。
        service: 当前设置服务。

    Returns:
        按资源类型归一化的下载默认值。
    """
    return service.get_download_defaults()


@router.put("/downloads")
def save_download_defaults(
    payload: DownloadDefaultsRequest,
    _: str = Depends(require_session),
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, Any]:
    """保存搜索结果使用的 qBittorrent 默认参数。

    Args:
        payload: 已校验的下载默认值。
        _: 已认证的管理员会话标识。
        service: 当前设置服务。

    Returns:
        保存后的下载默认值。
    """
    return service.save_download_defaults(payload.model_dump())
