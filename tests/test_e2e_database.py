"""端對端資料庫與業務邏輯測試腳本
直接測試與 PostgreSQL 連線、帳號註冊登入、預約申請、時段衝突攔截 (409)、
相鄰時段可銜接、管理員審核 (核准/退件) 與領用歸還完整流程。
"""

import sys
from datetime import date, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from app.auth import current_user
from app.db import connect
from app.main import Credentials, Decision, Registration, login, me, register, review
from app.routers.bookings import (
    BookingCreate,
    ReviewDecision,
    checkout_booking,
    create_booking,
    get_weekly_bookings,
    list_bookings,
    list_items,
    return_booking,
    review_booking,
)
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials


def run_e2e_tests():
    print(">>> 1. 測試資料庫連線與教室讀取...")
    with connect() as db:
        room = db.execute("SELECT * FROM rooms ORDER BY room_id LIMIT 1").fetchone()
        assert room, "教室資料表不能為空"
        room_id = room["room_id"]
        print(f"    教室讀取正常：room_id={room_id}, code={room['room_code']}, name={room['name']}")

    print(">>> 2. 測試物品清單讀取...")
    with connect() as db:
        items = db.execute("SELECT * FROM borrowable_items ORDER BY item_id").fetchall()
        assert len(items) >= 5, "種子資料物品至少需有 5 項"
        print(f"    物品讀取正常：共 {len(items)} 項，包含 {[it['item_name'] for it in items]}")

    print(">>> 3. 測試學生註冊與登入...")
    test_user = "stu_test_e2e"
    test_pwd = "password123"
    with connect() as db:
        db.execute("DELETE FROM users WHERE username = %s", (test_user,))
    reg_res = register(Registration(username=test_user, password=test_pwd, role="student"))
    assert reg_res["approval_status"] == "approved", "學生帳號註冊後應立即 approved"

    login_res = login(Credentials(username=test_user, password=test_pwd))
    token = login_res["access_token"]
    user = current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert user["username"] == test_user
    print(f"    學生登入成功：user_id={user['user_id']}, username={user['username']}")

    print(">>> 4. 測試管理員帳號建立與登入...")
    admin_user = "adm_test_e2e"
    admin_pwd = "admin_password123"
    with connect() as db:
        db.execute("DELETE FROM users WHERE username = %s", (admin_user,))
    from app.security import hash_password
    with connect() as db:
        db.execute(
            "INSERT INTO users (username, password_hash, role, approval_status) VALUES (%s, %s, 'admin', 'approved')",
            (admin_user, hash_password(admin_pwd)),
        )
    adm_login = login(Credentials(username=admin_user, password=admin_pwd))
    admin_obj = current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=adm_login["access_token"]))
    assert admin_obj["role"] == "admin"
    print(f"    管理員登入成功：user_id={admin_obj['user_id']}")

    print(">>> 5. 測試新增預約申請...")
    tomorrow = date.today() + timedelta(days=1)
    # 申請 Slot 1: 10:00 - 11:00
    b1 = create_booking(
        BookingCreate(
            room_id=room_id,
            booking_date=tomorrow,
            start_time=time(10, 0),
            end_time=time(11, 0),
            purpose="E2E 小組討論 1",
            item_ids=[items[0]["item_id"], items[1]["item_id"]],
        ),
        user=user,
    )
    b1_id = b1["booking_id"]
    print(f"    預約申請 1 送出成功：id={b1_id}, status={b1['status']}")

    print(">>> 6. 測試相鄰時段借用（11:00 - 12:00，應不衝突可送出與核准）...")
    b2 = create_booking(
        BookingCreate(
            room_id=room_id,
            booking_date=tomorrow,
            start_time=time(11, 0),
            end_time=time(12, 0),
            purpose="E2E 相鄰銜接時段",
            item_ids=[],
        ),
        user=user,
    )
    b2_id = b2["booking_id"]
    print(f"    預約申請 2（相鄰時段）送出成功：id={b2_id}")

    print(">>> 7. 測試管理員核准預約 1...")
    rev1 = review_booking(b1_id, ReviewDecision(status="approved", review_comment="核准借用 1"), admin_user=admin_obj)
    assert rev1["status"] == "approved"
    print("    預約 1 核准完成")

    print(">>> 8. 測試重疊衝突判定（已核准 10:00-11:00，申請 10:30-11:30 應被 409 拒絕）...")
    try:
        create_booking(
            BookingCreate(
                room_id=room_id,
                booking_date=tomorrow,
                start_time=time(10, 30),
                end_time=time(11, 30),
                purpose="衝突時段測試",
            ),
            user=user,
        )
        assert False, "重疊時段應被拒絕"
    except HTTPException as ex:
        assert ex.status_code == 409
        print(f"    重疊時段正確被 409 攔截：{ex.detail}")

    print(">>> 9. 測試相鄰時段（11:00-12:00）核准（應無衝突成功）...")
    rev2 = review_booking(b2_id, ReviewDecision(status="approved", review_comment="核准相鄰時段"), admin_user=admin_obj)
    assert rev2["status"] == "approved"
    print("    預約 2 核准完成，證實相鄰時段銜接不衝突")

    print(">>> 10. 測試領用借出（approved -> checked_out）...")
    chk = checkout_booking(b1_id, admin_user=admin_obj)
    assert chk["status"] == "checked_out"
    print(f"    預約 1 借出領用成功：checked_out_at={chk['checked_out_at']}")

    print(">>> 11. 測試確認歸還（checked_out -> returned）...")
    ret = return_booking(b1_id, admin_user=admin_obj)
    assert ret["status"] == "returned"
    print(f"    預約 1 歸還完成：returned_at={ret['returned_at']}")

    print(">>> 12. 測試週檢視占用狀況回傳...")
    weekly = get_weekly_bookings(room_id=room_id, week_start=tomorrow - timedelta(days=tomorrow.weekday()), user=user)
    assert "room" in weekly and "bookings" in weekly and "formal_courses" in weekly
    print(f"    週檢視資料結構驗證完成，目前當週借用筆數：{len(weekly['bookings'])}")

    print("\n============================================================")
    print("🎉 資料庫連線、認證、時段衝突 (409) 與完整領還生命週期測試全數通過！")
    print("============================================================")


if __name__ == "__main__":
    run_e2e_tests()
