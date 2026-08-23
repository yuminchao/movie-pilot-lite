from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.auth.session import SESSION_COOKIE, AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


class PasswordRequest(BaseModel):
    """管理员密码请求。"""

    password: str = Field(min_length=1, max_length=256)


def get_auth_service() -> AuthService:
    """返回由应用状态提供的认证服务。"""
    raise RuntimeError("认证服务尚未绑定")


def require_session(
    session_id: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    service: AuthService = Depends(get_auth_service),
) -> str:
    """验证管理员会话，否则返回 401。"""
    if not service.is_valid(session_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证失败")
    return session_id or ""


@router.get("/status")
def auth_status(service: AuthService = Depends(get_auth_service)) -> dict[str, bool]:
    """返回是否需要首次初始化。"""
    return {"setup_required": not service.has_admin()}


@router.post("/setup", status_code=status.HTTP_201_CREATED)
def setup(request: PasswordRequest, service: AuthService = Depends(get_auth_service)) -> None:
    """创建首次管理员账户。"""
    try:
        service.setup(request.password)
    except RuntimeError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="管理员已经初始化") from error


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(request: PasswordRequest, response: Response, service: AuthService = Depends(get_auth_service)) -> None:
    """验证密码并设置 HttpOnly 会话 Cookie。"""
    session_id = service.login(request.password)
    if session_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证失败")
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=12 * 60 * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session_id: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    service: AuthService = Depends(get_auth_service),
) -> None:
    """使当前会话失效并清理 Cookie。"""
    service.logout(session_id)
    response.delete_cookie(SESSION_COOKIE)

