from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.api.auth import require_session
from app.services.downloads import DownloadService
from app.services.tokens import InvalidSourceToken

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


class AddDownloadRequest(BaseModel):
    """下载任务提交参数。"""

    source_token: str = Field(min_length=1, max_length=4096)
    category: str = Field(min_length=1, max_length=100)
    save_path: str = Field(min_length=1, max_length=1000)
    start: bool = True


def get_download_service() -> DownloadService:
    """返回当前已解锁的下载服务。"""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="下载服务尚未配置",
    )


@router.post("")
def add_download(
    request: AddDownloadRequest,
    response: Response,
    _: str = Depends(require_session),
    service: DownloadService = Depends(get_download_service),
) -> dict:
    """将搜索结果幂等提交到 qBittorrent。"""
    try:
        record, created = service.add(
            request.source_token,
            request.category,
            request.save_path,
            request.start,
        )
    except (ValueError, InvalidSourceToken) as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return record


@router.get("")
def list_downloads(
    _: str = Depends(require_session),
    service: DownloadService = Depends(get_download_service),
) -> dict:
    """返回 qBittorrent 任务的只读状态。"""
    return service.list()
