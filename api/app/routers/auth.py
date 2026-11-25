import secrets
import urllib.parse
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field, field_validator, model_validator

from ..auth import (
    bearer,
    current_user,
    delete_auth_cookie,
    dummy_hash,
    optional_user,
    public_fields,
    set_auth_cookie,
)
from ..db import connect
from ..security import hash_password, matches, token_hash
from ..templates import render_template

router = APIRouter(tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,40}$")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize(cls, value):
        return value.lower()


class Registration(Credentials):
    role: Literal["student", "teacher"] = "student"
    confirm_password: str | None = None

    @model_validator(mode="after")
    def validate_passwords(self):
        if self.confirm_password is not None and self.confirm_password != self.password:
            raise ValueError("密碼與確認密碼不相符")
        return self


class ChangePassword(BaseModel):
    old_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_change(self):
        if self.new_password != self.confirm_password:
            raise ValueError("新密碼與確認新密碼不一致")
        if self.old_password == self.new_password:
            raise ValueError("新密碼不可與目前密碼相同")
        return self


# =========================================================================
# REST API Endpoints
# =========================================================================


@router.post("/api/auth/register", status_code=201)
def register(data: Registration):
    status = "approved" if data.role == "student" else "pending"
    try:
        with connect() as db:
            return db.execute(
                "INSERT INTO users (username,password_hash,role,approval_status) "
                f"VALUES (%s,%s,%s,%s) RETURNING {public_fields}",
                (data.username, hash_password(data.password), data.role, status),
            ).fetchone()
    except UniqueViolation:
        raise HTTPException(409, "帳號已被使用") from None


@router.post("/api/auth/login")
def login(data: Credentials, response: Response = None):
    with connect() as db:
        user = db.execute("SELECT * FROM users WHERE username=%s", (data.username,)).fetchone()
        valid = matches(data.password, user["password_hash"] if user else dummy_hash)
        if not user or not valid:
            raise HTTPException(401, "帳號或密碼錯誤")
        if user["approval_status"] != "approved":
            message = "帳號等待審核" if user["approval_status"] == "pending" else "帳號申請已退件"
            raise HTTPException(403, message)
        token = secrets.token_urlsafe(32)
        db.execute("DELETE FROM auth_sessions WHERE expires_at <= now()")
        db.execute(
            "INSERT INTO auth_sessions VALUES (%s,%s,now()+interval '8 hours')",
            (token_hash(token), user["user_id"]),
        )
        if response is not None:
            set_auth_cookie(response, token)
        return {"access_token": token, "token_type": "bearer"}


@router.get("/api/auth/me")
def me(user=Depends(current_user)):
    return user


@router.post("/api/auth/change-password")
def change_password(data: ChangePassword, user=Depends(current_user)):
    with connect() as db:
        user_row = db.execute("SELECT password_hash FROM users WHERE user_id=%s", (user["user_id"],)).fetchone()
        if not user_row or not matches(data.old_password, user_row["password_hash"]):
            raise HTTPException(400, "目前密碼不正確，請重新輸入")
        db.execute(
            "UPDATE users SET password_hash=%s WHERE user_id=%s",
            (hash_password(data.new_password), user["user_id"]),
        )
        return {"message": "密碼已成功修改"}


@router.post("/api/auth/logout", status_code=204)
def logout(
    request: Request = None,
    response: Response = None,
    auth: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    token = None
    if auth:
        token = auth.credentials
    elif request and "access_token" in request.cookies:
        token = request.cookies["access_token"]

    if token:
        with connect() as db:
            db.execute("DELETE FROM auth_sessions WHERE token_hash=%s", (token_hash(token),))
    if response is not None:
        delete_auth_cookie(response)
        return response
    return Response(status_code=204)


# =========================================================================
# SSR Web Endpoints
# =========================================================================


@router.get("/auth/login")
def login_page(request: Request, user=Depends(optional_user)):
    if user:
        return RedirectResponse(url="/spaces", status_code=303)
    message = request.query_params.get("message")
    error = request.query_params.get("error")
    return render_template(
        request,
        "auth/login.html",
        {"user": None, "message": message, "error": error},
    )


@router.post("/auth/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    clean_username = username.strip().lower()
    try:
        with connect() as db:
            user = db.execute("SELECT * FROM users WHERE username=%s", (clean_username,)).fetchone()
            valid = matches(password, user["password_hash"] if user else dummy_hash)
            if not user or not valid:
                return render_template(
                    request,
                    "auth/login.html",
                    {"user": None, "error": "帳號或密碼錯誤"},
                    status_code=400,
                )
            if user["approval_status"] != "approved":
                msg = "帳號等待審核中，核准後方可登入" if user["approval_status"] == "pending" else "帳號申請已退件"
                return render_template(
                    request,
                    "auth/login.html",
                    {"user": None, "error": msg},
                    status_code=403,
                )
            token = secrets.token_urlsafe(32)
            db.execute("DELETE FROM auth_sessions WHERE expires_at <= now()")
            db.execute(
                "INSERT INTO auth_sessions VALUES (%s,%s,now()+interval '8 hours')",
                (token_hash(token), user["user_id"]),
            )
            resp = RedirectResponse(
                url=f"/spaces?message={urllib.parse.quote('登入成功')}",
                status_code=303,
            )
            set_auth_cookie(resp, token)
            return resp
    except Exception as ex:
        return render_template(
            request,
            "auth/login.html",
            {"user": None, "error": f"登入失敗: {ex}"},
            status_code=400,
        )


@router.get("/auth/register")
def register_page(request: Request, user=Depends(optional_user)):
    if user:
        return RedirectResponse(url="/spaces", status_code=303)
    message = request.query_params.get("message")
    error = request.query_params.get("error")
    return render_template(
        request,
        "auth/register.html",
        {"user": None, "message": message, "error": error},
    )


@router.post("/auth/register")
def register_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    role: str = Form("student"),
):
    if password != confirm_password:
        return render_template(
            request,
            "auth/register.html",
            {"user": None, "error": "兩次輸入的密碼不一致，請重新確認。"},
            status_code=400,
        )
    if len(password) < 8 or len(password) > 128:
        return render_template(
            request,
            "auth/register.html",
            {"user": None, "error": "密碼長度須介於 8 至 128 字元。"},
            status_code=400,
        )
    if role not in ("student", "teacher"):
        role = "student"

    clean_username = username.strip().lower()
    status = "approved" if role == "student" else "pending"
    try:
        with connect() as db:
            db.execute(
                "INSERT INTO users (username, password_hash, role, approval_status) VALUES (%s, %s, %s, %s)",
                (clean_username, hash_password(password), role, status),
            )
        msg = "學生帳號已建立，請登入。" if role == "student" else "老師帳號已送審，核准後即可登入。"
        return RedirectResponse(
            url=f"/auth/login?message={urllib.parse.quote(msg)}",
            status_code=303,
        )
    except UniqueViolation:
        return render_template(
            request,
            "auth/register.html",
            {"user": None, "error": "帳號已被使用，請另選其他帳號名稱。"},
            status_code=409,
        )
    except Exception as ex:
        return render_template(
            request,
            "auth/register.html",
            {"user": None, "error": f"註冊失敗: {ex}"},
            status_code=400,
        )


@router.get("/auth/change-password")
def change_password_page(request: Request, user=Depends(optional_user)):
    if not user:
        return RedirectResponse(
            url=f"/auth/login?error={urllib.parse.quote('請先登入系統')}",
            status_code=303,
        )
    message = request.query_params.get("message")
    error = request.query_params.get("error")
    return render_template(
        request,
        "auth/change_password.html",
        {"user": user, "message": message, "error": error},
    )


@router.post("/auth/change-password")
def change_password_submit(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user=Depends(optional_user),
):
    if not user:
        return RedirectResponse(
            url=f"/auth/login?error={urllib.parse.quote('請先登入系統')}",
            status_code=303,
        )
    if new_password != confirm_password:
        return render_template(
            request,
            "auth/change_password.html",
            {"user": user, "error": "新密碼與確認新密碼不一致，請重新確認。"},
            status_code=400,
        )
    if old_password == new_password:
        return render_template(
            request,
            "auth/change_password.html",
            {"user": user, "error": "新密碼不可與目前密碼相同。"},
            status_code=400,
        )
    if len(new_password) < 8 or len(new_password) > 128:
        return render_template(
            request,
            "auth/change_password.html",
            {"user": user, "error": "新密碼長度須介於 8 至 128 字元。"},
            status_code=400,
        )

    with connect() as db:
        user_row = db.execute("SELECT password_hash FROM users WHERE user_id=%s", (user["user_id"],)).fetchone()
        if not user_row or not matches(old_password, user_row["password_hash"]):
            return render_template(
                request,
                "auth/change_password.html",
                {"user": user, "error": "目前舊密碼不正確，請重新輸入。"},
                status_code=400,
            )
        db.execute(
            "UPDATE users SET password_hash=%s WHERE user_id=%s",
            (hash_password(new_password), user["user_id"]),
        )

    return RedirectResponse(
        url=f"/spaces?message={urllib.parse.quote('密碼已成功修改！')}",
        status_code=303,
    )


@router.post("/auth/logout")
def logout_submit(request: Request, response: Response):
    token = request.cookies.get("access_token")
    if token:
        with connect() as db:
            db.execute("DELETE FROM auth_sessions WHERE token_hash=%s", (token_hash(token),))
    resp = RedirectResponse(
        url=f"/spaces?message={urllib.parse.quote('已登出')}",
        status_code=303,
    )
    delete_auth_cookie(resp)
    return resp
