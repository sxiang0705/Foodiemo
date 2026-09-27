# 2026-09-28 管理員控制台與推薦紀錄測試

## 驗證範圍

- 後端管理 API、檢舉 API、推薦執行／事件保存、`0007_admin_console` migration。
- 管理員控制台與個人頁管理員入口的 JavaScript 語法。
- 隔離資料庫使用專案指定 `.env.test`；測試資料在外層交易後回滾。

## 結果

| 檢查 | 結果 |
| --- | --- |
| `scripts/test.py` | 通過，50 項 |
| `scripts/test.py --integration` | 通過，20 項；包含 migration 重複執行、管理權限、使用者／貼文／留言查詢、檢舉提交與重複拒絕、留言隱藏／恢復、檢舉結案、推薦 run／score／reason／曝光／詳情事件與稽核紀錄 |
| `python -m compileall -q backend/app tests scripts` | 通過 |
| Node `--check` 管理頁內嵌 JavaScript | 通過 |
| `git diff --check` | 通過；Git 僅提示目前檔案的 LF／CRLF 慣例 |
| `scripts/check_source.py` | 未通過：檢查器回報原始前端基線 `edit.html` 雜湊與 `frontend-baseline.json` 不一致。管理功能未修改原始前端目錄，因此保留基線與原始檔，未以新雜湊覆蓋檢查基準 |
| 正式資料庫完整備份與隔離還原 | 通過：`backups/20260927_182704`，SHA-256、schema 及 23 張表的筆數均符合，還原至新隔離資料庫驗證成功 |
| 正式資料庫 `0007_admin_console` | 通過：guarded 預檢及 transaction migration 成功；唯讀後驗證 PostgreSQL 9.5.25、版本 `0007_admin_console`、25 張表；`content_reports` 與 `admin_audit_logs` 均為 0 筆 |
| 首位管理員帳號 | 尚未設定：使用者提供的識別值未匹配到既有帳號；bootstrap 僅接受既有、啟用且已驗證帳號，不會建立未驗證帳號 |

## 功能檢查內容

- 一般使用者呼叫 `/api/admin/*` 得到 403，未登入得到 401；角色權限由後端驗證。
- 停用帳號會撤銷 Session；管理員角色調整使用交易鎖，避免並行操作移除最後一位管理員。
- 管理員可搜尋帳號、貼文、留言與檢舉；停用／恢復帳號、隱藏／恢復貼文或留言、審理檢舉都要求原因並留稽核資料。
- 管理員可從檢舉佇列檢視檢舉對象與貼文照片，並直接對目標執行適用的停用或內容審核操作。
- 留言審核使用 `moderation_hidden` 獨立欄位；解除管理隱藏不會復原使用者刪除的留言。
- 登入者每次推薦回應都記錄演算法版本、請求情境、結果排序與 score/reasons；卡片曝光、詳情與地圖點擊按 run 和餐廳 ID 關聯。匿名推薦仍可讀取，但不保存使用者推薦紀錄。

## 正式套用狀態

正式完整資料庫備份已建立並還原至新隔離資料庫驗證。備份來源及還原筆數均為 23 張舊版資料表，checksum 與 schema 相符。正式庫先通過 guarded 預檢，再交易式套用 `0007_admin_console`；唯讀後驗證確認版本為 0007，新增兩張管理資料表後總數 25 張。未從正式資料庫讀取使用者資料列來做版本核對以外的檢查；帳號 bootstrap 查詢只搜尋使用者提供的兩個識別值及其啟用／驗證狀態欄位，未匹配到帳號，也未讀取 Email 或密碼雜湊。設定首位管理員前，需有一個已註冊、啟用且完成 Email 驗證的帳號，並確認其登入 username。
