// 定義快取名稱
const CACHE_NAME = 'foodiemo-v2-static-v2';

// 定義需要快取的資源清單
const ASSETS_TO_CACHE = [
  // 主頁面與核心檔案
  './',
  './index.html',
  './home.html',
  './social.html',
  './memories.html',
  './profile.html',
  './login.html',
  './signup.html',
  './onboarding.html',
  './forgot-password.html',
  './otp_verify.html',
  './reset_password.html',
  './payment.html',
  './comments.html',
  './edit.html',
  './message.html',
  './search.html',
  './main.js',
  './env.js',
  './config.js',
  './static/api/client.js',
  './static/api/pickers.js',
  './assets/restaurant-placeholder.svg',
  './manifest.json',

  // 靜態圖片資源 (您清單中的 12 張照片)
  './IMG_1940.jpg',
  './IMG_3535.jpg',
  './IMG_3604.jpg',
  './IMG_3698.jpg',
  './IMG_3899.jpg',
  './IMG_6207.jpg',
  './IMG_6398.jpg',
  './IMG_6433.jpg',
  './IMG_6481.jpg',
  './IMG_6654.jpg',
  './IMG_6677.jpg',
  './IMG_7136.jpg',
  './icon-192.png',
  './icon-512.png',

];

// 1. 安裝階段 (Install)：將資源存入快取
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('SW: 正在快取所有資源');
      return Promise.allSettled(ASSETS_TO_CACHE.map((asset) => cache.add(asset)));
    })
  );
  // 讓新版本的 Service Worker 立即生效
  self.skipWaiting();
});

// 2. 激活階段 (Activate)：清理舊版本的快取
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cache) => {
          if (cache.startsWith('foodiemo-v2-') && cache !== CACHE_NAME) {
            console.log('SW: 清理舊快取', cache);
            return caches.delete(cache);
          }
        })
      );
    })
  );
  return self.clients.claim();
});

// 3. 攔截請求 (Fetch)：實現離線瀏覽
self.addEventListener('fetch', (event) => {
  // 1. 排除非 GET 請求 (例如 POST 註冊資料)，直接走網路
  if (event.request.method !== 'GET') {
    return; 
  }

  // 2. 排除 API 請求，避免使用者資料被快取混用
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/uploads')) {
    return;
  }

  // 3. HTML 頁面採用網路優先，避免更新後仍吃舊頁面
  if (url.origin === self.location.origin && (event.request.mode === 'navigate' || /\.(html|js)$/.test(url.pathname))) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          if (response.ok) caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match(event.request).then((cached) => cached || Response.error()))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((response) => response || fetch(event.request))
  );
});

// 監聽來自網頁端的指令來顯示通知
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SHOW_RECAP_NOTIFICATION') {
        const options = {
            body: event.data.body,
            icon: 'icon-192.png', // 您的 App 圖示
            badge: 'icon-192.png', // Android 狀態列小圖示
            vibrate: [200, 100, 200],
            data: { url: './home.html?action=showRecap' } // 點擊通知要開哪頁
        };

        self.registration.showNotification(event.data.title, options);
    }
});

// 處理點擊通知後的動作：打開 App 並顯示回顧
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(
        clients.openWindow(event.notification.data.url)
    );
});
