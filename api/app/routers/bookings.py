"""空間與物品預約借用路由 (Bookings Router)

提供可借用物品清單、週檢視占用狀況、新增預約申請、
借用紀錄查詢、管理員審核、領用借出與確認歸還等功能。
"""

from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import admin, current_user
from ..db import connect
from ..services.availability import (
    assert_no_conflict,
    get_room_weekly_availability,
    lock_room_for_update,
)

router = APIRouter(tags=["bookings"])


class BookingCreate(BaseModel):
    room_id: int
    booking_date: date
    start_time: time
    end_time: time
    purpose: str = Field(min_length=1, max_length=500)
    item_ids: list[int] = Field(default_factory=list)


class ReviewDecision(BaseModel):
    status: Literal["approved", "rejected"]
    review_comment: str | None = Field(default=None, max_length=500)


def _format_booking_row(b: dict[str, Any], items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "booking_id": b["booking_id"],
        "room_id": b["room_id"],
        "room_code": b.get("room_code"),
        "room_name": b.get("room_name"),
        "floor": b.get("floor"),
        "user_id": b["user_id"],
        "applicant_username": b.get("applicant_username"),
        "applicant_role": b.get("applicant_role"),
        "booking_date": b["booking_date"].isoformat() if hasattr(b["booking_date"], "isoformat") else str(b["booking_date"]),
        "start_time": b["start_time"].strftime("%H:%M") if hasattr(b["start_time"], "strftime") else str(b["start_time"]),
        "end_time": b["end_time"].strftime("%H:%M") if hasattr(b["end_time"], "strftime") else str(b["end_time"]),
        "purpose": b["purpose"],
        "status": b["status"],
        "review_comment": b.get("review_comment"),
        "reviewed_by": b.get("reviewed_by"),
        "reviewer_username": b.get("reviewer_username"),
        "reviewed_at": b["reviewed_at"].isoformat() if b.get("reviewed_at") else None,
        "checked_out_by": b.get("checked_out_by"),
        "checkout_operator": b.get("checkout_operator"),
        "checked_out_at": b["checked_out_at"].isoformat() if b.get("checked_out_at") else None,
        "returned_by": b.get("returned_by"),
        "return_operator": b.get("return_operator"),
        "returned_at": b["returned_at"].isoformat() if b.get("returned_at") else None,
        "created_at": b["created_at"].isoformat() if b.get("created_at") else None,
        "items": items or [],
    }


@router.get("/api/items")
def list_items(user=Depends(current_user)):
    """取得可借用物品清單（需登入）。"""
    with connect() as db:
        return db.execute(
            "SELECT item_id, item_name, description, total_quantity, is_active "
            "FROM borrowable_items WHERE is_active = true ORDER BY item_id"
        ).fetchall()


@router.get("/api/bookings/weekly")
def get_weekly_bookings(
    room_id: int = Query(...),
    week_start: date | None = Query(None),
    user=Depends(current_user),
):
    """以週為單位回傳指定教室當週的借用占用狀況與預留正式課表結構。"""
    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())  # 預設為當週週一

    with connect() as db:
        return get_room_weekly_availability(db, room_id, week_start)


@router.post("/api/bookings", status_code=201)
def create_booking(
    data: BookingCreate,
    user=Depends(current_user),
):
    """新增預約申請（空間、日期、起訖時間、多選物品、事由）。"""
    if data.start_time >= data.end_time:
        raise HTTPException(status_code=400, detail="結束時間必須晚於開始時間")

    today = date.today()
    if data.booking_date < today:
        raise HTTPException(status_code=400, detail="不可預約過去日期")

    with connect() as db:
        # 1. 檢查教室是否存在且開放借用
        room = db.execute(
            "SELECT room_id, room_code, name, is_bookable FROM rooms WHERE room_id = %s",
            (data.room_id,),
        ).fetchone()
        if not room:
            raise HTTPException(status_code=404, detail="找不到指定教室")
        if room["is_bookable"] is False:
            raise HTTPException(status_code=400, detail="該空間目前不開放預約借用")

        # 2. 衝突判斷（同教室相鄰不衝突，重疊且為 approved/checked_out 則回傳 409）
        assert_no_conflict(db, data.room_id, data.booking_date, data.start_time, data.end_time)

        # 3. 檢查物品合法性
        item_rows = []
        if data.item_ids:
            unique_item_ids = list(set(data.item_ids))
            item_rows = db.execute(
                "SELECT item_id, item_name FROM borrowable_items WHERE item_id = ANY(%s) AND is_active = true",
                (unique_item_ids,),
            ).fetchall()
            if len(item_rows) != len(unique_item_ids):
                raise HTTPException(status_code=400, detail="選取的借用物品包含無效或未啟用的項目")

        # 4. 寫入預約主表 (bookings)
        created_booking = db.execute(
            """
            INSERT INTO bookings (room_id, user_id, booking_date, start_time, end_time, purpose, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending')
            RETURNING booking_id, room_id, user_id, booking_date, start_time, end_time, purpose, status, created_at
            """,
            (
                data.room_id,
                user["user_id"],
                data.booking_date,
                data.start_time,
                data.end_time,
                data.purpose,
            ),
        ).fetchone()

        booking_id = created_booking["booking_id"]

        # 5. 寫入借用明細 (booking_items)
        attached_items = []
        for it in item_rows:
            db.execute(
                "INSERT INTO booking_items (booking_id, item_id, quantity, status) VALUES (%s, %s, 1, 'reserved')",
                (booking_id, it["item_id"]),
            )
            attached_items.append({
                "item_id": it["item_id"],
                "item_name": it["item_name"],
                "quantity": 1,
                "status": "reserved",
            })

        booking_data = dict(created_booking)
        booking_data["room_code"] = room["room_code"]
        booking_data["room_name"] = room["name"]
        booking_data["applicant_username"] = user["username"]
        booking_data["applicant_role"] = user["role"]

        return _format_booking_row(booking_data, attached_items)


@router.get("/api/bookings")
def list_bookings(
    status: str | None = Query(None),
    room_id: int | None = Query(None),
    user_id: int | None = Query(None),
    user=Depends(current_user),
):
    """瀏覽借用紀錄。一般使用者只看自己；管理員可看全部並支援依 status、room_id 篩選（供排課模組查詢）。"""
    with connect() as db:
        query = """
            SELECT b.*,
                   r.room_code, r.name AS room_name, r.floor,
                   u.username AS applicant_username, u.role AS applicant_role,
                   rev.username AS reviewer_username,
                   cho.username AS checkout_operator,
                   ret.username AS return_operator
            FROM bookings b
            JOIN rooms r ON b.room_id = r.room_id
            JOIN users u ON b.user_id = u.user_id
            LEFT JOIN users rev ON b.reviewed_by = rev.user_id
            LEFT JOIN users cho ON b.checked_out_by = cho.user_id
            LEFT JOIN users ret ON b.returned_by = ret.user_id
            WHERE 1=1
        """
        params: list[Any] = []

        # 權限過濾：非管理員強制只能看自己的紀錄
        if user["role"] != "admin":
            query += " AND b.user_id = %s"
            params.append(user["user_id"])
        else:
            if user_id is not None:
                query += " AND b.user_id = %s"
                params.append(user_id)

        if status:
            query += " AND b.status = %s"
            params.append(status)

        if room_id is not None:
            query += " AND b.room_id = %s"
            params.append(room_id)

        query += " ORDER BY b.booking_date DESC, b.start_time DESC, b.booking_id DESC"
        rows = db.execute(query, tuple(params)).fetchall()

        if not rows:
            return []

        # 一併批次抓取 items 明細
        booking_ids = [r["booking_id"] for r in rows]
        item_rows = db.execute(
            """
            SELECT bi.booking_item_id, bi.booking_id, bi.item_id, bi.quantity, bi.status,
                   bi.checked_out_at, bi.returned_at,
                   i.item_name, i.description
            FROM booking_items bi
            JOIN borrowable_items i ON bi.item_id = i.item_id
            WHERE bi.booking_id = ANY(%s)
            ORDER BY bi.booking_item_id
            """,
            (booking_ids,),
        ).fetchall()

        items_map: dict[int, list[dict[str, Any]]] = {bid: [] for bid in booking_ids}
        for item in item_rows:
            items_map[item["booking_id"]].append({
                "booking_item_id": item["booking_item_id"],
                "item_id": item["item_id"],
                "item_name": item["item_name"],
                "quantity": item["quantity"],
                "status": item["status"],
                "checked_out_at": item["checked_out_at"].isoformat() if item["checked_out_at"] else None,
                "returned_at": item["returned_at"].isoformat() if item["returned_at"] else None,
            })

        return [_format_booking_row(r, items_map.get(r["booking_id"], [])) for r in rows]


@router.post("/api/admin/bookings/{booking_id}/review")
def review_booking(
    booking_id: int,
    decision: ReviewDecision,
    admin_user=Depends(admin),
):
    """審核預約（限管理員）：核准 (approved) 或退件 (rejected)，可填意見。核准時鎖定教室資料列並重查重疊。"""
    with connect() as db:
        # 1. 查詢並行鎖定目前預約
        booking = db.execute(
            "SELECT * FROM bookings WHERE booking_id = %s FOR UPDATE",
            (booking_id,),
        ).fetchone()
        if not booking:
            raise HTTPException(status_code=404, detail="找不到此預約申請")
        if booking["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"該申請狀態為 {booking['status']}，已無法重複審核")

        # 2. 若為核准，必須鎖定教室並重新檢查衝突
        if decision.status == "approved":
            lock_room_for_update(db, booking["room_id"])
            assert_no_conflict(
                db,
                booking["room_id"],
                booking["booking_date"],
                booking["start_time"],
                booking["end_time"],
                exclude_booking_id=booking_id,
            )
            updated = db.execute(
                """
                UPDATE bookings
                SET status = 'approved',
                    review_comment = %s,
                    reviewed_by = %s,
                    reviewed_at = now()
                WHERE booking_id = %s
                RETURNING *
                """,
                (decision.review_comment, admin_user["user_id"], booking_id),
            ).fetchone()
        else:
            updated = db.execute(
                """
                UPDATE bookings
                SET status = 'rejected',
                    review_comment = %s,
                    reviewed_by = %s,
                    reviewed_at = now()
                WHERE booking_id = %s
                RETURNING *
                """,
                (decision.review_comment, admin_user["user_id"], booking_id),
            ).fetchone()

        return _format_booking_row(dict(updated))


@router.post("/api/admin/bookings/{booking_id}/checkout")
def checkout_booking(
    booking_id: int,
    admin_user=Depends(admin),
):
    """領用教室鑰匙與物品時註記借出（限管理員：approved -> checked_out）。"""
    with connect() as db:
        booking = db.execute(
            "SELECT * FROM bookings WHERE booking_id = %s FOR UPDATE",
            (booking_id,),
        ).fetchone()
        if not booking:
            raise HTTPException(status_code=404, detail="找不到此預約申請")
        if booking["status"] != "approved":
            raise HTTPException(
                status_code=409,
                detail=f"目前預約狀態為 {booking['status']}，只有已核准 (approved) 的預約才能登記借出領用",
            )

        updated = db.execute(
            """
            UPDATE bookings
            SET status = 'checked_out',
                checked_out_by = %s,
                checked_out_at = now()
            WHERE booking_id = %s
            RETURNING *
            """,
            (admin_user["user_id"], booking_id),
        ).fetchone()

        db.execute(
            """
            UPDATE booking_items
            SET status = 'checked_out',
                checked_out_at = now()
            WHERE booking_id = %s
            """,
            (booking_id,),
        )

        return _format_booking_row(dict(updated))


@router.post("/api/admin/bookings/{booking_id}/return")
def return_booking(
    booking_id: int,
    admin_user=Depends(admin),
):
    """歸還時確認註記歸還（限管理員：checked_out -> returned）。"""
    with connect() as db:
        booking = db.execute(
            "SELECT * FROM bookings WHERE booking_id = %s FOR UPDATE",
            (booking_id,),
        ).fetchone()
        if not booking:
            raise HTTPException(status_code=404, detail="找不到此預約申請")
        if booking["status"] != "checked_out":
            raise HTTPException(
                status_code=409,
                detail=f"目前預約狀態為 {booking['status']}，只有借出中 (checked_out) 的預約才能登記歸還",
            )

        updated = db.execute(
            """
            UPDATE bookings
            SET status = 'returned',
                returned_by = %s,
                returned_at = now()
            WHERE booking_id = %s
            RETURNING *
            """,
            (admin_user["user_id"], booking_id),
        ).fetchone()

        db.execute(
            """
            UPDATE booking_items
            SET status = 'returned',
                returned_at = now()
            WHERE booking_id = %s
            """,
            (booking_id,),
        )

        return _format_booking_row(dict(updated))
