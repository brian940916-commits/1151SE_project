# 排課後端驗證紀錄

測試日期：2026-11-26。來源：使用者提供的 1151SE_project-main.zip。

## 實際環境
- Windows、Python 3.12.14、PostgreSQL 17.11。
- 套件安裝於獨立 .venv，未交付此環境。
- 獨立本機 PostgreSQL 測試 cluster，與使用者既有資料庫分開；測試庫名稱 scheduling_test。
- 自動測試將排課時計凍結於 2027-01-01，個別歷史資料測試再前進時間；實際服務採臺灣當地時間。

## 結果
`python -m pytest -q --tb=short`：**28 passed, 1 warning**，64.34 秒。

涵蓋每週重複、邊界日期、跨週例外、相鄰區間、角色與所有權、老師指派、志願增改刪、依志願 ID 確認、志願衝突清單、正式教室/教師衝突、待審與核准/退回、單次/後續調課、例外還原、舊版本阻擋、歷史保護、平行核准防撞期，以及同時調課時週查詢的一致性。使用真實 PostgreSQL，未用假資料庫替代。

既有 API 回歸：老師註冊→管理員核准→登入→查身分→建課，及公開教室清單。

初次 HTTP smoke：實際 Uvicorn 提供 `/docs`、`/openapi.json`、`/api/rooms`，確認 34 筆教室；CLI `init` 連跑兩次正常。交付前再執行同一 HTTP smoke。

`python -m pip check`：No broken requirements found。

測試有一則 Starlette 提醒：目前版本的 TestClient 使用 httpx 即將棄用，建議未來採 httpx2。這是測試工具的相容性提醒，本次 28 項測試均成功；未為消除提示而任意替換測試工具。

## 程式碼檢查
由獨立 reviewer 檢查。其發現的歷史改派、延遲核准、志願確認、極端日期、角色檢查順序及讀取快照一致性問題皆先寫出失敗回歸測試，再修正至通過，並重跑全部測試。沒有提交 Git、推送或合併 PR。

## 仍有的限制
- Python 3.11 尚未實際測試，本次實測為 3.12.14。
- 借用模組尚未提供，跨借用防撞期與管理員協調通知尚未整合。
- 沒有網頁、CSS、拖曳 UI；以 /docs 操作。
- Cookie 登入頁、CSRF 表單與 SQLAlchemy 共用連線池尚待團隊其他模組完成。
- 有歷史安排的課程不允許整門改派老師，避免覆寫既有歷史；可另建新課程處理未來安排。
- 所有測試是在來源 ZIP 上整合；若 GitHub 後續已有其他修改，main.py、requirements.txt 等共用檔案必須比較後再合併。
