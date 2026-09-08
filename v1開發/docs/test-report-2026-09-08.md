# 第一批驗收報告

測試日期：2026-09-08（Asia/Taipei）  
程式版本：0.1.0；對應本機 Git 的第一批開發 commit，可用 git log -1 核對。  
測試範圍：《v1測試流程》A、B 類及餐廳瀏覽，不涵蓋階段 2–6。  
程式快照：42 個程式／設定檔，SHA-256 `5cfa86aebf679dc6c855bac55b6d970f07ac647b8fdfbc9ed6b38244777aff93`。  
快照按 backend、frontend、migrations、scripts、tests 下的 py/js/cjs/html/css/sql/ps1，以及 requirements.in、requirements.lock、package.json、pnpm-lock.yaml、alembic.ini、pytest.ini，以相對路徑排序後雜湊「路徑 + NUL + 原始 bytes + NUL」，排除 __pycache__。文件不納入快照。

## 環境與資料保護

- PostgreSQL：9.5.25；應用來源 project_db，隔離測試 foodiemo_v1_test。
- migration：0001_baseline；正式庫只新增版本表，既有 14 張應用表未重建。
- 後端：Windows、Python 3.12、FastAPI 0.115.12、SQLAlchemy 2.0.40、psycopg2-binary 2.9.10；完整固定版本見 requirements.lock，pip check 通過。
- 備份／還原工具：遠端 pg_dump／pg_restore 9.5.25。
- 照片測試位置：test-uploads/，與正式位置分離；本批尚無上傳功能，沒有建立照片測試檔。
- 瀏覽器：Microsoft Edge 152.0.4191.66，Playwright 1.62.1；桌面 1280×900、模擬窄螢幕 390×844。
- 原始 DEMO 與歷史文件未修改；.env、.env.test、備份、SSH known_hosts、測試截圖與上傳位置被 Git 排除。
- GitHub 遠端唯讀查詢成功，目前未回傳 refs；本次建立本機 Git 基線，未推送。

## 執行結果

| 檢查 | 結果 |
| --- | --- |
| scripts/test.py | 22 通過 |
| scripts/test.py --integration | 9 通過，使用真正 PostgreSQL |
| tests/browser.cjs | 17 項斷言通過 |
| tests/live_smoke.cjs | 真實 DB → API → 列表 → ID 詳情 → 關閉通過 |
| scripts/remote_backup.py | 完整備份及新隔離 DB 還原通過 |
| scripts/stamp_existing.py | 即時 Schema／備份核對與版本標記通過 |
| scripts/check_source.py | Git 候選檔案沒有本機帳密、私鑰或排除資料 |
| python -m pip check | 無相依衝突 |
| Tunnel 實際中斷與恢復 | 2.16 秒內回 503，恢復後 health 200、餐廳瀏覽正常 |
| 測試清理 | 整合／瀏覽器測試餐廳剩餘 0 筆 |

22 個單元測試包含 HTTP 合約替身及真實不可連接埠的錯誤測試；**不以替身宣稱 DB 整合成功**。9 個整合測試使用實際 PostgreSQL 9.5.25，瀏覽器測試連到 8001 隔離資料庫 fixture 服務；503 的畫面分支採受控 HTTP 回應，離線分支採瀏覽器 offline。另有實際 Tunnel 中斷與真實資料瀏覽測試補足連線驗證。

## A 類案例對照

| 案例 | 狀態 | 實際證據與限制 |
| --- | --- | --- |
| ENV-01 | 通過 | 後端核對 DB、版本、欄位、CHECK／FK／UNIQUE／索引、角色與逐表權限；交易 readonly=on，不輸出資料列或雜湊 |
| ENV-02 | 通過 | 缺設定／非法埠立即失敗；無 SQLite fallback；無法連線回 503 |
| ENV-03 | 通過 | 停止本批後端 Tunnel，API 2.16 秒回 DATABASE_UNAVAILABLE；重建 Tunnel 後恢復；前端離線／重試也通過 |
| ENV-04 | 通過 | custom-format 全庫備份，於全新隔離 DB 還原；14 張表 Schema、逐表筆數相同，所有外鍵與 CHECK 成功還原 |
| ENV-05 | 通過 | 即時結構與匯出 baseline 完全一致後 stamp；既有資料表未重建；後續唯讀再次核對通過 |
| ENV-06 | 通過 | 空測試庫建立 14 張表、sequence、trigger 等完整結構；upgrade head 重跑不重建 |
| ENV-07 | 通過（備份還原策略） | 已實際於新隔離 DB 還原並核對；baseline downgrade 明確拒絕刪表。未執行正式庫覆蓋切換，也不宣稱後續 migration 的 downgrade 已驗證 |
| ENV-08 | 通過 | 正式名稱、錯誤環境、主機、埠、缺標記皆拒絕；伺服器端資料庫註解也在每次測試寫入前核對 |

備份保存於本機 backups/20260908_070431/，隔離還原資料庫 foodiemo_v1_restore_20260908_070431 保留核對。只記錄本輪觀測值，不將正式 158 間餐廳／30,420 則評論作為自動化測試固定斷言。

## B 類案例對照

| 案例 | 狀態 | 實際證據 |
| --- | --- | --- |
| REST-01 | 通過 | 固定 ID 排序、名稱／地址、精確分類、分頁、參數界限、%／_ 文字搜尋；瀏覽器換頁及重整保留頁數 |
| REST-02 | 通過 | 非連續 ID 正確查詢、不存在為 404、超過 bigint 範圍為 422；瀏覽器詳情 ID 與真實 API 一致 |
| REST-03 | 通過 | null、空營業時間、無照片／評分／價位均明示，無 undefined／假評分；窄螢幕詳情可閱讀 |
| REST-04 | 通過 | 大小寫 DB 欄位、HTML 特殊字元名稱與評論顯示為文字；javascript: 網站不生成連結 |
| REST-05 | 通過 | 空結果清除舊卡片；503／offline 與空資料分開；重新載入恢復；頁面沒有 JavaScript 例外 |
| REST-06 | 通過 | 評論匯入 created_at 不對外冒充發布時間；rating／published_at=null；來源評論數與保存筆數分開 |

## 失敗、修正與重測

1. 第一輪隔離檢查讀取 DB 註解時用了 obj_description，導致安全入口拒絕所有測試寫入。修正為 PostgreSQL 共用目錄所需的 shobj_description，再執行整合測試。
2. JSONB 測試字串中的冒號被 SQLAlchemy 當成參數。改為 CAST(:payload AS jsonb) 與綁定值；9 個整合測試全數通過。
3. 窄螢幕截圖原先誤等到背景卡片標題，截圖仍是「正在載入」。改為等待 dialog 內的標題及評論，再重跑 17 項瀏覽器斷言，重新檢視截圖。
4. 自動化瀏覽器控制元件啟動失敗，改用 bundled Playwright 搭配 Edge；實際畫面與操作已驗證，並非僅語法檢查。
5. Windows 沙箱在初始化 Git 後出現 setup refresh helper 錯誤；後續以受審核的專案命令完成檔案讀寫與測試。沒有自動核准審查拒絕導致的未完成操作。

測試工具另顯示一則 Starlette／AnyIO BlockingPortal 棄用警告，未影響本輪結果；後續調整框架版本時應一併處理。

## 未完成與限制

- C–G 類案例（帳號、收藏／紀錄／照片／日曆、社群、推薦、模擬會員）全部標記「未執行／待實作」，屬於文件規定的後續批次。
- 手機實機觸控、其他瀏覽器、HTTPS 對外部署、服務開機重啟未驗證；本輪窄螢幕是模擬 viewport。
- 原始營業時間表為空；weekday 的星期起算規則未確認，不猜測星期或即時營業狀態。
- 正式應用目前沿用既有 DB 角色，FastAPI 強制唯讀；後續寫入階段需檢討應用與 migration 角色分離。
- 原始 Schema 的全庫結構已保存；本批只建立查詢需要的 3 張表 ORM，其餘 ORM 按後续階段補齊。
- 只有本次用到的 PostgreSQL 9.5.25 功能完成實測，未概括保證新版資料庫或後續套件升級相容。
- 備份和還原驗證資料庫刻意保留；沒有上傳 GitHub，也沒有將備份內資料用作測試 fixture。

截圖位於忽略的 test-results/：desktop.png、mobile.png、mobile-detail.png、empty.png、error.png、live-desktop.png。可作為本機驗收證據，截圖不包含帳密或會員資料。
