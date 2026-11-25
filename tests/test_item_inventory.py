"""測試跨所有教室物品庫存重疊時段合計與核准阻擋 (五台筆電不可借出六台)
"""

import sys
from datetime import date, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from app.auth import current_user
from app.db import connect
from app.main import Credentials, login
from app.routers.bookings import (
    BookingCreate,
    ReviewDecision,
    checkout_booking,
    create_booking,
    return_booking,
    review_booking,
)
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials


def test_laptop_inventory_limit():
    print("=" * 60)
    print("測試：跨教室物品庫存重疊計算與核准攔截（五台筆電不可借出六台）")
    print("=" * 60)

    # 1. 取得管理員與測試學生 Token
    adm_login = login(Credentials(username="admin", password="passw0rd"))
    admin_obj = current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=adm_login["access_token"]))

    # 取得或建立測試學生
    with connect() as db:
        user_row = db.execute("SELECT user_id, username, role, approval_status FROM users WHERE role='student' LIMIT 1").fetchone()
    if not user_row:
        from app.main import Registration, register
        reg = register(Registration(username="test_student_inv", password="password123", role="student"))
        stu_login = login(Credentials(username="test_student_inv", password="password123"))
        user = current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=stu_login["access_token"]))
    else:
        user = user_row

    # 2. 取得「筆電」與多間教室
    with connect() as db:
        laptop = db.execute("SELECT item_id, item_name, total_quantity FROM borrowable_items WHERE item_name='筆電'").fetchone()
        assert laptop, "找不到筆電"
        laptop_id = laptop["item_id"]
        laptop_total = laptop["total_quantity"]
        assert laptop_total == 5, f"預設筆電總量應為 5，目前為 {laptop_total}"

        rooms = db.execute("SELECT room_id, room_code FROM rooms ORDER BY room_id LIMIT 10").fetchall()
        assert len(rooms) >= 6, "至少需要 6 間教室進行測試"

    test_date = date.today() + timedelta(days=2)

    # 清理該日期的舊預約
    with connect() as db:
        db.execute("DELETE FROM bookings WHERE booking_date = %s", (test_date,))

    print(f"✔ 準備就緒：物品「{laptop['item_name']}」總量為 {laptop_total} 台，測試日期 {test_date}")

    # 3. 依序在 5 間不同教室申請 14:00 - 16:00 各借 1 台筆電
    booking_ids = []
    for i in range(5):
        b = create_booking(
            BookingCreate(
                room_id=rooms[i]["room_id"],
                booking_date=test_date,
                start_time=time(14, 0),
                end_time=time(16, 0),
                purpose=f"教室 {rooms[i]['room_code']} 筆電申請",
                item_ids=[laptop_id],
            ),
            user=user,
        )
        booking_ids.append(b["booking_id"])

    print("✔ 5 筆預約申請已建立（分屬 5 間不同教室）")

    # 4. 管理員核准這 5 筆預約：應該全部成功 (5/5 已佔滿)
    for idx, bid in enumerate(booking_ids):
        res = review_booking(bid, ReviewDecision(status="approved", review_comment=f"核准第 {idx+1} 台"), admin_user=admin_obj)
        assert res["status"] == "approved"

    print("✔ 管理員已成功核准 5 間教室的借用申請，目前 14:00-16:00 筆電已達上限 5 台")

    # 5. 第 6 間教室申請重疊時段 15:00 - 17:00 借 1 台筆電
    b6 = create_booking(
        BookingCreate(
            room_id=rooms[5]["room_id"],
            booking_date=test_date,
            start_time=time(15, 0),
            end_time=time(17, 0),
            purpose="第 6 間教室欲借第 6 台筆電",
            item_ids=[laptop_id],
        ),
        user=user,
    )
    b6_id = b6["booking_id"]
    print(f"✔ 第 6 筆申請已送出 (id={b6_id})，時段為 15:00-17:00 (與 14:00-16:00 重疊)")

    # 6. 管理員嘗試核准第 6 筆申請：必須被拒絕，回傳 409 Conflict 並告知理由！
    try:
        review_booking(b6_id, ReviewDecision(status="approved", review_comment="嘗試核准第 6 台"), admin_user=admin_obj)
        assert False, "庫存不足時核准應該失敗，但卻成功了！"
    except HTTPException as ex:
        assert ex.status_code == 409
        print(f"✔ 成功攔截第 6 筆核准！狀態碼：409 Conflict")
        print(f"  拒絕理由：{ex.detail}")
        assert "筆電" in ex.detail
        assert "庫存不足" in ex.detail
        assert "5" in ex.detail

    # 7. 驗證相鄰時段借用筆電（16:00 - 18:00，與 14:00-16:00 銜接不重疊）
    b7 = create_booking(
        BookingCreate(
            room_id=rooms[6]["room_id"],
            booking_date=test_date,
            start_time=time(16, 0),
            end_time=time(18, 0),
            purpose="相鄰時段借用筆電",
            item_ids=[laptop_id],
        ),
        user=user,
    )
    res7 = review_booking(b7["booking_id"], ReviewDecision(status="approved", review_comment="核准相鄰時段"), admin_user=admin_obj)
    assert res7["status"] == "approved"
    print(f"✔ 相鄰時段 (16:00-18:00) 筆電核准成功（確認相鄰銜接不衝突）")

    # 8. 測試領用與歸還流程對庫存的影響：
    # 將第 1 筆預約註記借出 (checked_out)
    checkout_booking(booking_ids[0], admin_user=admin_obj)
    print("✔ 第 1 筆預約已借出 (checked_out)")

    # 此時第 6 筆申請嘗試核准仍應被拒絕（借出中仍視為占用）
    try:
        review_booking(b6_id, ReviewDecision(status="approved"), admin_user=admin_obj)
        assert False, "借出中仍應算入占用"
    except HTTPException as ex:
        assert ex.status_code == 409
        print(f"✔ 當物品狀態為 checked_out 時，依然正確算入跨教室占用並攔截")

    # 將第 1 筆預約註記歸還 (returned)
    return_booking(booking_ids[0], admin_user=admin_obj)
    print("✔ 第 1 筆預約已歸還 (returned)，14:00-16:00 筆電占用降為 4 台")

    # 此時第 6 筆申請再次審核，庫存已釋出，應可成功核准！
    res6 = review_booking(b6_id, ReviewDecision(status="approved", review_comment="庫存釋出後核准"), admin_user=admin_obj)
    assert res6["status"] == "approved"
    print("✔ 歸還釋出庫存後，第 6 筆預約順利核准通過！")

    print("=" * 60)
    print("🎉 跨教室物品庫存重疊計算與攔截測試 100% 通過！")
    print("=" * 60)


if __name__ == "__main__":
    test_laptop_inventory_limit()
