"""共用時段判斷與可用性服務 (Availability Service)

此模組提供空間預約與排課模組共用的時段衝突檢查、併發交易鎖定以及週占用查詢。
"""

from datetime import date, time, timedelta
from typing import Any

from fastapi import HTTPException


def lock_room_for_update(db, room_id: int) -> dict[str, Any]:
    """在目前資料庫交易中鎖定特定教室資料列 (SELECT ... FOR UPDATE)

    防止多個管理員或預約程序同時核准重疊時段造成撞期。
    """
    room = db.execute(
        "SELECT room_id, room_code, name, is_bookable, is_schedulable FROM rooms WHERE room_id = %s FOR UPDATE",
        (room_id,),
    ).fetchone()
    if not room:
        raise HTTPException(status_code=404, detail="找不到指定教室")
    return room


def check_room_overlap(
    db,
    room_id: int,
    booking_date: date,
    start_time: time,
    end_time: time,
    exclude_booking_id: int | None = None,
) -> list[dict[str, Any]]:
    """檢查指定教室在特定日期的時段是否有衝突。

    業務規則：
    1. 同教室才判斷重疊，不同教室各自獨立。
    2. 相鄰時段視為可銜接（如 10:00–11:00 與 11:00–12:00 不衝突）：
       SQL 判斷條件為 `start_time < :end_time AND end_time > :start_time`。
    3. 僅已核准 (approved) 與借出中 (checked_out) 的預約視為佔用時段。
    """
    query = """
        SELECT booking_id, room_id, booking_date, start_time, end_time, status, purpose
        FROM bookings
        WHERE room_id = %s
          AND booking_date = %s
          AND status IN ('approved', 'checked_out')
          AND start_time < %s
          AND end_time > %s
    """
    params: list[Any] = [room_id, booking_date, end_time, start_time]

    if exclude_booking_id is not None:
        query += " AND booking_id <> %s"
        params.append(exclude_booking_id)

    query += " ORDER BY start_time"
    return db.execute(query, tuple(params)).fetchall()


def check_formal_schedule_conflict(
    db,
    room_id: int,
    booking_date: date,
    start_time: time,
    end_time: time,
) -> list[dict[str, Any]]:
    """預留介面：檢查與排課模組（模組三）正式課表的衝突狀況。

    待排課模組建立正式課表資料表（如 course_schedules）後，
    可在此處增加對應的每週定期課程時段檢查。
    目前回傳空清單，保持向下相容。
    """
    # TODO (模組三接入):
    # weekday = booking_date.isoweekday() # 1=Mon, ..., 7=Sun
    # SELECT * FROM course_schedules WHERE room_id = %s AND weekday = %s AND ...
    return []


def assert_no_conflict(
    db,
    room_id: int,
    booking_date: date,
    start_time: time,
    end_time: time,
    exclude_booking_id: int | None = None,
) -> None:
    """綜合衝突驗證：若有撞期則直接拋出 409 Conflict。"""
    # 1. 檢查借用占用
    overlaps = check_room_overlap(
        db, room_id, booking_date, start_time, end_time, exclude_booking_id
    )
    if overlaps:
        c = overlaps[0]
        s_str = c["start_time"].strftime("%H:%M") if hasattr(c["start_time"], "strftime") else str(c["start_time"])
        e_str = c["end_time"].strftime("%H:%M") if hasattr(c["end_time"], "strftime") else str(c["end_time"])
        raise HTTPException(
            status_code=409,
            detail=f"該時段已被已核准借用佔用 ({s_str} - {e_str})，請選擇其他時段",
        )

    # 2. 檢查正式課表占用（預留介面）
    schedule_conflicts = check_formal_schedule_conflict(
        db, room_id, booking_date, start_time, end_time
    )
    if schedule_conflicts:
        raise HTTPException(
            status_code=409,
            detail="該時段與正式課表衝突，請選擇其他時段",
        )


def check_item_inventory_overlap(
    db,
    item_id: int,
    booking_date: date,
    start_time: time,
    end_time: time,
    requested_qty: int = 1,
    exclude_booking_id: int | None = None,
) -> tuple[bool, int, int, int, time | None]:
    """檢查指定物品在特定日期與時段的跨教室庫存占用狀況。

    業務規則：
    1. 合計所有教室在該時段已核准 (approved) 或借出中 (checked_out) 的同項物品數量。
    2. 相鄰時段視為可銜接（如前筆至 11:00 歸還，本筆自 11:00 起借用不計入重疊）。
    3. 評估時段內所有關鍵時間點的最高並行使用量 (peak usage)。

    回傳：
    (is_available, total_quantity, max_existing_used, peak_with_requested, peak_time)
    """
    item = db.execute(
        "SELECT item_id, item_name, total_quantity FROM borrowable_items WHERE item_id = %s FOR UPDATE",
        (item_id,),
    ).fetchone()
    if not item:
        raise HTTPException(status_code=404, detail="找不到指定的借用物品")

    total_quantity = item["total_quantity"]

    # 跨所有教室查詢該日期、重疊時段內且狀態為 approved 或 checked_out 的該物品借用紀錄
    query = """
        SELECT b.booking_id, b.room_id, b.start_time, b.end_time, bi.quantity
        FROM bookings b
        JOIN booking_items bi ON b.booking_id = bi.booking_id
        WHERE bi.item_id = %s
          AND b.booking_date = %s
          AND b.status IN ('approved', 'checked_out')
          AND b.start_time < %s
          AND b.end_time > %s
    """
    params: list[Any] = [item_id, booking_date, end_time, start_time]
    if exclude_booking_id is not None:
        query += " AND b.booking_id <> %s"
        params.append(exclude_booking_id)

    query += " ORDER BY b.start_time"
    overlapping_bookings = db.execute(query, tuple(params)).fetchall()

    if not overlapping_bookings:
        is_avail = (requested_qty <= total_quantity)
        return is_avail, total_quantity, 0, requested_qty, start_time

    # 收集關鍵時間點（申請開始時間點，以及在申請時段內開始的其他預約時間點）
    critical_times = {start_time}
    for b in overlapping_bookings:
        bst = b["start_time"]
        if start_time <= bst < end_time:
            critical_times.add(bst)

    max_existing_used = 0
    peak_time = start_time

    for t in sorted(critical_times):
        # 計算時間點 t 正在使用的物品總量 (start_time <= t < end_time)
        active_qty = sum(
            b["quantity"]
            for b in overlapping_bookings
            if b["start_time"] <= t < b["end_time"]
        )
        if active_qty > max_existing_used:
            max_existing_used = active_qty
            peak_time = t

    peak_with_requested = max_existing_used + requested_qty
    is_avail = (peak_with_requested <= total_quantity)

    return is_avail, total_quantity, max_existing_used, peak_with_requested, peak_time


def assert_items_availability_for_booking(
    db,
    booking_id: int,
    exclude_booking_id: int | None = None,
) -> None:
    """核准預約時驗證此筆預約所含的所有物品，在重疊時段內跨教室合計數量是否超過庫存總量。

    若有任何物品超過庫存上限，拋出 409 Conflict 並告知具體原因。
    """
    booking = db.execute(
        "SELECT booking_id, booking_date, start_time, end_time FROM bookings WHERE booking_id = %s",
        (booking_id,),
    ).fetchone()
    if not booking:
        raise HTTPException(status_code=404, detail="找不到指定預約")

    booking_items = db.execute(
        """
        SELECT bi.booking_item_id, bi.item_id, bi.quantity, i.item_name
        FROM booking_items bi
        JOIN borrowable_items i ON bi.item_id = i.item_id
        WHERE bi.booking_id = %s
        ORDER BY bi.item_id
        """,
        (booking_id,),
    ).fetchall()

    for bi in booking_items:
        is_avail, total_qty, used_qty, peak_qty, peak_time = check_item_inventory_overlap(
            db=db,
            item_id=bi["item_id"],
            booking_date=booking["booking_date"],
            start_time=booking["start_time"],
            end_time=booking["end_time"],
            requested_qty=bi["quantity"],
            exclude_booking_id=booking_id if exclude_booking_id is None else exclude_booking_id,
        )
        if not is_avail:
            peak_str = peak_time.strftime("%H:%M") if hasattr(peak_time, "strftime") else str(peak_time)
            s_str = booking["start_time"].strftime("%H:%M") if hasattr(booking["start_time"], "strftime") else str(booking["start_time"])
            e_str = booking["end_time"].strftime("%H:%M") if hasattr(booking["end_time"], "strftime") else str(booking["end_time"])
            raise HTTPException(
                status_code=409,
                detail=(
                    f"物品「{bi['item_name']}」庫存不足無法核准："
                    f"全校總庫存量為 {total_qty} 件，"
                    f"申請時段 {s_str}–{e_str}（重疊高峰約 {peak_str}）全校已核准/借出共 {used_qty} 件，"
                    f"本申請需借用 {bi['quantity']} 件，合計將達 {peak_qty} 件超出庫存上限。"
                ),
            )


def get_room_weekly_availability(
    db,
    room_id: int,
    week_start: date,
) -> dict[str, Any]:
    """取得指定教室在某週 (週一至週日) 的全部預約與課表占用狀況。"""
    room = db.execute(
        "SELECT room_id, room_code, name, floor, capacity, is_bookable, is_schedulable FROM rooms WHERE room_id = %s",
        (room_id,),
    ).fetchone()
    if not room:
        raise HTTPException(status_code=404, detail="找不到指定教室")

    week_end = week_start + timedelta(days=6)

    # 查詢當週的所有借用（含 pending, approved, checked_out 等狀態，供週檢視呈現）
    bookings = db.execute(
        """
        SELECT b.booking_id, b.room_id, b.booking_date, b.start_time, b.end_time,
               b.status, b.purpose, b.user_id, u.username AS applicant_username
        FROM bookings b
        JOIN users u ON b.user_id = u.user_id
        WHERE b.room_id = %s
          AND b.booking_date >= %s
          AND b.booking_date <= %s
          AND b.status IN ('approved', 'checked_out', 'pending')
        ORDER BY b.booking_date, b.start_time
        """,
        (room_id, week_start, week_end),
    ).fetchall()

    formatted_bookings = []
    for b in bookings:
        formatted_bookings.append({
            "booking_id": b["booking_id"],
            "booking_date": b["booking_date"].isoformat() if hasattr(b["booking_date"], "isoformat") else str(b["booking_date"]),
            "start_time": b["start_time"].strftime("%H:%M") if hasattr(b["start_time"], "strftime") else str(b["start_time"]),
            "end_time": b["end_time"].strftime("%H:%M") if hasattr(b["end_time"], "strftime") else str(b["end_time"]),
            "status": b["status"],
            "purpose": b["purpose"],
            "user_id": b["user_id"],
            "applicant_username": b["applicant_username"],
        })

    # 預留排課模組正式課表結構
    formal_courses: list[dict[str, Any]] = []

    return {
        "room": room,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "bookings": formatted_bookings,
        "formal_courses": formal_courses,
    }
