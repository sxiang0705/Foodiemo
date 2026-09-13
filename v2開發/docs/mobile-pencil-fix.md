# 手機鉛筆入口修正

使用者在 iPhone Safari 回報點首頁鉛筆完全無反應。程式檢查發現 iframe 的 touchstart 會啟用外層拖曳遮罩，即使手指點的是導頁連結。桌面 Chromium 觸控模擬原本可跳轉，因此無法聲稱完整重現 Safari 問題。

修正：a、button、輸入欄位及快門不再透過外層手勢橋接啟用遮罩，保留原本原生點擊與導頁。一般區域的左右側滑、五分之一門檻、主樣式與按鈕位置不變。更新 PWA 靜態快取版本。

`node tests/navigation-touch.cjs` 在 390／412 px 觸控環境驗證：按住鉛筆時遮罩維持 pointer-events:none、tap 進編輯頁、Finish 存在、空白編輯頁 Back 返回。既有原版回歸另以 tests/browser.cjs 執行。

本機未安裝 WebKit 測試引擎，尚待使用者重新整理後，以真實 Safari 確認修正有效；不以 Chromium 模擬代替 iPhone 實機驗收。
