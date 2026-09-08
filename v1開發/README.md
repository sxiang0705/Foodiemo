# Foodiemo v1：第一批開發

本批依《v1開發流程》第 7 節完成階段 0、1 的程式與本機驗證：PostgreSQL 連線、完整 Schema 基線、備份還原、隔離測試、餐廳 API 與探索頁。帳號、收藏、貼文、推薦、會員屬於後續階段，介面沒有提供假的可用入口。

所有新增程式位於本目錄；原始 DEMO 與歷史文件未修改。Git 只追蹤審查過的 v1 檔案及根目錄忽略規則，避免歷史筆記或 DEMO 設定帶入機密。

## 現在可用

- 本機探索頁：[http://127.0.0.1:8000](http://127.0.0.1:8000)。
- 餐廳查詢、完整名稱分類篩選、店名／地址搜尋、分頁、詳情與原始評論分頁。
- 以真正 restaurant_id 查詢，URL 可保存搜尋、頁數及詳情；重新整理後維持位置。
- 缺少照片、地址、評分、價位、營業時間皆明示；文字不當成 HTML 執行。
- API 以唯讀交易存取 PostgreSQL。資料庫設定缺失直接失敗，沒有 SQLite 或假餐廳備援。
- 正式 DB 與測試 DB 都已標記 `0001_baseline`。正式 14 張應用表未重建，只新增 Alembic 版本表。

## 啟動（Windows PowerShell）

已建立的本機環境可直接使用 `.venv/Scripts/python.exe`。另一台電腦先安裝 Python 3.12 與 OpenSSH，於本目錄執行：

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.lock
Copy-Item .env.example .env
```

最後一行只在尚無 `.env` 時執行；在本機編輯 DB 與 SSH 設定。範例中的假值不能連線。不要把帳密放在瀏覽器、對話、Git 或命令列參數中。

第一個終端機建立 SSH Tunnel，主機與使用者改為自己的設定：

```powershell
./scripts/tunnel.ps1 -SshHost your-server.example -SshUser your-user
```

SSH 會提示輸入密碼，執行期間保持此終端機開啟。本機只監聽 `127.0.0.1:55432`，轉送至遠端 `127.0.0.1:5432`；與 DBeaver 的 Tunnel 分離。首次連線記錄 SSH 主機金鑰於忽略的 `.local/known_hosts`，後續金鑰變更會拒絕連線。

第二個終端機：

```powershell
./scripts/start.ps1
```

開啟 [探索頁](http://127.0.0.1:8000)。唯讀就緒檢查為 [health](http://127.0.0.1:8000/api/v1/health)，回傳 503 表示資料庫不可用。程式不在啟動時建表或執行 migration。

目前服務是本機開發用途，關閉終端機或重新開機後請重新啟動。正式部署需要另外配置 HTTPS、反向代理與服務重啟，見 [部署說明](docs/deployment.md)。

## 資料庫與備份

先閱讀 [資料庫操作說明](docs/database.md)，再執行以下操作：

```powershell
./.venv/Scripts/python.exe scripts/inspect_db.py
./.venv/Scripts/python.exe scripts/remote_backup.py
```

檢查腳本只輸出結構、版本與權限，不讀帳號資料列。備份腳本要求 SSH／sudo 密碼，使用遠端 PostgreSQL 9.5.25 的 pg_dump / pg_restore，保存完整 custom-format 備份，還原至全新隔離資料庫並比對 Schema 與逐表筆數；不覆蓋已有資料庫。

`.env.test`、`backups/`、`.local/`、`test-uploads/` 全部被 Git 忽略。本機已建立測試庫設定。新環境若沒有 sudo 權限，交由 Owner 依 `scripts/owner_setup.sql` 建立隔離資料庫與帳號。

## 執行檢查

```powershell
./.venv/Scripts/python.exe scripts/test.py
./.venv/Scripts/python.exe scripts/migrate.py upgrade
./.venv/Scripts/python.exe scripts/test.py --integration
./.venv/Scripts/python.exe -m pip check
./.venv/Scripts/python.exe scripts/check_source.py
```

整合測試僅接受 `.env.test` 指定的 `foodiemo_v1_test`、`APP_ENV=test`、精確主機／連接埠、寫入確認值，以及資料庫端的 `foodiemo-v1-isolated` 註解標記。任何條件不符就拒絕執行，不會在 project_db 測試寫入或清表。測試資料使用交易 rollback 清理；序號可能前進是 PostgreSQL 的正常行為。

瀏覽器測試需 Node.js、pnpm 11.19.0、Playwright 1.62.1 及 Microsoft Edge：

```powershell
pnpm install --frozen-lockfile
./.venv/Scripts/python.exe scripts/browser_server.py
```

在另一個終端機：

```powershell
pnpm test:browser
node tests/live_smoke.cjs
```

`browser_server.py` 只在 `127.0.0.1:8001` 提供隔離測試資料；Ctrl+C 後整批 rollback。不可同時在該連線執行其他測試。`live_smoke.cjs` 對 8000 的真實資料只讀餐廳清單與詳情，不寫資料。

若在本次 Codex 已有工具的環境重跑，Playwright 可透過 bundled Node 的 NODE_PATH 使用；一般開發機使用上面的 pnpm install --frozen-lockfile。

## 交接文件

- [測試結果與案例對照](docs/test-report-2026-09-08.md)
- [API 契約](docs/api.md)
- [資料庫、基線與回復](docs/database.md)
- [部署與後續範圍](docs/deployment.md)

本輪已驗證 Edge 桌面及 390px 模擬窄螢幕；手機實機觸控、其他瀏覽器與對外部署未驗證。實際營業時間表目前沒有資料，weekday 的星期起算方式未獲確認，介面不猜測對應星期。SQLAlchemy 2.0 對 PostgreSQL 9.5 屬 best-effort 範圍，本次所用查詢與 migration 已在 9.5.25 實測，後續功能須持續驗證相容性。
