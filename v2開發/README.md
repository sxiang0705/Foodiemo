# Foodiemo v2

目前版本 v2.2.1。已保留原版介面並串接 PostgreSQL：三卡推薦、可用帳號或 Email 登入、個人頁可修改唯一帳號、六題偏好、照片、地點／會員標註、留言及 Demo 會員。Email 仍用於 OTP 與密碼重設，不會公開在好友與貼文回應。SMTP 已完成實信驗收；月度回顧仍在後續規劃。詳見 [本批測試紀錄](docs/test-report-2026-09-23.md) 與 [資料庫現況](docs/資料庫現況.md)。

## 啟動

需要校內 VPN 可連到 SSH 主機。本機設定在 Git 忽略的 .env；由 .env.example 建立，勿將帳密填入前端。Windows PowerShell，工作目錄 v2開發：

~~~powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.lock
./.venv/Scripts/python.exe scripts/tunnel.py
~~~

Tunnel 使用 .local/known_hosts 中已核對的主機金鑰，未登錄時先核對主機指紋；不自動接受變動的金鑰。SSH 密碼在終端提示輸入。只有已確認 SSH／DB 密碼相同的本機環境才能明確使用 --use-db-password-for-ssh；密碼仍從忽略設定檔讀取。

另開終端：

~~~powershell
./scripts/start.ps1
~~~

- 原版推薦頁：http://127.0.0.1:8002/search.html
- 原版主入口：http://127.0.0.1:8002/ （Cookie 驗證；本機 SMTP 已設定）
- 健康檢查：http://127.0.0.1:8002/api/health
- v2 測試 API 預設 8003，Tunnel 預設 55433，不佔用 v1 的 8000／55432。

推薦頁可直接核對唯讀資料；沒有加入假登入，沒有把首頁換成餐廳清單。尚未實作的 API（如 Google OAuth）回 501 NOT_IMPLEMENTED。原版頁面內的本機示意仍保留，詳見差異清單。

## 測試

~~~powershell
./.venv/Scripts/python.exe scripts/check_source.py
./.venv/Scripts/python.exe scripts/test.py
./.venv/Scripts/python.exe scripts/test.py --integration
pnpm install --frozen-lockfile
$env:V2_LIVE='1'
pnpm test:browser
./.venv/Scripts/python.exe tests/run_browser_features.py
node tests/baseline.cjs
./.venv/Scripts/python.exe scripts/live_smoke.py
~~~

integration 必須先準備 .env.test 指向 foodiemo_v2_test，包含專用角色及伺服器隔離標記；入口不接受正式、v1 或備份還原庫。API 人工資料在交易後 rollback；完整瀏覽器測試只清理本輪 UUID 人工帳號與照片，不清表。瀏覽器測試使用已安裝 Microsoft Edge 的 headless 模式，API fixture 與 LIVE PostgreSQL 項目分別記錄。未設定 V2_LIVE 時不聲稱真實資料已驗證。

備份／新隔離還原與首次測試庫建立：

~~~powershell
./.venv/Scripts/python.exe scripts/remote_backup.py
./.venv/Scripts/python.exe scripts/migrate.py upgrade
~~~

此備份腳本針對已核對的 PostgreSQL 9.5.25；只建立新還原庫，不覆蓋正式庫，不覆蓋既有測試庫。基線延續 v1 的 0001_baseline；正式庫已套用 0002_accounts_records。後續既有庫升級使用 scripts/apply_existing.py，預設唯讀預檢；需明確 --apply 才寫入。備份、還原庫及測試庫需保留／清理時按確切目標另行操作，不自動刪除。

詳見 [開發流程](v2開發流程.md)、[測試流程](v2測試流程.md)、[前端基線](docs/frontend-baseline.md)、[API 契約](docs/api.md) 與 [本批測試紀錄](docs/test-report-2026-09-09.md)。


SMTP 最新進度見 [2026-09-12 實信測試](docs/smtp-test-2026-09-12.md)。


## 同 Wi-Fi 手機測試

在電腦保持 VPN 與 SSH Tunnel 運行時，可另開 LAN 預覽：

```powershell
./.venv/Scripts/python.exe scripts/run.py --lan-ip 電腦的WiFiIPv4位址
```

手機使用 `http://電腦的WiFiIPv4位址:8002`，不使用 127.0.0.1。預設啟動仍僅綁定 127.0.0.1；LAN 模式僅接受明確的 RFC1918 IPv4，不開放測試資料庫模式，也不改變 Tunnel 的 loopback 綁定。兩個預覽可使用不同綁定位址並存。

Windows 防火牆需允許指定 Wi-Fi 介面、LAN 位址、本地子網及 TCP 8002；不需路由器埠轉送。網路 IP 改變時需重啟 LAN 預覽並更新規則。HTTP LAN 可先驗證表單、相簿與互動；Service Worker、PWA 等需要安全來源的能力另以 HTTPS 驗收。手機使用另一個網站來源，因此需要重新登入。

## 本機 HTTPS 相機預覽

要在 iPhone Safari 使用中間的即時鏡頭，LAN 預覽必須使用 HTTPS。先保持 VPN 與 SSH Tunnel 運作，在 PowerShell 執行：

```powershell
.\.venv\Scripts\python.exe scripts\make_https_cert.ps1 -LanIp 192.168.0.22
```

此指令會在 `.local/https/` 建立本機 Root CA、伺服器憑證與私鑰；`.local/` 已被 Git 忽略。若 Windows 防火牆尚未建立規則，請用系統管理員 PowerShell 執行：

```powershell
New-NetFirewallRule -DisplayName 'Foodiemo-v2-LAN-8443' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8443 -LocalAddress 192.168.0.22 -RemoteAddress LocalSubnet -InterfaceAlias Wi-Fi -Profile Any
```

啟動 HTTPS 預覽：

```powershell
.\.venv\Scripts\python.exe scripts\run.py --lan-ip 192.168.0.22 --port 8443 --ssl-certfile .local/https/foodiemo-local-server-cert.pem --ssl-keyfile .local/https/foodiemo-local-server-key.pem
```

把 `.local/https/foodiemo-local-root.cer` 傳到 iPhone，點開後安裝描述檔，再到「設定 → 一般 → 關於本機 → 憑證信任設定」啟用此 Root CA。完成後用 Safari 開啟 `https://192.168.0.22:8443/index.html`，重新登入並允許相機權限。憑證只適用於目前這台電腦與目前 LAN IP；IP 改變時重新產生憑證並更新防火牆規則。
