import secrets
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field, field_validator, model_validator

from .auth import admin, bearer, current_user, dummy_hash, public_fields
from .db import connect
from .routers.bookings import router as bookings_router
from .security import hash_password, matches, token_hash

app = FastAPI(title="1151 SE 共用帳號與空間")
app.include_router(bookings_router)


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


class Decision(BaseModel):
    status: Literal["approved", "rejected"]


@app.post("/api/auth/register", status_code=201)
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


@app.post("/api/auth/login")
def login(data: Credentials):
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
        return {"access_token": token, "token_type": "bearer"}


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return user


@app.post("/api/auth/change-password")
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


@app.post("/api/auth/logout", status_code=204)
def logout(auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if auth:
        with connect() as db:
            db.execute("DELETE FROM auth_sessions WHERE token_hash=%s", (token_hash(auth.credentials),))
    return Response(status_code=204)


@app.get("/api/admin/pending", dependencies=[Depends(admin)])
def pending():
    with connect() as db:
        return db.execute(f"SELECT {public_fields} FROM users WHERE approval_status='pending' ORDER BY user_id").fetchall()


@app.post("/api/admin/users/{user_id}/review", dependencies=[Depends(admin)])
def review(user_id: int, decision: Decision):
    with connect() as db:
        result = db.execute(
            f"UPDATE users SET approval_status=%s WHERE user_id=%s AND approval_status='pending' RETURNING {public_fields}",
            (decision.status, user_id),
        ).fetchone()
        if not result:
            raise HTTPException(409, "申請不存在或已由其他人處理")
        return result


@app.get("/api/rooms")
def rooms():
    with connect() as db:
        return db.execute(
            "SELECT room_id,room_code,name,floor,capacity,is_bookable,is_schedulable FROM rooms "
            "ORDER BY CASE WHEN floor='B1' THEN 0 ELSE floor::integer END,room_code"
        ).fetchall()
