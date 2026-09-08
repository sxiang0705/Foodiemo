# 餐廳 API v1

路徑前綴 `/api/v1`，與前端同來源。本批為公開唯讀 API，不需要登入。OpenAPI JSON：`/openapi.json`。未啟用依賴 CDN 的 Swagger 頁面。

## 路由

| 方法與路徑 | 說明 |
| --- | --- |
| GET /health | DB 可連線為 200，失敗為 503 |
| GET /restaurants | 列表、分頁、搜尋與分類 |
| GET /restaurants/{id} | 指定餐廳詳情，無資料為 404 |
| GET /restaurants/{id}/reviews | 保存的原始餐廳評論；非平台留言 |

列表參數：`page=1`（1–10000）、`page_size=12`（1–50）、`q`（最長 100 字，店名或地址不分大小寫包含搜尋）、`category`（最長 100 字，完整分類名稱相等）。空白前後移除，空字串不篩選；% 與 _ 視為文字，不是萬用字元。ID 遞增穩定排序，不推算連續 ID。

評論參數：`page=1`、`page_size=10`，上限同列表。依 reviews_id 升冪排序，不宣稱為發布時間排序。無效參數為 422。

## 回應範例（人工示例）

```json
{
  "items": [
    {
      "id": "3",
      "name": "範例餐廳",
      "address": null,
      "category": null,
      "review_count": 0,
      "photo_url": null,
      "rating": null,
      "price": null
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 12
}
```

ID 一律為十進位字串，避免 JavaScript 遺失 bigint 精度。詳情額外回傳 phone、website、latitude、longitude、business_hours。營業時間包含 weekday（資料庫原始 0–6）、open_time、close_time（HH:MM:SS）、is_closed；缺少時為空陣列，不能當成公休或 24 小時營業。weekday 起算規則待資料來源確認，前端明示星期資訊待確認。

rating、price、photo_url 固定為 null，因目前餐廳表沒有可靠來源。review_count 來自含大寫的 reviewsCount，是來源的總數，不等於保存的評論數。

評論每筆只回傳 id、text、published_at=null、rating=null。不回傳 created_at 匯入時間，也不把它當成發布時間；不回傳 cleaned_features 或內部分析欄位。

## 錯誤契約

```json
{"error":{"code":"DATABASE_UNAVAILABLE","message":"資料庫暫時無法使用，請稍後重試","request_id":"server-generated-id"}}
```

- 404：NOT_FOUND。
- 422：INVALID_REQUEST。
- 503：DATABASE_UNAVAILABLE，涵蓋 Tunnel、查詢逾時與資料庫連線問題。

每個回應含 X-Request-ID。日誌只記錯誤類型與 request ID，不寫 SQL 參數、連線字串、DB 例外原文或使用者資料。瀏覽器請求 15 秒逾時，後端連線與單一查詢設定 5 秒，連線池等待 5 秒。空列表是 200 與 items=[]，與連線失敗分開。

前端使用 textContent；網站連結只接受絕對 http(s) URL。正式資料不由 localStorage、IndexedDB 或 Service Worker 供應，沒有假成功或快取身份。
