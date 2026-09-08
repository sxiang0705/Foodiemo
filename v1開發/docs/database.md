# 資料庫、基線與回復

## 已確認狀態

2026-09-08 透過獨立 SSH Tunnel，以後端實際連上 project_db，版本 9.5.25。完整 public Schema 已匯出至 migrations/baseline.sql，包含 14 張應用資料表、12 個自增 sequence、主鍵、外鍵、唯一限制、CHECK、索引、updated_at trigger 與函式。精確結構以該 SQL 為準。

本批 ORM 對應 restaurant_rows、business_hours、reviews_rows；其他功能後續建立 ORM，完整結構現在已由 migration 保存。三個含大寫欄位以 SQLAlchemy 精確對應，不以 SQLite 取代。

目前應用仍使用使用者提供的既有 DB 角色，該角色具有較廣的應用表寫入權限；本批 FastAPI 連線強制 readonly。測試庫另有專用非 superuser、不可建 DB／角色的帳號。進入帳號與寫入階段前，應評估將正式應用角色與 migration 角色分開。

## 備份與驗證

已產生本機忽略目錄 backups/20260908_070431/：

- project_db.dump：完整資料與結構，未進 Git。
- schema.sql：該次結構。
- manifest.json：備份 SHA-256、工具版本、隔離還原 DB 名稱、各表筆數及核對結果。

工具皆為遠端 PostgreSQL 9.5.25。還原目標為新建的 foodiemo_v1_restore_20260908_070431，撤除 PUBLIC 的 DB 存取；未覆蓋任何已有 DB。14 張表結構及逐表筆數相等，外鍵／CHECK 等限制由 pg_restore 完整建立。還原資料庫保留供核對，未作為測試庫。

來源在備份與後續核對期間若有並行寫入，腳本可能報筆數或 Schema 不同，此時不可標記驗證成功，應在協調後重做備份。Owner 與角色本身不由單一 DB pg_dump 備份；跨主機恢復前需先建角色。不要把含帳號雜湊的 globals 備份放入 Git。

重新執行 scripts/remote_backup.py 會產生新備份與新還原 DB，不會覆蓋現有 baseline.sql，也不會修改已存在的測試帳號／DB。此腳本是為目前已核對的 9.5.25 主機準備，工具版本不符時先停止。已有 SSH 金鑰必須在 .local/known_hosts，SSH／sudo 密碼由互動提示輸入；--use-db-password-for-ssh 只供已確認兩者密碼相同時使用。

## 新建測試資料庫

scripts/remote_backup.py 已建立 foodiemo_v1_test、專用 owner、精確 DB 註解與忽略的 .env.test。沒有 sudo 時由 Owner 執行 scripts/owner_setup.sql，使用 psql 的互動式密碼設定。

migration 僅接受 APP_ENV=test、精確名稱 foodiemo_v1_test、TEST_EXPECTED_HOST／PORT、TEST_ALLOW_WRITE=foodiemo-v1-isolated，連線後以 current_database() 和 shobj_description 再確認標記。PostgreSQL 的資料庫註解在共享目錄，不能使用 obj_description 讀取。

```powershell
./.venv/Scripts/python.exe scripts/migrate.py upgrade
./.venv/Scripts/python.exe scripts/migrate.py current
```

0001_baseline 只在沒有應用資料表時執行原始 Schema DDL；非空 DB 直接拒絕。重跑 Alembic head 不重建資料。不自動 drop、truncate 或以猜測結構執行 autogenerate。

## 既有資料庫標記

已在備份驗證後執行：

```powershell
./.venv/Scripts/python.exe scripts/stamp_existing.py --backup-manifest backups/20260908_070431/manifest.json --apply
```

此入口先驗證備份檔雜湊、還原報告及即時 pg_dump Schema 與 baseline.sql 完全相同，再以 Alembic stamp 新增版本表。沒有 upgrade 既有表。版本若已不同會停止，不能將未來版本倒寫成基線。去掉 --apply 可只做驗證。

維護操作前應確認 .env 的 DB Tunnel 和 SSH_HOST 指向同一已核對主機。不要將正式設定複製成測試設定。

## 回復策略

0001_baseline 的 downgrade 刻意拒絕刪除表。回復完整基線採備份還原至**新的隔離資料庫**，核對結構、逐表筆數和關聯後，另行安排應用切換；沒有一鍵覆蓋 project_db 或自動 drop 全表。此次已實際完成此還原驗證。

後續 migration 必須附回復策略；既有資料庫的 downgrade 與版本升級需另測，不能將本批備份驗證當成未來所有變更都已驗證。

## 相容性依據

SQLAlchemy 官方將 PostgreSQL 9.6+ 列為支援、9+ 為 best effort：[Dialect 支援範圍](https://docs.sqlalchemy.org/en/20/dialects/index.html)。因此本次鎖定套件並在 9.5.25 跑實際 migration／JSONB／外鍵／交易測試，不概括宣稱後續所有功能相容。

備份採相同版本工具並實際還原：[PostgreSQL 9.5 pg_dump 文件](https://www.postgresql.org/docs/9.5/app-pgdump.html)。baseline SQL 包含該版本的 default_with_oids 設定；未驗證直接套用至新版，升級須另外建立驗證流程。
