from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth import require_session
from app.services.search import SearchService

router = APIRouter(prefix="/api", tags=["search"])


def get_search_service() -> SearchService:
    """返回当前已解锁的搜索服务。"""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="M-Team 配置尚未解锁",
    )


@router.get("/search")
def search(
    q: str = Query(min_length=1, max_length=200),
    category: Literal["all", "movie", "tv", "music"] = "all",
    page: int = Query(default=1, ge=1),
    sort: Literal["promotion", "seeders", "newest"] = "promotion",
    _: str = Depends(require_session),
    service: SearchService = Depends(get_search_service),
) -> dict:
    """查询 M-Team 并返回规范化搜索结果。"""
    return service.search(q.strip(), category, page, sort).to_dict()

