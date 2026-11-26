# 1151 軟體工程學期專案

**組員開工前必讀**　[純 Python 全端重構協作契約](docs/refactor-contracts.md)列出共用技術、登入方式、樣板和目錄。[團隊開發規範](docs/team-guidelines.md)記錄分工、共用資料與業務規則。

- 管院空間查詢
- 空間／物品預約借用
- 志願排課

## 共用登入與管院教室清單

訪客可瀏覽教室。學生註冊後可立即登入；老師帳號須由管理員在「帳號審核」核准後才能登入。登入後可讀取目前身分並登出。管理員從本機命令建立。公開註冊帳號限 3–40 個英數字、點、底線或短橫線，大小寫視為相同。密碼至少 8 個字元，網頁註冊時需再次輸入以確認。

## 在自己的電腦啟動 FastAPI

開發環境使用 Python 3.11 以上與 PostgreSQL。FastAPI 由 Uvicorn 啟動，重構後的網頁由同一個服務渲染 Jinja2 樣板。先在 PostgreSQL 建立本專案專用的資料庫與具建表權限的帳號。在專案根目錄執行以下 PowerShell 指令：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

在本機編輯 .env，把 DATABASE_URL 換成自己的資料庫連線字串（密碼含 URL 特殊字元需百分比編碼）。不要將 .env 上傳 GitHub。接著執行：

```powershell
.\.venv\Scripts\python.exe api/manage.py init
.\.venv\Scripts\python.exe api/manage.py create-admin myadmin
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --host 127.0.0.1 --port 8000
```

服務啟動後，在瀏覽器開啟 `http://127.0.0.1:8000/spaces` 查看教室。從導覽列進入登入或註冊頁。管理員登入後可從「帳號審核」核准或退回老師申請。API 文件位於 `http://127.0.0.1:8000/docs`。

`init` 可重複執行。管理員核准老師申請前應確認申請身分。密碼以加鹽 PBKDF2 雜湊保存；API 登入回傳有效八小時的 bearer token，API 登出時撤銷該 token。本機預覽採用 HTTP 回環位址。

## 組員串接

| 方法 | 路徑 | 用途 |
| --- | --- | --- |
| GET | /api/rooms | 訪客可讀取 room_id、room_code、name、floor、capacity、is_bookable、is_schedulable。 |
| POST | /api/auth/register | JSON 含 username、password、role（student 或 teacher）。學生回傳 approved，老師回傳 pending，重複名稱回傳 409。 |
| POST | /api/auth/login | JSON 含 username、password，成功回傳 access_token。 |
| GET | /api/auth/me | 帶 Authorization: Bearer 憑證，取得 user_id、username、role、approval_status。 |
| POST | /api/auth/logout | 帶原憑證，撤銷此登入。 |
| GET | /api/admin/pending | 管理員查詢待審帳號。 |
| POST | /api/admin/users/{user_id}/review | 管理員送出 status 為 approved 或 rejected。已處理的申請回傳 409。 |

從 `app.auth` 匯入 `current_user` 或 `admin`，搭配 FastAPI 的 `Depends` 使用。兩者優先讀取 Bearer 憑證，瀏覽器則可用登入表單設定的八小時 HttpOnly Cookie（`access_token`）。登出會撤銷伺服器端憑證。頁面繼承 `templates/base.html`，使用 `app.pages.page` 傳入登入者和表單 CSRF 欄位。修改資料的網頁表單用 `Depends(verify_form)` 驗證；以 Cookie 呼叫需登入的寫入 API 時，將頁面表單的 `csrf` 值放入 `X-CSRF-Token` 標頭。Bearer 用戶端維持原呼叫方式。

## 名單範圍

教室清單按樓層顯示校方公開封面，點選教室可查設備、管理單位及借鑰匙說明。教室詳情透過 `room_id` 關聯 `room_profiles`。同步後執行 `python api/manage.py init` 建表並補入校方資料，重跑會保留已維護的詳情。照片由校方網站載入，詳情頁提供原始資料連結。

管理員可在詳情頁選「編輯教室資料」修改名稱、樓層、容量、設備、管理單位與借鑰匙方式。單獨啟動本模組時，詳情頁顯示「借用功能待整合」。掛載借用模組的 `calendar_page` 路由後，詳情頁會自動顯示借用入口並帶入目前的 `room_id`。

360° 檢視工具待選定。有該教室的實拍全景時，將可嵌入的 HTTPS 導覽網址或同站檢視器路徑寫入該教室的 `panorama_embed_url`；空值會顯示一般照片與待補提示。

管理員從教室詳情頁進入「管理這間教室的照片」，可上傳、更換或移除封面及詳情照片。上傳的圖片會轉成 WebP，和對應的教室編號一起保存在 PostgreSQL。移除詳情照片後，公開頁會優先以現有封面補位。

取自[暨大國企系教室空間](https://www.ibs.ncnu.edu.tw/index.php/resources/space-classroom)三頁目錄，收錄教室、研討室、會議室及會議廳共 34 筆，含管 B11、B15。排除教 A 系列、辦公室、研究室與咖啡空間。容量採目錄標示；管 451 在目錄為 20 人，[資管系預約系統](https://newroom.im.ncnu.edu.tw/)標示 12 人，暫以空值表示待確認。借用與排課資格也使用空值表示待確認。借用資格待確認時仍可送件，由管理員依序分發。
