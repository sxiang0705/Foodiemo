# 部署與後續工作

目前是 Windows 本機開發環境：瀏覽器 → 127.0.0.1:8000 FastAPI → 127.0.0.1:55432 SSH Tunnel → Ubuntu PostgreSQL。前端與 API 同來源，不開放 wildcard CORS。API 與前端由同一程式提供，CSP 僅允許自身資源，沒有第三方字型、地圖或推薦 API 依賴。

服務使用 scripts/start.ps1 啟動，以 Ctrl+C 停止；SSH Tunnel 必須獨立保持執行。範例僅監聽 loopback。部署位置尚未決定，這次沒有公開部署，也沒有建立系統開機服務。

對外部署前需確認：

1. 決定後端主機與 PostgreSQL 的私有連線方式；部署在同台 Ubuntu 時可直接 localhost 連 DB。
2. 反向代理 HTTPS、網路存取範圍、逾時、健康檢查及受管理的服務重啟。
3. 設定來自主機密鑰管理，限制 .env、備份的檔案存取與保留期限；管理 SSH 主機金鑰。
4. 後續登入 Cookie 的 Secure／HttpOnly／SameSite、CSRF 及跨來源需求；本批未實作登入，沒有可沿用的假驗證。
5. 後續照片儲存與公私存取、上傳限制、清理及失敗補償。
6. GitHub 推送前執行 scripts/check_source.py 並查看 git diff --cached，確認不含原始資料、帳密、上傳檔案或備份。

接下來依開發計畫進入階段 2：帳號、登入、Email 驗證／重設密碼與頭像 migration。收藏、紀錄與照片為階段 3；社群為階段 4；推薦契約與基礎實作為階段 5；模擬付款為階段 6。這些均尚未實作或測試，不能以餐廳 API 通過替代驗收。

推薦模組不在第一批新增空殼介面；到階段 5 再與演算法團隊確認版本化契約、輸入輸出與事件語意。
