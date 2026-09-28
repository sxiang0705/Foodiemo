# 2026-09-28 管理員控制台與推薦紀錄測試

## 驗證範圍

- 後端管理 API、檢舉 API、推薦執行／事件保存、`0007_admin_console` 與 `0008_email_less_first_admin` migrations，以及離線首管密碼輪替工具。
- 管理員控制台與個人頁管理員入口的 JavaScript 語法。
- 隔離資料庫使用專案指定 `.env.test`；測試資料在外層交易後回滾。

## 結果

| 檢查 | 結果 |
| --- | --- |
| `scripts/test.py` | 通過，50 項 |
| `scripts/test.py --integration` | 通過，22 項；包含 migration 重複執行、一般未驗證帳號拒絕登入、唯一無 Email 首管登入、首管角色保護、受限密碼輪替／舊 Token 撤銷／稽核、管理權限、檢舉與推薦事件流程 |
| `python -m compileall -q backend/app tests scripts` | 通過 |
| Node `--check` 管理頁內嵌 JavaScript | 通過 |
| `git diff --check` | 通過；Git 僅提示目前檔案的 LF／CRLF 慣例 |
| `scripts/check_source.py` | 未通過：檢查器回報原始前端基線 `edit.html` 雜湊與 `frontend-baseline.json` 不一致。管理功能未修改原始前端目錄，因此保留基線與原始檔，未以新雜湊覆蓋檢查基準 |
| 正式資料庫完整備份與隔離還原 | 通過：`backups/20260927_185115`，SHA-256、schema 及 25 張表筆數均符合，還原至新隔離資料庫驗證成功 |
| 正式資料庫 `0008_email_less_first_admin` | 通過：guarded 預檢及 transaction migration 成功；唯讀後驗證 PostgreSQL 9.5.25、版本 `0008_email_less_first_admin`、25 張表 |
| 首位管理員帳號 | 通過：互動式隱藏密碼輸入建立 `admin001`；Email 為 NULL、`email_auth_exempt=true`、角色為 admin、狀態 active；密碼只保存 scrypt 雜湊 |

## 功能檢查內容

- 一般使用者呼叫 `/api/admin/*` 得到 403，未登入得到 401；角色權限由後端驗證。
- 停用帳號會撤銷 Session；管理員角色調整使用交易鎖，避免並行操作移除最後一位管理員。
- 管理員可搜尋帳號、貼文、留言與檢舉；停用／恢復帳號、隱藏／恢復貼文或留言、審理檢舉都要求原因並留稽核資料。
- 管理員可從檢舉佇列檢視檢舉對象與貼文照片，並直接對目標執行適用的停用或內容審核操作。
- 留言審核使用 `moderation_hidden` 獨立欄位；解除管理隱藏不會復原使用者刪除的留言。
- 登入者每次推薦回應都記錄演算法版本、請求情境、結果排序與 score/reasons；卡片曝光、詳情與地圖點擊按 run 和餐廳 ID 關聯。匿名推薦仍可讀取，但不保存使用者推薦紀錄。
- 唯一無 Email 首管可登入管理頁；一般未驗證帳號仍無法登入。資料庫約束阻止第二個 Email 豁免帳號，管理 API 也拒絕移除此首管的 admin 角色。該帳號無 Email 密碼復原。
- 離線輪替工具只允許 `email_auth_exempt=true` 的無 Email 首管；更新密碼與撤銷所有舊 Token 在同一交易中完成，並留下不含密碼的稽核紀錄。未在正式資料庫執行密碼輪替。

## 正式套用狀態

正式庫的 `0007_admin_console` 與 `0008_email_less_first_admin` 均在完整備份、隔離還原及 guarded 預檢後以 transaction 套用。第二份備份 `backups/20260927_185115` 確認 25 張表 checksum、schema 與筆數相符。唯讀後驗證確認正式版本 0008、25 張表；首管建立後只核對指定 username、顯示名稱、Email 是否為 NULL、驗證豁免旗標、角色及狀態，未讀取 Email 值或密碼雜湊。Email 豁免僅限一筆 admin 帳號，一般註冊與未驗證帳號登入規則不變。首管無 Email 忘記密碼流程；新增的離線維護工具已在隔離整合測試驗證，未用來修改正式帳號密碼。
