# 志願排課後端：啟動、測試與整合

這版只有後端，沒有網頁、週曆畫面、拖曳操作與 CSS。以 FastAPI `/docs` 測試 API，之後網頁可直接呼叫同一套 API。

## 1. 這版能做什麼
- 老師新增、列出、修改、刪除自己的課程，填寫多筆希望時段。不能讀寫他人課程；學生不能使用排課管理 API。
- 管理員列出所有課程及已核准老師、指派老師、確認正式週課表。
- 為保留歷史，課程只要已有開始上課的紀錄，就不能直接改派整門課的老師（409）；請建立新課程處理後續安排。已停用系列也不會因改派而覆寫老師。
- 希望時段不占用教室；正式週課表才占用。檢查同教室或同老師的實際重疊日期與時間，相鄰時段允許。
- 查任意連續七天的正式課表，以及管理員的正式/志願衝突清單。
- 提出單次或後續每週調課，管理員核准/退回。核准前保留原課表；核准時重新檢查衝突及版本。單次移動可跨週但須在原學期區間；後續新系列保留原學期結束日。
- 刪除已有正式課表的課程時停用並釋放占用，資料保留可追溯；沒有正式課表的課程可刪除。課程停用後不可再新增志願或核准排課。

假設：日期與時間採 Asia/Taipei；星期一=0、星期日=6；不支援跨午夜。起訖日期包含首尾，區間最多 366 天，且至少有一天指定星期。假日不自動停課。沒有自動依志願順位分配功能。正式排課與調課不可改寫已開始的課；提出申請、核准時都檢查臺灣當地時間。已調過的單次課以目前有效安排的日期時間判斷。

## 2. 安裝與啟動
需要 Python 3.11+、PostgreSQL。先在 PostgreSQL 建立自己的專用開發資料庫及具建表權限的帳號。

在專案根目錄 PowerShell 分行執行：
```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```
僅第一次建立 `.env` 時執行 Copy-Item；已存在時直接編輯。將 DATABASE_URL 改成自己的連線資訊，不上傳 `.env`。

```powershell
.\.venv\Scripts\python.exe api/manage.py init
.\.venv\Scripts\python.exe api/manage.py create-admin myadmin
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --host 127.0.0.1 --port 8000
```
在瀏覽器開啟 http://127.0.0.1:8000/docs 。如果 `py` 不存在，改用自己安裝的 Python 執行檔，建立自己的 `.venv`，不要複製別人的虛擬環境。

根目錄 requirements.txt 補上既有 db.py 原本就需要的 python-dotenv。共用資料庫仍沿用 psycopg；SQLAlchemy 連線池重構尚待全組統一，不在本模組另建第二套連線。

## 3. 用 /docs 走一遍
1. `POST /api/auth/register` 註冊老師，role 填 teacher，帳號會 pending。
2. `POST /api/auth/login` 用命令建立的管理員登入，複製回傳的 access_token。
3. 點 `/docs` 的 Authorize，在 HTTPBearer 欄位只貼 token 本身。執行 `GET /api/admin/pending`，記下老師的 user_id，再呼叫帳號 review API 核准。
4. 老師登入，換成老師 token。呼叫 `POST /api/scheduling/courses`，送出 `{"title":"軟體工程"}`，記下 course_id。
5. 呼叫該課程的 preferences POST，送出下方時段。志願可以重疊，不會直接占用。
6. 管理員登入並替換 Authorize token；確認教室有排課資格，再呼叫 courses/{course_id}/preferences/{preference_id}/confirm POST，直接依該志願目前的內容建立正式週課表。亦可使用 courses/{course_id}/series POST 手動指定時段。管理員要代建課程時，先 GET /teachers 取得 user_id，並於課程新增/修改輸入 teacher_id。
7. GET /calendar：week_start 填 2027-02-01，顯示這天起七天；並非強制星期一。
8. 老師或管理員呼叫 series/{series_id}/changes POST 提出調課。管理員用 changes/{change_id}/review POST 核准或退回。未核准時正式課表不變。

時段範例：
```json
{
  "room_id": 1,
  "start_date": "2027-02-01",
  "end_date": "2027-06-30",
  "weekday": 1,
  "start_time": "10:00:00",
  "end_time": "12:00:00"
}
```
實際 room_id 從 GET /api/rooms 取得，不假設正式資料庫的 ID 與測試相同。
範例日期若已經過去，請替換成未來學期的日期並確認星期一致。

**教室資格：** 目前 seed 的 is_schedulable 全是 NULL。志願可先填，但正式排課回傳 409。需請空間主責確認並更新資格。在自己的開發測試資料庫，可由管理員用 PostgreSQL SQL 工具對已確認的測試教室設定，例如：
```sql
UPDATE rooms SET is_schedulable = true WHERE room_code = '管212';
```
此 SQL 只供本機測試，不是對真實教室資格的認定，也不修改共用 seed。

單次調課範例（原本 2027-02-02 週二，移到下週三）：
```json
{
  "scope": "single",
  "effective_date": "2027-02-02",
  "new_date": "2027-02-10",
  "new_weekday": 2,
  "room_id": 1,
  "start_time": "14:00:00",
  "end_time": "16:00:00",
  "note": "老師申請原因"
}
```
後續每週調課將 scope 改成 future，effective_date 是原系列開始受影響的上課日，new_date 是新系列第一個上課日，必須不早於生效日且在原學期內，之後依 new_weekday 重複。

審核輸入：`{"status":"approved","note":"管理員處理意見"}`，退回使用 rejected。回傳 note 保留申請原因，review_note 保存審核意見。

若後續調課碰到已核准單次例外，回傳 409，不會靜默覆蓋。先協調並提出 single 變更，將該次課的日期、教室、時間全部恢復成原週課表；核准後便會清除有效例外，審核歷史仍保留。之後可重新提出 future 申請。不要手改正式資料庫繞過衝突檢查。

## 4. API 清單
所有路徑前綴 `/api/scheduling`：

| 方法 | 路徑 | 用途 |
|---|---|---|
| GET | /teachers | 管理員取得已核准老師 ID |
| GET、POST | /courses | 列出／新增課程 |
| GET、PUT、DELETE | /courses/{course_id} | 查看／修改／刪除或停用課程 |
| GET、POST | /courses/{course_id}/preferences | 列出／新增志願 |
| PUT、DELETE | /courses/{course_id}/preferences/{preference_id} | 修改／刪除志願 |
| POST | /courses/{course_id}/preferences/{preference_id}/confirm | 管理員確認該筆最新志願 |
| GET、POST | /courses/{course_id}/series | 查看正式系列／管理員排定 |
| GET | /calendar?week_start=YYYY-MM-DD | 已登入老師、管理員看七天正式占用 |
| GET | /conflicts?week_start=YYYY-MM-DD&source=formal | 管理員看正式衝突 |
| GET | /conflicts?week_start=YYYY-MM-DD&source=preferences | 管理員看希望時段彼此衝突 |
| POST | /series/{series_id}/changes | 老師本人或管理員提出調課 |
| GET | /changes | 老師看自己的課程申請，管理員看全部 |
| POST | /changes/{change_id}/review | 管理員核准／退回 |

401 未登入、403 權限不足、404 不存在、409 衝突/待確認/版本已變、422 不合法資料。PUT 為完整更新，依 /docs 欄位填寫。

## 5. 共用檔案與借用整合
- main.py 僅新增 router 註冊，將 current_user/admin 抽到 app.auth 後保留相同匯入名稱。既有帳號 API 保留；logout 支援 Cookie 撤銷並清除 Cookie。
- current_user 優先檢查 Authorization，沒有 Header 才讀 access_token Cookie；無效 Header 不會退回 Cookie。登入 API 仍回傳 Bearer token，尚未代做帳號組的 Cookie 登入頁。這不是完整瀏覽器認證流程，未提供網頁/CSRF 表單機制。
- availability.calendar_events(db,start_date,end_date) 提供正式占用，每筆含 series_id、course_id、teacher_id、room_id、origin_date、date、start_time、end_time、title。
- 資料表為 courses、schedule_preferences、schedule_series、schedule_exceptions、schedule_change_requests。希望與正式分開，調課保存變更前快照與審核紀錄。
- 排課寫入先取得 advisory transaction lock `(1151,4)`，再以 user_id、room_id 遞增順序鎖定 users、rooms 資料列，於同筆交易重新讀取/檢查/寫入；目前採粗粒度鎖，優先保證小型學期專案的正確性。
- 週課表與衝突清單的唯讀交易採 REPEATABLE READ，避免同時調課時將不同版本的系列與例外拼在一起。
- **借用尚未接上。** API 回傳 booking_integration=not_connected。借用主責需共用相同鎖順序，核准借用前查正式課表；排課核准前也需加入已核准借用的查詢。借用的週期表示、狀態、取消與協調紀錄未定，不提供會假裝「沒有借用」的空查詢。
- 調課撞借用的通知、協調結果、正式資料更新，須等借用資料表與狀態確認後整合。未串接前，不可當成已完成跨模組防撞期。

## 6. 執行測試
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests/test_scheduling_time.py -q
```
整合測試使用獨立 PostgreSQL 資料庫，名稱**必須以 _test 結尾**，帳號須具重建 schema 權限：
```powershell
$env:SCHEDULING_TEST_DATABASE_URL = 'postgresql://測試帳號:測試密碼@127.0.0.1:5432/scheduling_test'
.\.venv\Scripts\python.exe -m pytest -q
```
**測試會清空此測試庫的 public schema。只可填專門建立、沒有重要資料的測試庫。** 未提供環境變數時，整合測試會明確 skip，不能把 skip 當成整合通過。

## 7. GitHub 上傳
先將最新 main 同步到 feature/scheduling。變更包只含相對於提供 ZIP 的新增/修改檔案，解壓縮後保留 api、database、docs、tests 的目錄層級上傳，不能把整個包套在另一層資料夾內。

main.py、requirements.txt 是共用檔案。若組員已更新，需合併各自的修改，不能用本版直接蓋掉新版本。不要上傳 .env、.venv、測試資料庫或快取。PR：base=main，compare=feature/scheduling。
