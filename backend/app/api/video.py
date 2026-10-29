import os
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.auth import require_session
from app.integrations.video_grab import VideoGrabClient, VideoGrabError

router = APIRouter(prefix="/api/video", tags=["video"])

TaskId = Annotated[str, Path(pattern=r"^[a-z0-9]{1,64}$")]


def get_video_client() -> VideoGrabClient:
    """按环境变量构造 video-grab 客户端。

    Returns:
        指向 VIDEO_GRAB_URL 的客户端。

    Raises:
        HTTPException: 未配置 VIDEO_GRAB_TOKEN。
    """
    token = os.getenv("VIDEO_GRAB_TOKEN", "")
    if not token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="视频下载服务未配置")
    return VideoGrabClient(os.getenv("VIDEO_GRAB_URL", "http://video-grab:8095"), token)


def _call(client: VideoGrabClient, method: str, path: str, body: Any = None) -> Any:
    """转发 JSON 请求，把服务错误转换为带中文说明的 HTTP 错误。

    Raises:
        HTTPException: video-grab 返回错误或不可达。
    """
    try:
        return client.request_json(method, path, body)
    except VideoGrabError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@router.get("/settings")
def get_settings(
    _: str = Depends(require_session),
    client: VideoGrabClient = Depends(get_video_client),
) -> Any:
    """读取视频下载设置。"""
    return _call(client, "GET", "/api/settings")


@router.put("/settings")
def save_settings(
    body: dict[str, Any] = Body(),
    _: str = Depends(require_session),
    client: VideoGrabClient = Depends(get_video_client),
) -> Any:
    """保存视频下载设置。"""
    return _call(client, "PUT", "/api/settings", body)


@router.get("/tasks")
def list_tasks(
    _: str = Depends(require_session),
    client: VideoGrabClient = Depends(get_video_client),
) -> Any:
    """返回全部视频下载任务。"""
    return _call(client, "GET", "/api/tasks")


@router.post("/tasks")
def create_tasks(
    body: dict[str, Any] = Body(),
    _: str = Depends(require_session),
    client: VideoGrabClient = Depends(get_video_client),
) -> Any:
    """按网页地址批量创建下载任务。"""
    return _call(client, "POST", "/api/tasks", body)


@router.post("/tasks/{task_id}/{action}")
def task_action(
    task_id: TaskId,
    action: Literal["retry", "cancel"],
    _: str = Depends(require_session),
    client: VideoGrabClient = Depends(get_video_client),
) -> Any:
    """重试或取消任务。"""
    return _call(client, "POST", f"/api/tasks/{task_id}/{action}")


@router.delete("/tasks/{task_id}")
def delete_task(
    task_id: TaskId,
    delete_file: bool = Query(default=False, alias="deleteFile"),
    _: str = Depends(require_session),
    client: VideoGrabClient = Depends(get_video_client),
) -> Any:
    """删除任务，可选同时删除视频文件。"""
    return _call(client, "DELETE", f"/api/tasks/{task_id}" + ("?deleteFile=1" if delete_file else ""))


@router.get("/tasks/{task_id}/file")
def task_file(
    task_id: TaskId,
    request: Request,
    inline: bool = False,
    _: str = Depends(require_session),
    client: VideoGrabClient = Depends(get_video_client),
) -> StreamingResponse:
    """下载或在线播放视频文件，透传 Range 以支持拖动进度条。

    Raises:
        HTTPException: video-grab 返回错误或不可达。
    """
    path = f"/api/tasks/{task_id}/file" + ("?inline=1" if inline else "")
    try:
        file = client.open_file(path, request.headers.get("range"))
    except VideoGrabError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    return StreamingResponse(file.iter_bytes(), status_code=file.status_code, headers=file.headers)
