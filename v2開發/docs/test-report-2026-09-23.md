# 2026-09-23 帳號識別功能測試紀錄

- 版本：v2.2.1
- 正式資料庫：PostgreSQL 9.5.25，migration `0006_usernames`
- 正式資料變更前備份：`backups/20260923_092736`；備份 checksum、schema、筆數核對及還原至新隔離資料庫均通過。
- 正式套用方式：`scripts/apply_0006_existing.py` 以備份 manifest、hash、schema、筆數及前置 revision 驗證後，transaction 套用。
- 套用後唯讀驗證：`transaction_read_only=on`、username 為 NOT NULL、唯一索引存在、username 無 NULL、23 張表筆數與備份相同。只執行 metadata／筆數查詢，未讀取使用者資料列。

## 自動測試

- `python scripts/test.py`：50 passed。
- `python scripts/check_source.py`：原版前端保護、搜尋頁 UI 與機密掃描通過。新增 profile handle 樣式已在來源保護工具中列為明確授權的新增樣式。
- `python scripts/migrate.py upgrade --env-file .env.test`：隔離測試資料庫升級成功。
- `python scripts/test.py --integration`：19 passed，涵蓋 migration 重複執行、帳號與 Email 相容登入、名稱修改、唯一性／格式、好友搜尋、Email 欄位排除及既有帳號功能。
- `python tests/run_browser_features.py`：帳號相關真瀏覽器檢查通過：註冊／OTP、帳號登入、個人頁修改與保存、好友帳號搜尋、邀請批准、聊天、既有多圖貼文。全套流程之後在月回顧 `.hero` 元素等待逾時，且未出現 JavaScript 例外；因此後續月回顧、留言、回憶測試未跑完，該故障與本次帳號變更尚無關聯證據。

## 功能核對

- 新會員註冊必須選擇 3–30 字元唯一 username；格式為小寫英數字、底線及句點，Email OTP 不變。
- 舊會員自動獲得 `foodie_{user_id}` 初始 username；穩定 user_id 不變，既有貼文、好友與聊天關係不變。
- 登入 API 接受 `identifier`（帳號或 Email）；舊 `email` 欄位仍相容。忘記密碼與 OTP 一律使用 Email。
- 好友搜尋公開帳號；個人 Email 不出現在好友、聊天對象或貼文 API 回應中。
