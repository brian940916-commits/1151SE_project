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
