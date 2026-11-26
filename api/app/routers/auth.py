import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from pydantic import ValidationError

from .. import accounts
from ..auth import admin, current_user, optional_user, revoke, session_token
from ..pages import cookie_options, page, redirect, verify_form

router = APIRouter()
api = APIRouter(prefix="/api")
web = APIRouter(include_in_schema=False)

api.post("/auth/register", status_code=201)(accounts.register)
api.post("/auth/login")(accounts.login)
api.get("/admin/pending", dependencies=[Depends(admin)])(accounts.pending)
api.post("/admin/users/{user_id}/review", dependencies=[Depends(admin)])(accounts.review)


@api.get("/auth/me")
def me(user=Depends(current_user)):
    return user


@api.post("/auth/logout", status_code=204)
def api_logout(request: Request, token=Depends(session_token)):
    revoke(token)
    response = Response(status_code=204)
    if token and token == request.cookies.get("access_token"):
        response.delete_cookie("access_token")
    return response


@web.get("/auth/register")
def register_page(request: Request, user=Depends(optional_user)):
    return page(request, "auth/register.html", user=user)


@web.post("/auth/register", dependencies=[Depends(verify_form)])
def register_form(request: Request, username: Annotated[str, Form()] = "",
                  password: Annotated[str, Form()] = "", confirm_password: Annotated[str, Form()] = "",
                  role: Annotated[str, Form()] = "",
                  user=Depends(optional_user)):
    try:
        if not confirm_password:
            raise HTTPException(422, "請再次輸入密碼。")
        if password != confirm_password:
            raise HTTPException(422, "兩次輸入的密碼不一致，請重新輸入。")
        account = accounts.register(accounts.Registration(username=username, password=password, role=role))
    except (ValidationError, HTTPException) as exc:
        error = exc.detail if isinstance(exc, HTTPException) else "請確認帳號、密碼長度與申請身分。"
        status = exc.status_code if isinstance(exc, HTTPException) else 422
        return page(request, "auth/register.html", user=user, error=error, status=status,
                    username=username, role=role)
    notice = "registered" if account["approval_status"] == "approved" else "pending"
    return redirect(f"/auth/login?notice={notice}")


@web.get("/auth/login")
def login_page(request: Request, user=Depends(optional_user)):
    return page(request, "auth/login.html", user=user)


@web.post("/auth/login", dependencies=[Depends(verify_form)])
def login_form(request: Request, username: Annotated[str, Form()] = "",
               password: Annotated[str, Form()] = "", user=Depends(optional_user)):
    try:
        result = accounts.login(accounts.Credentials(username=username, password=password))
    except (ValidationError, HTTPException) as exc:
        error = exc.detail if isinstance(exc, HTTPException) else "請確認帳號格式及密碼長度。"
        status = exc.status_code if isinstance(exc, HTTPException) else 422
        return page(request, "auth/login.html", user=user, error=error, status=status, username=username)
    revoke(request.cookies.get("access_token"))
    response = redirect("/spaces?notice=login")
    options = cookie_options(request)
    response.set_cookie("access_token", result["access_token"], max_age=28800, **options)
    response.set_cookie("csrf_token", secrets.token_urlsafe(32), **options)
    return response


@web.post("/auth/logout", dependencies=[Depends(verify_form)])
def logout_form(request: Request):
    revoke(request.cookies.get("access_token"))
    response = redirect("/auth/login?notice=logout")
    response.delete_cookie("access_token")
    response.delete_cookie("csrf_token")
    return response


@web.get("/admin/users")
def pending_page(request: Request, user=Depends(admin)):
    return page(request, "auth/review.html", user=user, people=accounts.pending())


@web.post("/admin/users/{user_id}/review", dependencies=[Depends(verify_form)])
def review_form(request: Request, user_id: int, decision: Annotated[str, Form()] = "",
                user=Depends(admin)):
    try:
        accounts.review(user_id, accounts.Decision(status=decision))
    except (ValidationError, HTTPException) as exc:
        error = exc.detail if isinstance(exc, HTTPException) else "請選擇核准或退件。"
        status = exc.status_code if isinstance(exc, HTTPException) else 422
        return page(request, "auth/review.html", user=user, people=accounts.pending(),
                    error=error, status=status)
    return redirect("/admin/users?notice=reviewed")


router.include_router(api)
router.include_router(web)
