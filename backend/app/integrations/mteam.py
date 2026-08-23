from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx

_MOVIE_CATEGORIES = ["401", "419", "420", "421", "439", "405", "404"]
_TV_CATEGORIES = ["403", "402", "435", "438", "404", "405"]
_MUSIC_CATEGORIES = ["434", "406"]


class IntegrationError(RuntimeError):
    """第三方服务调用失败。"""


@dataclass(frozen=True, slots=True)
class SearchResult:
    """统一的站点搜索结果。"""

    source_id: str
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


class MTeamClient:
    """访问 M-Team API 的同步客户端。"""

    def __init__(
        self,
        base_url: str,
        headers: dict[str, str] | None = None,
        cookie: str | None = None,
        user_agent: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._site_url = base_url.rstrip("/")
        self._api_url = self._build_api_url(self._site_url)
        self._headers = {str(key): str(value) for key, value in (headers or {}).items()}
        if cookie:
            self._headers["Cookie"] = cookie
        if user_agent:
            self._headers["User-Agent"] = user_agent
        self._timeout = timeout

    def search(self, keyword: str, category: str, page: int) -> list[SearchResult]:
        """按关键字和垂类搜索 M-Team 资源。"""
        categories = self._categories_for(category)
        payload = {
            "keyword": keyword,
            "categories": categories,
            "pageNumber": page,
            "pageSize": 100,
            "visible": 1,
        }
        try:
            response = httpx.post(
                f"{self._api_url}/api/torrent/search",
                headers=self._headers,
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            raw_results = response.json().get("data", {}).get("data", [])
            if not isinstance(raw_results, list):
                raise IntegrationError("M-Team 搜索响应格式无效")
            return [self._parse_result(item) for item in raw_results if isinstance(item, dict)]
        except IntegrationError:
            raise
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise IntegrationError("M-Team 搜索失败") from error

    def get_download_url(self, source_id: str) -> str:
        """生成供 qBittorrent 使用的 M-Team 临时下载描述。"""
        return f"{self._api_url}/api/torrent/genDlToken?id={source_id}"

    def _parse_result(self, item: dict) -> SearchResult:
        status = item.get("status") or {}
        raw_category = str(item.get("category") or "")
        category = self._category_name(raw_category)
        labels = item.get("labelsNew") or []
        if not labels and item.get("labels"):
            labels = str(item["labels"]).split()
        discount = status.get("discount")
        return SearchResult(
            source_id=str(item.get("id") or ""),
            title=str(item.get("name") or ""),
            description=str(item.get("smallDescr") or ""),
            category=category,
            size=int(item.get("size") or 0),
            seeders=int(status.get("seeders") or 0),
            leechers=int(status.get("leechers") or 0),
            downloads=int(status.get("timesCompleted") or 0),
            download_factor=self._download_factor(discount),
            upload_factor=self._upload_factor(discount),
            created_at=item.get("createdDate"),
            page_url=f"{self._site_url}/detail/{item.get('id')}",
            labels=tuple(str(label) for label in labels),
        )

    @staticmethod
    def _build_api_url(site_url: str) -> str:
        parsed = urlsplit(site_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("M-Team 站点地址必须包含 scheme 和 host")
        host = parsed.netloc
        if not host.startswith("api."):
            host = f"api.{host}"
        return urlunsplit((parsed.scheme, host, "", "", ""))

    @staticmethod
    def _categories_for(category: str) -> list[str]:
        return {
            "movie": _MOVIE_CATEGORIES,
            "tv": _TV_CATEGORIES,
            "music": _MUSIC_CATEGORIES,
            "all": [],
        }.get(category, [])

    @staticmethod
    def _category_name(category: str) -> str:
        if category in _MUSIC_CATEGORIES:
            return "music"
        if category in _TV_CATEGORIES and category not in _MOVIE_CATEGORIES:
            return "tv"
        if category in _MOVIE_CATEGORIES:
            return "movie"
        return "all"

    @staticmethod
    def _download_factor(discount: str | None) -> float:
        return {
            "FREE": 0,
            "PERCENT_50": 0.5,
            "PERCENT_70": 0.3,
            "_2X_FREE": 0,
            "_2X_PERCENT_50": 0.5,
        }.get(discount or "", 1)

    @staticmethod
    def _upload_factor(discount: str | None) -> float:
        return 2.0 if discount in {"_2X", "_2X_FREE", "_2X_PERCENT_50"} else 1.0

