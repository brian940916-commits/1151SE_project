# PR 標題
新增志願排課後端：課程、每週課表與調課審核

## 行為
老師管理自己的課程與希望時段，管理員指派老師並排定正式週課表。調課可只改一次或修改後續每週安排；核准前原課表有效，核准時檢查同教室/老師衝突、版本與同時寫入。尚未製作網頁、CSS 或拖曳 UI。

## 資料庫更新
新增 004_schedules.sql；使用 python api/manage.py init，SQL 可重複執行。教室 is_schedulable 須由空間主責確認，NULL 時不能正式排定。

## 共用修改
- main.py 註冊排課路由並引用 app.auth；舊帳號 API 保留。
- 共用認證抽至 app.auth，支援 Header 優先、Cookie 備援；logout 同步處理 Cookie。
- requirements.txt 補上既有 db.py 需要的 python-dotenv。
- 新增正式課表查詢與交易鎖介面，現有 users/rooms 欄位不變。

## 如何驗證
依 docs/scheduling-backend.md 安裝，在獨立 *_test PostgreSQL 資料庫執行 pytest；再依 /docs 範例走老師建課、管理員排定、週查詢、單次與後續調課流程。

## 尚待整合
借用資料表尚未提供，未檢查已核准借用、未做借用衝突通知/協調；不可視為跨模組整合完成。Cookie 登入頁與 SQLAlchemy 共用連線池待帳號/共用主責重構。本版不更動其他模組的資料表。
