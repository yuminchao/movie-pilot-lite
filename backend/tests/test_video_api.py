import json

import pytest

GRAB = "http://video-grab.test:8095"


@pytest.fixture(autouse=True)
def video_env(monkeypatch) -> None:
    monkeypatch.setenv("VIDEO_GRAB_URL", GRAB)
    monkeypatch.setenv("VIDEO_GRAB_TOKEN", "grab-secret")


def _login(client) -> None:
    client.post("/mpl/api/auth/setup", json={"password": "correct horse battery"})
    response = client.post("/mpl/api/auth/login", json={"password": "correct horse battery"})
    assert response.status_code == 204


def test_video_requires_session(client) -> None:
    assert client.get("/mpl/api/video/tasks").status_code == 401


def test_video_tasks_are_relayed_with_token(client, httpx_mock) -> None:
    _login(client)
    httpx_mock.add_response(method="GET", url=f"{GRAB}/api/tasks", json=[{"id": "abc", "status": "done"}])
    httpx_mock.add_response(method="POST", url=f"{GRAB}/api/tasks", json=[{"id": "new"}])

    assert client.get("/mpl/api/video/tasks").json() == [{"id": "abc", "status": "done"}]
    assert client.post("/mpl/api/video/tasks", json={"urls": ["https://v.test/1"]}).json() == [{"id": "new"}]

    requests = httpx_mock.get_requests()
    assert all(request.headers["X-Grab-Token"] == "grab-secret" for request in requests)
    assert json.loads(requests[1].content) == {"urls": ["https://v.test/1"]}


def test_video_error_message_is_passed_through(client, httpx_mock) -> None:
    _login(client)
    httpx_mock.add_response(method="POST", url=f"{GRAB}/api/tasks/abc/retry", status_code=400, json={"message": "任务还在进行中"})

    response = client.post("/mpl/api/video/tasks/abc/retry")

    assert response.status_code == 400
    assert response.json() == {"detail": "任务还在进行中"}


def test_video_delete_forwards_delete_file_flag(client, httpx_mock) -> None:
    _login(client)
    httpx_mock.add_response(method="DELETE", url=f"{GRAB}/api/tasks/abc?deleteFile=1", json={"ok": True})

    assert client.delete("/mpl/api/video/tasks/abc", params={"deleteFile": "1"}).json() == {"ok": True}


def test_video_rejects_invalid_task_id(client) -> None:
    _login(client)

    assert client.post("/mpl/api/video/tasks/ABC..x/retry").status_code == 422
    assert client.post("/mpl/api/video/tasks/abc/explode").status_code == 422


def test_video_file_streams_with_range(client, httpx_mock) -> None:
    _login(client)
    httpx_mock.add_response(
        method="GET",
        url=f"{GRAB}/api/tasks/abc/file?inline=1",
        status_code=206,
        content=b"0123",
        headers={"Content-Type": "video/mp4", "Content-Range": "bytes 0-3/10", "Accept-Ranges": "bytes"},
    )

    response = client.get("/mpl/api/video/tasks/abc/file", params={"inline": "true"}, headers={"Range": "bytes=0-3"})

    assert response.status_code == 206
    assert response.content == b"0123"
    assert response.headers["content-range"] == "bytes 0-3/10"
    assert httpx_mock.get_request().headers["Range"] == "bytes=0-3"


def test_video_unconfigured_token_returns_503(client, monkeypatch) -> None:
    _login(client)
    monkeypatch.setenv("VIDEO_GRAB_TOKEN", "")

    response = client.get("/mpl/api/video/tasks")

    assert response.status_code == 503
    assert response.json() == {"detail": "视频下载服务未配置"}
