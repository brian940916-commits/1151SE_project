import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import connect
from .security import token_hash

bearer = HTTPBearer(auto_error=False)


def check_csrf(request: Request, submitted: str):
    expected = request.cookies.get("csrf_token", "")
    if not expected or not submitted or not secrets.compare_digest(expected.encode(), submitted.encode()):
        raise HTTPException(403, "表單已失效，請重新整理後再試。")


def session_token(request: Request, auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if auth:
        return auth.credentials
    token = request.cookies.get("access_token")
    if token and request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_csrf(request, request.headers.get("X-CSRF-Token", ""))
    return token


def optional_user(request: Request, token: str | None = Depends(session_token)):
    request.state.user = None
    if token:
        with connect() as db:
            request.state.user = db.execute(
                "SELECT u.user_id, username, role, approval_status FROM users u "
                "JOIN auth_sessions s USING (user_id) WHERE token_hash=%s "
                "AND expires_at > now() AND approval_status='approved'",
                (token_hash(token),),
            ).fetchone()
    return request.state.user


def current_user(user=Depends(optional_user)):
    if user is None:
        raise HTTPException(401, "請先登入或重新登入")
    return user


def admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "需要管理員權限")
    return user


def revoke(token: str | None):
    if token:
        with connect() as db:
            db.execute("DELETE FROM auth_sessions WHERE token_hash=%s", (token_hash(token),))
