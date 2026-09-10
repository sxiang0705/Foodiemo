# v2 第一批開發／測試紀錄

日期：2026-09-09（Asia/Taipei）。範圍為開發流程階段 0／1 的原版複本、唯讀餐廳推薦、工具與自動化驗證。完整 v2 尚未完成；手機實機與部分原版子頁互動尚待驗收。

## 結果

| 驗證 | 結果 | 限制 |
| --- | --- | --- |
| scripts/test.py | 45 項通過 | 單元與 TestClient；無 DB 連線的測試不代表 PostgreSQL |
| scripts/test.py --integration | 8 項通過 | 真實 PostgreSQL 9.5.25，僅 foodiemo_v2_test |
| V2_LIVE=1 node tests/browser.cjs | 36 項檢查通過 | 34 項人工 fixture／瀏覽器控制；2 項 LIVE PostgreSQL |
| scripts/live_smoke.py | 通過 | API 三筆店名／地址逐筆對 DB、輪替、唯讀及正式基線 |
| scripts/check_source.py | 通過 | 37 個來源檔案保留核對；僅 3 個繼承檔案允許必要改動；無本機連線機密 |
| node tests/baseline.cjs | 15 組其他頁面截圖完成 | 人工 fixture、封鎖外部素材；不等同功能驗收 |
| 原版推薦頁視覺對照 | 通過 | 390×844，同 fixture；幾何、樣式相同，最後一輪像素差異 0 |
| 手機實機 | 未驗證 | 相機、軟鍵盤、巢狀側滑仍須實機 |

以上是不同層次的檢查數量，不代表測試流程中的 90 個案例已全部完成。Python 測試有一則 Starlette／AnyIO deprecated alias 警告，沒有失敗；依鎖定版本保存，未因此無目的升級相依套件。

## 資料庫與備份證據

- VPN 啟用前 SSH 逾時；使用者開啟校內 VPN 後重新建立獨立 v2 Tunnel。
- 主機的 PostgreSQL 9.5.25，project_db 15 張 public 表（14 張應用表及 alembic_version）。
- 本批正式連線 transaction_read_only=on；正式版本仍為 0001_baseline，未新增或修改正式 Schema。
- 唯讀盤點餐廳 158 筆、business_hours 0 筆。照片、評分、價格沒有可靠欄位，不產生假值；營業時間尚不能提供。
- 新備份：backups/20260908_165928/project_db.dump（UTC；台灣時間 2026-09-09 00:59:28）。
- 新還原庫：foodiemo_v2_restore_20260908_165928。完整 Schema 與逐表筆數均相等；原備份及 manifest 的 SHA-256 存在本機忽略目錄。
- 新建 foodiemo_v2_test、foodiemo_v2_test_owner，角色不是 superuser、不可建 DB／角色。精確資料庫註解 foodiemo-v2-isolated。正式、v1、還原庫不能通過功能測試寫入入口。
- v2 測試庫已套用同一 0001_baseline，重跑 upgrade 不重建表。人工候選資料在交易結束 rollback，最後核對餐廳 fixture 筆數為 0。
- 基線 downgrade 明確拒絕刪表；本批回復驗證採新隔離庫還原，不覆蓋任何既有資料庫。備份時若有同時寫入導致筆數差異，腳本會失敗，不能冒稱一致。

## 本批覆蓋

- ENV-01／02／04–10：盤點、缺設定、保護正式資料、備份還原、版本、測試庫／角色／路徑防呆。ENV-03 的真實 VPN 中斷／恢復已觀察，瀏覽器錯誤／逾時恢復另外使用可控制替身；未刻意在 SQL 執行中切斷線路。
- UI-01–05、07–09：原登入 gate、三 iframe 首頁、指定 tab、主容器事件／鎖定／resize、幾何樣式與原控制。UI-06 的手機巢狀手勢尚未實機驗證。
- REST-01–12：3 間、觸控／滑鼠下拉、門檻、非頂端、整批替換、詳情、地圖、字串 bigint、安全文字、缺值、0／1／2／3／7 筆候選、舊回應／逾時／重試、來源映射；部分是單元或 fixture 驗證，真實讀取另列 LIVE。
- D–H：未列本批功能通過。僅基礎推薦提供者的替換點與安全輸出部分有單元測試，不代表偏好、run／items 或事件已實作。

## 原版保留與已修問題

原始資料夾與 v1 程式未修改。推薦 CSS、靜態可見控制逐字相同；只有 config.js、search.html、sw.js 的必要串接調整。來源與 v2 雜湊詳見 frontend-baseline.json。

修正前端 API helper 曾與 /api/* 衝突，改由 /static/api/client.js 載入，並補上靜態載入回歸。原版字串拼 HTML 改安全節點；重複下拉具取消與最新序號保護。沒有新增搜尋欄、分頁控制或更換主入口。

其他 15 組基線截圖中的 edit.html 因測試封鎖外部 unpkg 而記錄 lucide is not defined，原版與 v2 都有相同限制；不將缺圖示的截圖當成編輯流程完成。原版未完成的按讚／通知／標記等示意尚保留。

## 證據位置

Git 忽略的 test-results 包含：

- original-search.png、v2-search-fixture.png、visual-comparison.json。
- v2-live-search.png、v2-live-detail.png、v2-error.png。
- v2-original-home-fixture.png、browser-result.json、live-result.json。
- baseline/：15 組原版／v2 截圖及人工資料、外部素材限制清單。

未提交或推送 Git。下一批依開發流程處理帳號、OTP、個資與六題偏好持久化，仍須保留原畫面與路徑。


程式快照 SHA-256（frontend／backend／scripts／tests／migrations，排除 __pycache__）：b16de09fcfdee165b81e8c86088921252a81a2a4464c7cf44b93c40d8f47be4f。
