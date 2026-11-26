from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles

from .db import ROOT
from .pages import page
from .routers import auth, room_photos, spaces

app = FastAPI(title="1151 SE 共用帳號與空間")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
app.include_router(auth.router)
app.include_router(spaces.router)
app.include_router(room_photos.router)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return await http_exception_handler(request, exc)
    return page(request, "auth/error.html", user=getattr(request.state, "user", None),
                error=exc.detail, status=exc.status_code)
