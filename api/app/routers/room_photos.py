from io import BytesIO
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from ..auth import admin
from ..db import connect
from ..pages import page, redirect, verify_form
from .spaces import get_room

router = APIRouter(include_in_schema=False)
PhotoKind = Literal["cover", "interior"]
photo_fields = {"cover": "cover_url", "interior": "photo_url"}
max_bytes = 10 * 1024 * 1024


def encode_photo(upload: UploadFile, kind: PhotoKind) -> bytes:
    data = upload.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, "照片超過 10 MB，請縮小後再上傳。")
    try:
        with Image.open(BytesIO(data), formats=("JPEG", "PNG", "WEBP")) as image:
            if image.width * image.height > 32_000_000:
                raise HTTPException(422, "照片解析度過高，請縮小後再上傳。")
            size = 960 if kind == "cover" else 1920
            photo = ImageOps.exif_transpose(image)
            photo.thumbnail((size, size), Image.Resampling.LANCZOS)
            output = BytesIO()
            photo.convert("RGB").save(output, "WEBP", quality=85)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(422, "無法讀取照片，請選擇 JPG、PNG 或 WebP 圖片。") from None


@router.get("/spaces/{room_id}/photos/{kind}")
def room_photo(room_id: int, kind: PhotoKind):
    with connect() as db:
        row = db.execute("SELECT image_data FROM room_images WHERE room_id=%s AND kind=%s",
                         (room_id, kind)).fetchone()
    if row is None:
        raise HTTPException(404, "找不到這張照片。")
    return Response(content=bytes(row["image_data"]), media_type="image/webp",
                    headers={"Cache-Control": "no-store"})


@router.get("/admin/spaces/{room_id}/photos")
def edit_photos(request: Request, room_id: int, user=Depends(admin)):
    return page(request, "spaces/photos.html", user=user, room=get_room(room_id))


def save_photo(room_id: int, kind: PhotoKind, data: bytes | None):
    field = photo_fields[kind]
    with connect() as db:
        if not db.execute("SELECT room_id FROM rooms WHERE room_id=%s FOR UPDATE", (room_id,)).fetchone():
            raise HTTPException(404, "找不到這間教室。")
        url = None
        if data is None:
            db.execute("DELETE FROM room_images WHERE room_id=%s AND kind=%s", (room_id, kind))
        else:
            db.execute("INSERT INTO room_images (room_id,kind,image_data) VALUES (%s,%s,%s) "
                       "ON CONFLICT (room_id,kind) DO UPDATE SET image_data=EXCLUDED.image_data",
                       (room_id, kind, data))
            url = f"/spaces/{room_id}/photos/{kind}"
        db.execute(f"INSERT INTO room_profiles (room_id,{field}) VALUES (%s,%s) "
                   f"ON CONFLICT (room_id) DO UPDATE SET {field}=EXCLUDED.{field}", (room_id, url))


@router.post("/admin/spaces/{room_id}/photos/{kind}", dependencies=[Depends(admin), Depends(verify_form)])
def upload_photo(request: Request, room_id: int, kind: PhotoKind, user=Depends(admin),
                 photo: Annotated[UploadFile | None, File()] = None):
    try:
        if photo is None:
            raise HTTPException(422, "請先選擇照片。")
        data = encode_photo(photo, kind)
    except HTTPException as exc:
        return page(request, "spaces/photos.html", room=get_room(room_id), user=user,
                    status=exc.status_code, error=exc.detail)
    save_photo(room_id, kind, data)
    return redirect(f"/admin/spaces/{room_id}/photos?notice=photo-updated")


@router.post("/admin/spaces/{room_id}/photos/{kind}/remove", dependencies=[Depends(admin), Depends(verify_form)])
def remove_photo(room_id: int, kind: PhotoKind):
    save_photo(room_id, kind, None)
    return redirect(f"/admin/spaces/{room_id}/photos?notice=photo-removed")
