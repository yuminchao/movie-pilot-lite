from collections.abc import Iterator
from typing import Any

import httpx

# 视频文件转发时透传给浏览器的响应头（支持拖动进度条与附件文件名）
FILE_HEADERS = (
    "Content-Type",
    "Content-Length",
    "Content-Range",
    "Accept-Ranges",
    "Content-Disposition",
)


class VideoGrabError(RuntimeError):
    """video-grab 服务返回错误或不可达。"""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class VideoGrabFile:
    """一次视频文件下载的流式响应。"""

    def __init__(self, client: httpx.Client, response: httpx.Response) -> None:
        self._client = client
        self._response = response
        self.status_code = response.status_code
        self.headers = {name: response.headers[name] for name in FILE_HEADERS if name in response.headers}

    def iter_bytes(self) -> Iterator[bytes]:
        """逐块读取文件内容，读完或中断后释放连接。

        Returns:
            文件内容分块迭代器。
        """
        try:
            yield from self._response.iter_bytes(64 * 1024)
        finally:
            self._response.close()
            self._client.close()


class VideoGrabClient:
    """调用 video-grab 抓视频服务（无头浏览器打开网页、抓流存成视频）。"""

    def __init__(self, base_url: str, token: str, timeout: float = 15.0) -> None:
        """初始化客户端。

        Args:
            base_url: 服务地址，如 http://video-grab:8095。
            token: 共享令牌，随请求放在 X-Grab-Token 头。
            timeout: 普通接口的超时秒数。
        """
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-Grab-Token": token}
        self._timeout = timeout

    def request_json(self, method: str, path: str, body: Any = None) -> Any:
        """调用 JSON 接口并返回解析后的响应。

        Args:
            method: HTTP 方法。
            path: 以 /api/ 开头的接口路径（可含查询串）。
            body: 请求体；为 None 时不发送。

        Returns:
            服务返回的 JSON 数据。

        Raises:
            VideoGrabError: 服务不可达，或返回非 2xx 状态。
        """
        try:
            response = httpx.request(
                method,
                f"{self._base_url}{path}",
                headers=self._headers,
                json=body,
                timeout=self._timeout,
            )
        except httpx.HTTPError as error:
            raise VideoGrabError(502, "视频下载服务不可用") from error
        if response.status_code >= 400:
            raise VideoGrabError(response.status_code, self._error_message(response))
        try:
            return response.json()
        except ValueError as error:
            raise VideoGrabError(502, "视频下载服务响应格式无效") from error

    def open_file(self, path: str, range_header: str | None) -> VideoGrabFile:
        """以流式方式打开视频文件，透传 Range 以支持拖动进度条。

        Args:
            path: 文件接口路径。
            range_header: 浏览器请求的 Range 头。

        Returns:
            待读取的文件流；调用方必须读完 iter_bytes 以释放连接。

        Raises:
            VideoGrabError: 服务不可达，或返回非 2xx 状态。
        """
        headers = dict(self._headers)
        if range_header:
            headers["Range"] = range_header
        client = httpx.Client(timeout=httpx.Timeout(self._timeout, read=None))
        try:
            response = client.send(client.build_request("GET", f"{self._base_url}{path}", headers=headers), stream=True)
        except httpx.HTTPError as error:
            client.close()
            raise VideoGrabError(502, "视频下载服务不可用") from error
        if response.status_code >= 400:
            response.read()
            message = self._error_message(response)
            response.close()
            client.close()
            raise VideoGrabError(response.status_code, message)
        return VideoGrabFile(client, response)

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            message = response.json().get("message")
        except (ValueError, AttributeError):
            message = None
        return str(message) if message else f"视频下载服务返回 {response.status_code}"
