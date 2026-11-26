import secrets
from typing import Annotated

from fastapi import Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .auth import check_csrf
from .db import ROOT

templates = Jinja2Templates(directory=ROOT / "templates")
notices = {
    "registered": "學生帳號已建立，請登入。",
    "pending": "老師帳號已送審，核准後即可登入。",
    "login": "登入成功。",
    "logout": "已登出。",
    "reviewed": "已處理申請。",
    "photo-updated": "已更新照片。",
    "room-updated": "已儲存教室資料。",
    "photo-removed": "已移除照片。",
}


def verify_form(request: Request, csrf: Annotated[str, Form()] = ""):
    check_csrf(request, csrf)


def cookie_options(request: Request):
    return {"httponly": True, "samesite": "lax", "secure": request.url.scheme == "https"}


def page(request: Request, template: str, *, user=None, status=200, **context):
    expired = hasattr(request.state, "user") and user is None and "access_token" in request.cookies
    csrf = request.cookies.get("csrf_token") or secrets.token_urlsafe(32)
    response = templates.TemplateResponse(
        request=request, name=template,
        context={
            "user": user, "csrf": csrf,
            "message": "登入已過期，請重新登入。" if expired else notices.get(request.query_params.get("notice")),
            **context,
        },
        status_code=status, headers={"Cache-Control": "no-store"},
    )
    if "csrf_token" not in request.cookies:
        response.set_cookie("csrf_token", csrf, **cookie_options(request))
    if expired:
        response.delete_cookie("access_token")
    return response


def redirect(path: str):
    return RedirectResponse(path, status_code=303, headers={"Cache-Control": "no-store"})
