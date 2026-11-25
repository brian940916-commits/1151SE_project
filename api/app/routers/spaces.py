import urllib.parse
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..auth import admin, optional_user, public_fields
from ..db import connect
from ..templates import render_template

router = APIRouter(tags=["spaces"])


class Decision(BaseModel):
    status: Literal["approved", "rejected"]


# =========================================================================
# REST API Endpoints
# =========================================================================


@router.get("/api/rooms")
def rooms():
    with connect() as db:
        return db.execute(
            "SELECT room_id,room_code,name,floor,capacity,is_bookable,is_schedulable FROM rooms "
            "ORDER BY CASE WHEN floor='B1' THEN 0 ELSE floor::integer END,room_code"
        ).fetchall()


@router.get("/api/admin/pending", dependencies=[Depends(admin)])
def pending():
    with connect() as db:
        return db.execute(
            f"SELECT {public_fields} FROM users WHERE approval_status='pending' ORDER BY user_id"
        ).fetchall()


@router.post("/api/admin/users/{user_id}/review", dependencies=[Depends(admin)])
def review(user_id: int, decision: Decision):
    with connect() as db:
        result = db.execute(
            f"UPDATE users SET approval_status=%s WHERE user_id=%s AND approval_status='pending' RETURNING {public_fields}",
            (decision.status, user_id),
        ).fetchone()
        if not result:
            raise HTTPException(409, "申請不存在或已由其他人處理")
        return result


# =========================================================================
# SSR Web Endpoints
# =========================================================================


@router.get("/")
def home():
    return RedirectResponse(url="/spaces", status_code=303)


@router.get("/spaces")
def spaces_page(request: Request, user=Depends(optional_user)):
    with connect() as db:
        all_rooms = db.execute(
            "SELECT room_id,room_code,name,floor,capacity,is_bookable,is_schedulable FROM rooms "
            "ORDER BY CASE WHEN floor='B1' THEN 0 ELSE floor::integer END,room_code"
        ).fetchall()

    message = request.query_params.get("message")
    error = request.query_params.get("error")
    return render_template(
        request,
        "spaces/rooms.html",
        {
            "user": user,
            "rooms": all_rooms,
            "message": message,
            "error": error,
        },
    )


@router.get("/admin/users")
def admin_users_page(request: Request, user=Depends(optional_user)):
    if not user:
        return RedirectResponse(
            url=f"/auth/login?error={urllib.parse.quote('請先登入系統')}",
            status_code=303,
        )
    if user["role"] != "admin":
        return render_template(
            request,
            "spaces/admin_users.html",
            {
                "user": user,
                "pending_users": [],
                "error": "需要管理員權限",
            },
            status_code=403,
        )

    with connect() as db:
        pending_list = db.execute(
            f"SELECT {public_fields} FROM users WHERE approval_status='pending' ORDER BY user_id"
        ).fetchall()

    message = request.query_params.get("message")
    error = request.query_params.get("error")
    return render_template(
        request,
        "spaces/admin_users.html",
        {
            "user": user,
            "pending_users": pending_list,
            "message": message,
            "error": error,
        },
    )


@router.post("/admin/users/{user_id}/review")
def admin_users_review(
    request: Request,
    user_id: int,
    decision: str = Form(...),
    user=Depends(optional_user),
):
    if not user or user["role"] != "admin":
        return RedirectResponse(
            url=f"/auth/login?error={urllib.parse.quote('需要管理員權限')}",
            status_code=303,
        )
    if decision not in ("approved", "rejected"):
        decision = "approved"

    with connect() as db:
        result = db.execute(
            f"UPDATE users SET approval_status=%s WHERE user_id=%s AND approval_status='pending' RETURNING {public_fields}",
            (decision, user_id),
        ).fetchone()

    msg = "已核准帳號申請" if decision == "approved" else "已退件帳號申請"
    if not result:
        msg = "申請不存在或已由其他人處理"

    return RedirectResponse(
        url=f"/admin/users?message={urllib.parse.quote(msg)}",
        status_code=303,
    )
