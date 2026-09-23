> 本文件原有段落記錄第一批推薦契約；2026-09-10 新增帳號與照片契約見文末，原「未串接」狀態以新段落為準。

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



## 2026-09-10 帳號／照片 API

所有受保護 API 以 HttpOnly Cookie `foodiemo_session` 識別使用者。前端 email 不決定身分；不符時 403。未登入 401、缺資料 404、格式錯誤 422、頻率限制 429、寄信／資料庫不可用 503。未知 API 仍為 501。聊天室訊息只保存於好友雙方的私有對話，不公開給其他使用者。

| 路徑 | 方法與資料 |
| --- | --- |
| /api/register | POST JSON email/username/name/password/phone/dob；username 為 3–30 字元、小寫英數字、底線或句點且唯一；寄信成功後回 verification_required，尚不登入 |
| /api/send_email_code | POST email/purpose（signup 或 reset_password）；驗證與密碼重設仍使用 Email |
| /api/verify_email_code | POST email/purpose/code；註冊驗證建立 Cookie；重設用途回一次性 reset_token |
| /api/login、/api/logout | POST；登入接受 identifier（帳號或 Email），相容舊 email 欄位；登出撤銷當前 Token |
| /api/me/username | PUT JSON username；修改登入／搜尋帳號，保留穩定 user_id 與既有關係 |
| /api/reset_password | POST reset_token/new_password；成功撤銷該帳號所有工作階段 |
| /api/me | GET 會員自己的 Email、username、姓名、avatar_url、is_premium、preferences |
| /api/preferences | PUT version=1、answers 六題 key/value；選項需完全符合原六題 |
| /api/get_memories、/api/get_post/{id} | GET 作者紀錄或登入者被標記的紀錄，保留原版 imageUrls/date/timestamp/location/comments 格式，不回傳作者 Email，並回傳 `likes`、`isLiked`、`commentCount`；`/api/get_memories?scope=memories` 或 `scope=social` 會再合併目前登入會員被標記的貼文，附 `isOwner`、`isTagged`、`canEdit` 權限欄位 |
| /api/upload_memory_post、/api/update_post | POST multipart files、photo_order、restaurant_id、mention_ids；可附 `initial_comment`（最多 2000 字）建立第一則留言；沒有餐廳選擇時可附 `photo_location_text`（最多 200 字）保存照片 EXIF GPS 的顯示標籤；更新須 post_id |
| /api/locations?q=、/api/members?q= | GET 搜尋餐廳／已驗證會員；`/api/members` 不帶 q 時先回傳目前已接受的好友，輸入 q 時可依 username 或顯示名稱搜尋；不回傳 Email；ID 以字串傳遞 |
| /api/posts/{id}/mention | DELETE 由被標記會員取消自己的標記；作者或未被標記會員不能呼叫成功 |
| /api/friends、/api/friends/search?q= | GET 好友與請求；以公開 username 搜尋，回傳姓名／username／頭像／關係，不回傳 Email |
| /api/friends/requests | POST user_id；送出好友請求，對方批准後建立關係 |
| /api/friends/requests/{id}/approve、/reject | POST；批准或忽略收到的好友請求 |
| /api/chats/{friend_id}/messages | GET；讀取已接受好友的聊天訊息（可用 after_id 增量輪詢）；POST JSON text；只有已接受好友可收發，訊息最多 2000 字；好友識別只回傳姓名、username 與頭像 |
| /api/posts/{id} | DELETE 整篇紀錄及照片引用 |
| /api/posts/{id}/like | POST／DELETE；目前登入者對自己或被標記的紀錄新增／取消愛心，重複新增不會重複計數 |
| /api/delete_single_photo | DELETE post_id/photo_url；只刪作者自己指定的一張 |
| /api/photos/{id} | GET 作者或被標記會員可讀取 JPEG；不公開本機檔案路徑 |
| /api/add_comment | POST photo_id（沿用原版，值為紀錄 ID）、text；作者或被標記會員可留言 |
| /api/update_profile_name、/api/upload_avatar | POST multipart name 或 file |
| /api/check_vip/{email}、/api/upgrade_premium | GET 會員狀態／POST Demo 開通，金額 0、simulated=true |

photo_order 是 JSON 陣列，例：`[{"existing":"/api/photos/12"},{"new":0}]`。new 是 files 順序索引；existing 必須屬於本篇。全部新檔案必須使用一次，不接受重複／他人的照片。未傳順序時以新檔案原順序保存（首頁直接上傳用）。mention_ids 為會員 ID JSON 陣列，最多 10 人。

CaptureMailer 僅由隔離測試注入，HTTP 回應無 OTP preview；正式 SMTP 由忽略的本機設定提供並已完成實信驗收。付款沒有外部金流請求；既有 Google OAuth API 尚未實作。

`photo_location_text` 不是餐廳 ID，也不會取得餐廳資料；目前用既有 `records.location_text` 保存照片 GPS 的短標籤，後端在圖片實體化時移除原始 EXIF。照片 GPS 由前端在畫布壓縮前讀取，沒有 GPS 時不會自動呼叫瀏覽器定位。
