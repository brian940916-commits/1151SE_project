import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import connect
from .security import hash_password, token_hash

bearer = HTTPBearer(auto_error=False)
public_fields = "user_id, username, role, approval_status"
dummy_hash = hash_password(secrets.token_urlsafe(32))


def current_user(auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if auth:
        with connect() as db:
            user = db.execute(
                "SELECT u.user_id, username, role, approval_status FROM users u "
                "JOIN auth_sessions s USING (user_id) WHERE token_hash=%s "
                "AND expires_at > now() AND approval_status='approved'",
                (token_hash(auth.credentials),),
            ).fetchone()
            if user:
                return user
    raise HTTPException(401, "請先登入或重新登入")


def admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "需要管理員權限")
    return user
