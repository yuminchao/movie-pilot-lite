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
    poster_url: str | None = None


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

    def test_connection(self) -> None:
        """调用用户资料接口验证站点凭据。"""
        try:
            response = httpx.post(
                f"{self._api_url}/api/member/profile",
                headers=self._headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            if not response.json().get("data"):
                raise IntegrationError("M-Team 认证无效")
        except IntegrationError:
            raise
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise IntegrationError("M-Team 连接失败") from error

    def check_in(self) -> None:
        """调用 M-Team 问候接口完成签到。

        Raises:
            IntegrationError: 网络、响应格式或业务状态表示签到失败。
        """
        try:
            response = httpx.post(
                f"{self._api_url}/api/system/hello",
                headers=self._headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or str(payload.get("code")) not in {
                "0",
                "200",
            }:
                raise ValueError("签到响应无效")
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise IntegrationError("M-Team 签到失败") from error

    def get_download_url(self, source_id: str) -> str:
        """调用 M-Team 接口生成供 qBittorrent 使用的临时下载地址。"""
        try:
            response = httpx.post(
                f"{self._api_url}/api/torrent/genDlToken",
                headers=self._headers,
                params={"id": source_id},
                timeout=self._timeout,
            )
            response.raise_for_status()
            url = response.json().get("data")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                raise IntegrationError("M-Team 未返回有效下载地址")
            return url
        except IntegrationError:
            raise
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise IntegrationError("M-Team 下载地址生成失败") from error

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
            poster_url=self._poster_url(item.get("imageList")),
        )

    @staticmethod
    def _poster_url(image_list: object) -> str | None:
        """从图片列表中选择第一个有效的 HTTPS 地址。

        Args:
            image_list: M-Team 返回的图片列表。

        Returns:
            第一个有效的 HTTPS 地址；没有时返回 None。
        """
        if not isinstance(image_list, list):
            return None
        for image in image_list:
            if not isinstance(image, str):
                continue
            try:
                parsed = urlsplit(image)
            except ValueError:
                continue
            if parsed.scheme == "https" and parsed.hostname:
                return image
        return None

    @staticmethod
    def _build_api_url(site_url: str) -> str:
        parsed = urlsplit(site_url)
        if not parsed.scheme or not parsed.hostname:
            raise ValueError("M-Team 站点地址必须包含 scheme 和 host")
        host = parsed.hostname.lower()
        for official_domain in ("m-team.cc", "m-team.io"):
            if host == official_domain or host.endswith(f".{official_domain}"):
                host = official_domain
                break
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
