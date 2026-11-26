# 1151 軟體工程學期專案

**組員開工前必讀**　[純 Python 全端重構協作契約](docs/refactor-contracts.md)列出共用技術、登入方式、樣板和目錄。[團隊開發規範](docs/team-guidelines.md)記錄分工、共用資料與業務規則。

- 管院空間查詢
- 空間／物品預約借用
- 志願排課

## 共用登入與管院教室清單

訪客可瀏覽教室。學生註冊後可立即登入；老師帳號須由管理員在「帳號審核」核准後才能登入。登入後可讀取目前身分並登出。管理員從本機命令建立。公開註冊帳號限 3–40 個英數字、點、底線或短橫線，大小寫視為相同。密碼長度 8–128 字元。

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

服務啟動後，可在瀏覽器開啟 `http://127.0.0.1:8000/docs`，測試 `GET /api/rooms`。目前 `main` 已提供帳號與教室 API，`web/` 是待遷移的舊版頁面；各模組的 Jinja2 頁面會隨後續提交加入。

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

其他模組的 FastAPI 路由可透過 Depends(current_user) 取得已驗證身分。需要管理員的操作使用 Depends(admin)。新網頁依重構契約使用共用 Jinja2 樣板與瀏覽器登入機制。身分以 API 驗證結果為準。

## 名單範圍

取自[暨大國企系教室空間](https://www.ibs.ncnu.edu.tw/index.php/resources/space-classroom)三頁目錄，收錄教室、研討室、會議室及會議廳共 34 筆，含管 B11、B15。排除教 A 系列、辦公室、研究室與咖啡空間。容量採目錄標示；管 451 在目錄為 20 人，[資管系預約系統](https://newroom.im.ncnu.edu.tw/)標示 12 人，暫以空值表示待確認。借用與排課資格也使用空值表示待確認。借用資格待確認時仍可送件，由管理員依序分發。
