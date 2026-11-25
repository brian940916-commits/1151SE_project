"""測試純 Python Jinja2 SSR 網頁與 HttpOnly Cookie 認證全生命週期

驗證內容包含：
1. 首頁與教室清單 GET /spaces
2. 學生註冊 POST /auth/register
3. Cookie 登入 POST /auth/login
4. 預約頁面檢視 GET /bookings/calendar（攜帶 Cookie）
5. 填表申請預約 POST /bookings/calendar（攜帶 Cookie）
6. 借用紀錄檢視 GET /bookings/history（攜帶 Cookie）
7. 修改個人密碼 POST /auth/change-password（攜帶 Cookie）
8. 登出並清除 Cookie POST /auth/logout
9. 管理員登入與審核專區 GET /admin/bookings
10. 管理員核准、領用借出與確認歸還（審核生命週期）
"""

import asyncio
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from app.db import connect
from app.main import app
from app.security import hash_password


async def request_asgi(method, path, data=None, cookie=None):
    response_body = []
    status_code = None
    headers = []

    body_bytes = b""
    content_type = b""
    if data is not None:
        body_str = urllib.parse.urlencode(data, doseq=True)
        body_bytes = body_str.encode("utf-8")
        content_type = b"application/x-www-form-urlencoded"

    body_sent = False

    async def receive():
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        nonlocal status_code
        if message["type"] == "http.response.start":
            status_code = message["status"]
            headers.extend(message.get("headers", []))
        elif message["type"] == "http.response.body":
            response_body.append(message.get("body", b""))

    h = []
    if cookie:
        h.append((b"cookie", cookie.encode("utf-8")))
    if content_type:
        h.append((b"content-type", content_type))
        h.append((b"content-length", str(len(body_bytes)).encode("utf-8")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "headers": h,
        "query_string": b"",
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 50000),
    }

    await app(scope, receive, send)
    body = b"".join(response_body).decode("utf-8", errors="ignore")
    header_dict = {k.decode("latin1").lower(): v.decode("latin1") for k, v in headers}
    return status_code, header_dict, body


async def run_tests():
    print("=" * 60)
    print("開始執行：純 Python Jinja2 SSR 網頁與 Cookie 認證自動化測試")
    print("=" * 60)

    # 1. 清理測試資料
    with connect() as db:
        db.execute("DELETE FROM bookings WHERE purpose = 'SSR E2E Test Meeting'")
        db.execute("DELETE FROM users WHERE username IN ('ssr_student', 'admin_ssr')")

    # 2. 測試首頁轉址與教室清單
    print(">>> 1. 測試首頁 / 轉址與 /spaces 教室清單...")
    status, headers, body = await request_asgi("GET", "/")
    assert status == 303 and headers.get("location") == "/spaces"
    print("✔ 首頁正確 303 轉址至 /spaces")

    status, headers, body = await request_asgi("GET", "/spaces")
    assert status == 200 and "管院教室清單" in body
    print("✔ 教室清單正常渲染 (HTTP 200)")

    # 3. 測試註冊學生
    print(">>> 2. 測試學生透過表單註冊 POST /auth/register...")
    status, headers, body = await request_asgi(
        "POST",
        "/auth/register",
        {
            "username": "ssr_student",
            "password": "Password123",
            "confirm_password": "Password123",
            "role": "student",
        },
    )
    assert status == 303 and "/auth/login" in headers.get("location", "")
    print("✔ 學生註冊成功，自動轉址至登入頁")

    # 4. 測試表單登入取得 HttpOnly Cookie
    print(">>> 3. 測試表單登入 POST /auth/login...")
    status, headers, body = await request_asgi(
        "POST",
        "/auth/login",
        {
            "username": "ssr_student",
            "password": "Password123",
        },
    )
    assert status == 303 and "/spaces" in headers.get("location", "")
    set_cookie = headers.get("set-cookie", "")
    assert "access_token=" in set_cookie and "httponly" in set_cookie.lower()
    token_cookie = [p for p in set_cookie.split(";") if "access_token=" in p][0].strip()
    print("✔ 登入成功，正確寫入 access_token HttpOnly Cookie")

    # 5. 測試帶 Cookie 檢視週預約月曆
    print(">>> 4. 測試帶 Cookie 檢視預約頁 GET /bookings/calendar...")
    status, headers, body = await request_asgi("GET", "/bookings/calendar", cookie=token_cookie)
    assert status == 200 and "空間與物品預約" in body and "ssr_student" in body
    print("✔ 成功進入預約頁，導覽列正確顯示登入身分 ssr_student")

    # 6. 測試填表送出預約申請
    print(">>> 5. 測試填表送出預約申請 POST /bookings/calendar...")
    status, headers, body = await request_asgi(
        "POST",
        "/bookings/calendar",
        data={
            "room_id": 1,
            "booking_date": "2026-11-28",
            "start_time": "14:00",
            "end_time": "16:00",
            "purpose": "SSR E2E Test Meeting",
            "item_ids": [1, 2],
        },
        cookie=token_cookie,
    )
    assert status == 303 and "/bookings/history" in headers.get("location", "")
    print("✔ 預約申請送出成功，轉址至借用紀錄頁面")

    # 7. 檢視借用紀錄
    print(">>> 6. 檢視借用紀錄 GET /bookings/history...")
    status, headers, body = await request_asgi("GET", "/bookings/history", cookie=token_cookie)
    assert status == 200 and "SSR E2E Test Meeting" in body and "待審核" in body
    print("✔ 借用紀錄頁面正常渲染，顯示該筆預約狀態為「待審核」")

    # 8. 修改密碼
    print(">>> 7. 測試修改密碼 POST /auth/change-password...")
    status, headers, body = await request_asgi(
        "POST",
        "/auth/change-password",
        data={
            "old_password": "Password123",
            "new_password": "NewPassword456",
            "confirm_password": "NewPassword456",
        },
        cookie=token_cookie,
    )
    assert status == 303 and "/spaces" in headers.get("location", "")
    print("✔ 密碼修改成功")

    # 9. 登出
    print(">>> 8. 測試登出 POST /auth/logout...")
    status, headers, body = await request_asgi("POST", "/auth/logout", cookie=token_cookie)
    assert status == 303
    print("✔ 登出成功")

    # 10. 管理員審核與領還生命週期
    print(">>> 9. 測試管理員審核專區與生命週期...")
    with connect() as db:
        db.execute(
            "INSERT INTO users (username, password_hash, role, approval_status) "
            "VALUES ('admin_ssr', %s, 'admin', 'approved')",
            (hash_password("AdminPass123"),),
        )

    status, headers, body = await request_asgi(
        "POST",
        "/auth/login",
        {
            "username": "admin_ssr",
            "password": "AdminPass123",
        },
    )
    admin_cookie = [p for p in headers.get("set-cookie", "").split(";") if "access_token=" in p][0].strip()

    status, headers, body = await request_asgi("GET", "/admin/bookings", cookie=admin_cookie)
    assert status == 200 and "空間與物品借用管理（管理員專區）" in body and "SSR E2E Test Meeting" in body
    print("✔ 管理員成功檢視待審預約")

    with connect() as db:
        bk = db.execute("SELECT booking_id FROM bookings WHERE purpose = 'SSR E2E Test Meeting'").fetchone()
        booking_id = bk["booking_id"]

    # 核准
    status, headers, body = await request_asgi(
        "POST",
        f"/admin/bookings/{booking_id}/review",
        data={"decision": "approved", "review_comment": "審核通過"},
        cookie=admin_cookie,
    )
    assert status == 303
    print(f"✔ 管理員成功核准預約 #{booking_id}")

    # 借出
    status, headers, body = await request_asgi(
        "POST",
        f"/admin/bookings/{booking_id}/checkout",
        cookie=admin_cookie,
    )
    assert status == 303
    print(f"✔ 管理員成功登記借出領用 #{booking_id}")

    # 歸還
    status, headers, body = await request_asgi(
        "POST",
        f"/admin/bookings/{booking_id}/return",
        cookie=admin_cookie,
    )
    assert status == 303
    print(f"✔ 管理員成功登記確認歸還 #{booking_id}")

    print("=" * 60)
    print("🎉 純 Python Jinja2 SSR 網頁與 Cookie 認證全流程 100% 測試通過！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_tests())
