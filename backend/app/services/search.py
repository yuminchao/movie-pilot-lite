from collections.abc import Callable
from dataclasses import asdict, dataclass

from app.integrations.mteam import MTeamClient, SearchResult


@dataclass(frozen=True, slots=True)
class SearchItem:
    """提供给前端的规范化搜索项。"""

    source_token: str
    title: str
    description: str
    category: str
    size: int
    seeders: int
    leechers: int
    downloads: int
    download_factor: float
    upload_factor: float
    created_at: str | None
    page_url: str
    labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchPage:
    """带页码信息的搜索响应。"""

    items: tuple[SearchItem, ...]
    page: int
    has_more: bool

    @classmethod
    def from_results(
        cls,
        results: list[SearchResult],
        page: int,
        token_factory: Callable[[SearchResult], str],
    ) -> "SearchPage":
        """将站点结果投影为不包含凭据的 API 页面。"""
        items = tuple(
            SearchItem(
                source_token=token_factory(result),
                title=result.title,
                description=result.description,
                category=result.category,
                size=result.size,
                seeders=result.seeders,
                leechers=result.leechers,
                downloads=result.downloads,
                download_factor=result.download_factor,
                upload_factor=result.upload_factor,
                created_at=result.created_at,
                page_url=result.page_url,
                labels=result.labels,
            )
            for result in results
        )
        return cls(items=items, page=page, has_more=len(results) >= 100)

    def to_dict(self) -> dict:
        """转换为 FastAPI 可序列化结构。"""
        return {
            "items": [asdict(item) for item in self.items],
            "page": self.page,
            "has_more": self.has_more,
        }


class SearchService:
    """协调 M-Team 查询、排序和下载标识签发。"""

    def __init__(
        self,
        client: MTeamClient,
        token_factory: Callable[[SearchResult], str],
    ) -> None:
        self._client = client
        self._token_factory = token_factory

    def search(self, keyword: str, category: str, page: int, sort: str) -> SearchPage:
        """查询并按用户选择的规则排序结果。"""
        results = self._client.search(keyword, category, page)
        if sort == "seeders":
            results.sort(key=lambda item: item.seeders, reverse=True)
        elif sort == "newest":
            results.sort(key=lambda item: item.created_at or "", reverse=True)
        else:
            results.sort(key=lambda item: (item.download_factor, -item.seeders))
        return SearchPage.from_results(results, page, self._token_factory)

