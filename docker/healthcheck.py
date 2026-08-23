"""容器内健康检查。"""

import json
from urllib.request import urlopen


def main() -> None:
    """验证 HTTP 健康端点返回预期状态。"""
    with urlopen("http://127.0.0.1:8000/api/health", timeout=3) as response:
        payload = json.load(response)
    if payload != {"status": "ok"}:
        raise SystemExit(1)
    print("ok")


if __name__ == "__main__":
    main()

