"""Shared identity dependencies; existing Bearer API stays compatible."""
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import connect
from .security import token_hash

bearer = HTTPBearer(auto_error=False)


def access_token(request: Request, auth: HTTPAuthorizationCredentials | None):
    if 'authorization' in request.headers:
        return auth.credentials if auth else None
    return request.cookies.get('access_token')


def current_user(request: Request, auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
    token = access_token(request, auth)
    if token:
        with connect() as db:
            user = db.execute(
                'SELECT u.user_id, username, role, approval_status FROM users u '
                'JOIN auth_sessions s USING (user_id) WHERE token_hash=%s '
                "AND expires_at > now() AND approval_status='approved'",
                (token_hash(token),),
            ).fetchone()
            if user:
                return user
    raise HTTPException(401, '請先登入或重新登入')


def admin(user=Depends(current_user)):
    if user['role'] != 'admin':
        raise HTTPException(403, '需要管理員權限')
    return user
