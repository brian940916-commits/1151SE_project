# 115-1 軟體工程專案｜純 Python 全端重構協作契約

這份文件供**空間查詢**、**預約借用**、**志願排課**三位組員在分頭重構系統（完全取消 PHP，改採純 Python 全端架構）時作為共同約定。

只要大家共用同一份根目錄的 `requirements.txt`，並在分頭開發時嚴格遵守以下 **4 個核心契約**，最後各自分支合併時就能 100% 無縫對接！

---

## 0. 技術棧與重構目標

- **後端與頁面服務**：FastAPI + Uvicorn（單一服務同時處理 REST API 與 Jinja2 網頁渲染）。
- **前端樣板**：Jinja2 SSR（完全取代 PHP 頁面，不再需要 XAMPP 或 PHP Runtime）。
- **資料庫管理**：SQLAlchemy 連線池 + PostgreSQL（延用既有 Migration 序號制）。
- **啟動方式**：本機僅需在虛擬環境執行單一指令（預設 Port 8000）：
  ```powershell
  python -m uvicorn app.main:app --app-dir api --reload
  ```

---

## 契約一：瀏覽器認證與狀態管理契約（最關鍵）

取消 PHP Session 後，網頁瀏覽器的登入狀態改由 **HttpOnly Cookie** 維持。

### 1. Cookie 規格
- **Cookie 名稱**：`access_token`
- **屬性**：`httponly=True`, `samesite="lax"`, `max_age=28800`（8 小時）

### 2. 登入與登出約定
- **登入時**（組員一帳號主責）：
  使用者帳密驗證成功後，在回傳 Response 時直接寫入 Cookie：
  ```python
  response.set_cookie(
      key="access_token",
      value=token,
      httponly=True,
      samesite="lax",
      max_age=28800,
  )
  ```
- **登出時**：
  呼叫登出時，直接清除該 Cookie 並重定向至登入頁：
  ```python
  response.delete_cookie(key="access_token")
  ```

### 3. 三人共用的身分驗證依賴項 (`app.auth`)
所有需要驗證身分的頁面或 API，**一律只注入 `Depends(current_user)`**。
`current_user` 升級為**雙軌自動相容**（優先讀取 Header，若無則讀取 Cookie）：
```python
# 位於 api/app/auth.py
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

bearer = HTTPBearer(auto_error=False)

def current_user(request: Request, auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
    token = None
    if auth:
        token = auth.credentials
    elif "access_token" in request.cookies:
        token = request.cookies["access_token"]
        
    if not token:
        raise HTTPException(status_code=401, detail="請先登入系統")
        
    # 依 token_hash 查詢 users 與 auth_sessions...
```
> **組員效益**：只要組員一寫好登入頁，組員二與組員三的頁面只要加上 `user = Depends(current_user)`，就能直接獲取登入者資料（`user_id`, `username`, `role`），完全不需各做各的驗證。

---

## 契約二：Jinja2 樣板繼承契約（統一外框）

所有 HTML 檔案集中於專案根目錄的 `templates/` 目錄。為了避免各做各的導致導覽列與外框衝突，所有人**一律繼承共用的 `base.html`**。

### 1. 基底樣板結構 (`templates/base.html`)
由全組共用，集中放置全站導覽列、共用 CSS 與系統通知訊息：
```html
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}1151 SE 管院空間系統{% endblock %}</title>
</head>
<body>
  <!-- 全站共用導覽列 -->
  <nav>
    <a href="/spaces">教室清單</a>
    {% if user %}
      · <a href="/bookings/calendar">空間／物品預約</a>
      · <a href="/bookings/history">借用紀錄</a>
      · <a href="/scheduling">志願排課</a>
      {% if user.role == 'admin' %}
        · <a href="/admin/bookings">審核與領還管理</a>
        · <a href="/admin/users">帳號審核</a>
      {% endif %}
      · <a href="/auth/change-password">修改密碼</a>
      · <strong>{{ user.username }}</strong>（{{ user.role }}）
      <form action="/auth/logout" method="post" style="display:inline;">
        <button type="submit">登出</button>
      </form>
    {% else %}
      · <a href="/auth/login">登入</a>
      · <a href="/auth/register">註冊</a>
    {% endif %}
  </nav>
  <hr>

  <!-- 系統提示訊息區 -->
  <main>
    {% if message %}<p style="color: green;"><strong>{{ message }}</strong></p>{% endif %}
    {% if error %}<p style="color: red;"><strong>{{ error }}</strong></p>{% endif %}

    <!-- 各模組內容填入區 -->
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

### 2. 各組員頁面撰寫規範
三位組員的頁面**禁止自行重寫 `<html>`, `<head>`, `<body>`, `<nav>`**，一律只需繼承：
```html
{% extends "base.html" %}

{% block title %}空間預約 - 管院系統{% endblock %}

{% block content %}
  <h1>我的預約頁面標題</h1>
  <form method="post">
    <!-- 這裡只寫該功能所需的表單或表格 -->
  </form>
{% endblock %}
```

---

## 契約三：目錄劃分與命名空間契約（避免 Git 衝突）

為了讓三人同時開工時**零衝突（Zero Merge Conflicts）**，各自的程式碼與樣板必須嚴格放在專屬目錄與檔案中：

```text
1151SE_project/
├── requirements.txt                      # 全組共用相依套件清單
├── database/
│   ├── migrations/                       # SQL 結構變更（見契約四）
│   └── seed.sql                          # 共用測試種子資料
├── templates/                            # 前端 Jinja2 樣板根目錄
│   ├── base.html                         # 共用基底樣板
│   ├── auth/                             # 【組員一】登入、註冊、改密樣板
│   ├── spaces/                           # 【組員一】教室清單、位置、全景樣板
│   ├── bookings/                         # 【組員二】週占用、預約申請、紀錄、領還審核樣板
│   └── scheduling/                       # 【組員三】志願選填、課表檢視、調課樣板
└── api/
    └── app/
        ├── main.py                       # 核心入口（只做 router 掛載與全域設定）
        ├── db.py                         # 共用資料庫連線池
        ├── auth.py                       # 共用登入身分檢查
        ├── services/
        │   └── availability.py           # 借用與排課共用的衝突與可用性計算
        └── routers/
            ├── auth.py                   # 【組員一】帳號路由
            ├── spaces.py                 # 【組員一】空間查詢路由
            ├── bookings.py               # 【組員二】預約借用路由
            └── scheduling.py             # 【組員三】志願排課路由
```

### `api/app/main.py` 的合併規則
`main.py` 保持極簡，只負責註冊各自獨立的 Router，合併 PR 時絕不打架：
```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .routers import auth, spaces, bookings, scheduling

app = FastAPI(title="1151 SE 管院空間系統")

app.include_router(auth.router)
app.include_router(spaces.router)
app.include_router(bookings.router)
app.include_router(scheduling.router)
```

---

## 契約四：資料庫與 Migration 序號契約

1. **不可修改他人已提交的 SQL 檔**：所有結構變更皆透過 `database/migrations/` 新增檔案。
2. **三位組員的序號分工**：
   - `001_auth_rooms.sql`（組員一）：使用者帳號表、教室清單表。
   - `002_student_registration.sql`（組員一）：學生註冊審核狀態更新。
   - `003_bookings_and_items.sql`（組員二）：借用表、物品清單表、物品明細表。
   - `004_schedules.sql`（組員三）：課程表、排課結果、志願選填表。
3. **初始化命令一致**：
   無論是誰更新了資料表，組員同步後只需執行既有的初始化命令即可自動套用：
   ```powershell
   python api/manage.py init
   ```

---

## 總結：開工前 30 秒核對清單

- [ ] 三人已安裝相同虛擬環境：`pip install -r requirements.txt`。
- [ ] 認證統一讀取 Cookie 名稱：`access_token`，身分驗證統一用 `Depends(current_user)`。
- [ ] 頁面樣板一律繼承 `templates/base.html`，放在各自專屬子目錄中。
- [ ] 程式碼各自寫在 `routers/auth.py`, `spaces.py`, `bookings.py`, `scheduling.py`。
- [ ] 啟動系統不再需要 XAMPP 或 PHP，統一用 Uvicorn 一鍵啟動！
