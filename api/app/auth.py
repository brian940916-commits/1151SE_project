import secrets

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import connect
from .security import hash_password, token_hash

bearer = HTTPBearer(auto_error=False)
public_fields = "user_id, username, role, approval_status"
dummy_hash = hash_password(secrets.token_urlsafe(32))


def get_user_from_token(token: str | None) -> dict | None:
    if not token:
        return None
    with connect() as db:
        return db.execute(
            "SELECT u.user_id, username, role, approval_status FROM users u "
            "JOIN auth_sessions s USING (user_id) WHERE token_hash=%s "
            "AND expires_at > now() AND approval_status='approved'",
            (token_hash(token),),
        ).fetchone()


def current_user(
    request: Request = None,
    auth: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    token = None
    if isinstance(request, HTTPAuthorizationCredentials):
        token = request.credentials
    elif auth is not None:
        token = auth.credentials
    elif isinstance(request, Request) and "access_token" in request.cookies:
        token = request.cookies["access_token"]

    if not token:
        raise HTTPException(status_code=401, detail="請先登入系統")

    user = get_user_from_token(token)
    if user:
        return user
    raise HTTPException(status_code=401, detail="請先登入或重新登入")


def optional_user(
    request: Request = None,
    auth: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    token = None
    if isinstance(request, HTTPAuthorizationCredentials):
        token = request.credentials
    elif auth is not None:
        token = auth.credentials
    elif isinstance(request, Request) and "access_token" in request.cookies:
        token = request.cookies["access_token"]

    if not token:
        return None
    return get_user_from_token(token)


def admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理員權限")
    return user


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=28800,
    )


def delete_auth_cookie(response: Response) -> None:
    response.delete_cookie(key="access_token")

