import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from starlette.routing import NoMatchFound

from ..auth import admin, optional_user
from ..db import connect
from ..pages import page, redirect, verify_form

router = APIRouter()


@router.get("/", include_in_schema=False)
def home():
    return redirect("/spaces")


@router.get("/api/rooms")
def rooms():
    with connect() as db:
        return db.execute(
            "SELECT room_id,room_code,name,floor,capacity,is_bookable,is_schedulable FROM rooms "
            "ORDER BY CASE WHEN floor='B1' THEN 0 ELSE floor::integer END,room_code"
        ).fetchall()


@router.get("/spaces", include_in_schema=False)
def spaces(request: Request, user=Depends(optional_user)):
    with connect() as db:
        entries = db.execute(
            "SELECT room_id, room_code, name, floor, capacity, cover_url FROM rooms "
            "LEFT JOIN room_profiles USING (room_id) "
            "ORDER BY CASE WHEN floor='B1' THEN 0 ELSE floor::integer END, room_code"
        ).fetchall()
    floors = {}
    for entry in entries:
        floors.setdefault(entry["floor"], []).append(entry)
    return page(request, "spaces/list.html", user=user, floors=floors, count=len(entries))


@router.get("/spaces/{room_id}", include_in_schema=False)
def room_detail(request: Request, room_id: int, user=Depends(optional_user)):
    room = get_room(room_id)
    try:
        booking_url = request.url_for("calendar_page").include_query_params(room_id=room_id)
    except NoMatchFound:
        booking_url = None
    return page(request, "spaces/detail.html", user=user, room=room, booking_url=booking_url)


def get_room(room_id: int):
    with connect() as db:
        room = db.execute(
            "SELECT room_id, room_code, name, floor, capacity, managing_office, key_instructions, "
            "equipment, cover_url, photo_url, panorama_embed_url, source_url FROM rooms "
            "LEFT JOIN room_profiles USING (room_id) WHERE room_id = %s",
            (room_id,),
        ).fetchone()
    if room is None:
        raise HTTPException(404, "找不到這間教室。")
    return room


def edit_version(room):
    values = [room[field] for field in ("name", "floor", "capacity", "managing_office", "key_instructions", "equipment")]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


@router.get("/admin/spaces/{room_id}/edit", include_in_schema=False)
def edit_room(request: Request, room_id: int, user=Depends(admin)):
    room = get_room(room_id)
    return page(request, "spaces/edit.html", user=user, room=room, version=edit_version(room))


@router.post("/admin/spaces/{room_id}/edit", dependencies=[Depends(verify_form)], include_in_schema=False)
def update_room(request: Request, room_id: int, name: Annotated[str, Form()],
                floor: Annotated[str, Form()], version: Annotated[str, Form()],
                capacity: Annotated[str, Form()] = "", managing_office: Annotated[str, Form()] = "",
                key_instructions: Annotated[str, Form()] = "", equipment: Annotated[str, Form()] = "",
                user=Depends(admin)):
    items = [line.strip() for line in equipment.splitlines() if line.strip()]
    values = dict(name=name.strip(), floor=floor, capacity=capacity.strip(), managing_office=managing_office.strip(),
                  key_instructions=key_instructions.strip(), equipment=items)
    error = None
    if not values["name"] or "\x00" in (name + managing_office + key_instructions + equipment):
        error = "請填寫教室名稱，並確認文字內容有效。"
    elif floor not in ("B1", "1", "2", "3", "4"):
        error = "請選擇管院樓層。"
    elif values["capacity"] and not (values["capacity"].isascii() and values["capacity"].isdigit()
                                     and len(values["capacity"]) <= 10 and 0 < int(values["capacity"]) <= 2147483647):
        error = "容量請填正整數；待確認可留白。"
    if error:
        return page(request, "spaces/edit.html", user=user, room=get_room(room_id) | values,
                    version=version, status=422, error=error)
    with connect() as db:
        if not db.execute("SELECT room_id FROM rooms WHERE room_id=%s FOR UPDATE", (room_id,)).fetchone():
            raise HTTPException(404, "找不到這間教室。")
        current = db.execute(
            "SELECT room_id, room_code, name, floor, capacity, managing_office, key_instructions, equipment FROM rooms "
            "LEFT JOIN room_profiles USING (room_id) WHERE room_id=%s", (room_id,),
        ).fetchone()
        if edit_version(current) != version:
            return page(request, "spaces/edit.html", user=user, room=current | values, version=version, conflict=True,
                        status=409, error="教室資料已被更新。請另開最新版本比對後再編輯。")
        db.execute("UPDATE rooms SET name=%s, floor=%s, capacity=%s WHERE room_id=%s",
                   (values["name"], floor, int(capacity) if values["capacity"] else None, room_id))
        db.execute(
            "INSERT INTO room_profiles (room_id, managing_office, key_instructions, equipment) VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (room_id) DO UPDATE SET managing_office=EXCLUDED.managing_office, "
            "key_instructions=EXCLUDED.key_instructions, equipment=EXCLUDED.equipment",
            (room_id, values["managing_office"] or None, values["key_instructions"] or None, items),
        )
    return redirect(f"/spaces/{room_id}?notice=room-updated")
