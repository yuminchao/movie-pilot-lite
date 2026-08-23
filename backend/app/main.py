from fastapi import FastAPI

app = FastAPI(title="movie-pilot-lite")


@app.get("/api/health")
def health() -> dict[str, str]:
    """返回不依赖外部服务的进程健康状态。"""
    return {"status": "ok"}
