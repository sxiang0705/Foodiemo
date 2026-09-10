# v2 第一批 API 與推薦提供者

GET /api/restaurants/recommendations?count=3&cursor=...&t=...

count 為 1–3，原版固定 3。cursor 是上次 next_cursor 的不透明值，只在原下拉重取時傳送，不產生分頁 UI。t 為原版快取破除參數。此階段是公開唯讀餐廳資料，不宣稱已登入或個人化。

~~~json
{
  "items": [{
    "id": "9007199254740993",
    "title": "店名",
    "subtitle": null,
    "img": null,
    "rating": null,
    "hours": null,
    "price": null,
    "address": null,
    "mapLink": "https://www.google.com/maps/search/?api=1&query=...",
    "source": "postgresql"
  }],
  "source": "postgresql",
  "algorithm_version": "rotation-v1",
  "next_cursor": "不透明字串或 null"
}
~~~

ID 始終是十進位字串，避免 JavaScript bigint 精度流失。title／subtitle／address 保留資料文字，前端使用安全文字節點，不解讀 HTML。restaurant_rows 尚無可靠照片、總評分、價位欄位；目前 business_hours 為空且 weekday 起算未核對，因此 hours 留空，原位置提示查看地圖。後續取得可靠來源再映射，不造值。

mapLink 以有效座標或店名／地址 URL 編碼組成 Google Maps 搜尋；不把 googleMaps_id 當成已確認的 Places ID。前端只允許 https://www.google.com/maps/ 地圖連結，另開視窗使用 noopener。

backend/app/recommendation/service.py 的 Provider.select(session, RecommendationContext) 可替換。基礎 rotation-v1 依穩定主鍵接續、尾端繞回，至多取 3 筆且不重複；候選少於 3 就回實際筆數。游標不包含認證資訊，不能當成身分證明。無寫入 runs／items 或事件；階段 5 才接已驗證身分、後端偏好及演算法追蹤契約。此介面先提供可測試替換點，不代表最終演算法契約已完成。

錯誤採 JSON detail 與 error.code/message/request_id。無效 count／cursor 回 422；DB 中斷回 503，不洩漏 SQL／帳密，也不切內建餐廳。其他尚未實作 API 回 501。應用資料連線預設強制唯讀、有連線與 SQL 逾時。前端 10 秒逾時，連續下拉取消前請求並驗證最新序號，錯誤後仍用原下拉重試。

frontend/api/client.js 透過 /static/api/client.js 載入，避免與 /api/* 後端入口衝突。API 同源，不採用先前 localStorage 的外部後端覆寫值。

