"""核心入口 (Main FastAPI Application)

註冊四大模組路由：
- auth: 認證與帳號管理（API 與 SSR 網頁）
- spaces: 空間與教室清單（API 與 SSR 網頁）
- bookings: 空間與物品預約借用（API 與 SSR 網頁）
- scheduling: 志願排課預留路由（組員三主責）
"""

from fastapi import FastAPI

from .routers import auth, bookings, scheduling, spaces

app = FastAPI(title="1151 SE 管院空間系統")

# 掛載各模組路由
app.include_router(auth.router)
app.include_router(spaces.router)
app.include_router(bookings.router)
app.include_router(scheduling.router)

# 向上相容導出（供既有單元測試與腳本引用）
Credentials = auth.Credentials
Registration = auth.Registration
ChangePassword = auth.ChangePassword
login = auth.login
register = auth.register
me = auth.me
change_password = auth.change_password
logout = auth.logout

Decision = spaces.Decision
pending = spaces.pending
review = spaces.review
rooms = spaces.rooms
