// --- 1. 全域配置 ---
function resolveApiBaseUrl() {
    // v2 always uses the backend serving this frontend; ignore stale v1 overrides.
    return window.location.origin + "/api";
}

const DB_CONFIG = {
    name: "FoodiemoV2DB",
    version: 19, // 統一版本號
    apiUrl: resolveApiBaseUrl()
};

const ORIGINAL_FETCH = window.fetch.bind(window);

function isApiRequest(resource) {
    const url = typeof resource === "string" ? resource : resource && resource.url;
    if (!url) return false;
    return url.startsWith(DB_CONFIG.apiUrl) || url.includes(":8001/api") || url.startsWith("/api/");
}

window.fetch = function(resource, options = {}) {
    if (!isApiRequest(resource)) {
        return ORIGINAL_FETCH(resource, options);
    }

    return ORIGINAL_FETCH(resource, {
        ...options,
        credentials: options.credentials || "include"
    });
};

const DEFAULT_AVATAR_URL =
    "data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Ccircle cx='32' cy='32' r='32' fill='%239C7C66'/%3E%3C/svg%3E";

function normalizeAvatarUrl(url) {
    if (!url || url === "null" || url === "undefined") {
        return DEFAULT_AVATAR_URL;
    }
    return url;
}

function getStoredAvatarUrl() {
    return normalizeAvatarUrl(
        localStorage.getItem("myProfileAvatar") || localStorage.getItem("avatar_url")
    );
}

function setStoredAvatarUrl(url) {
    const normalized = normalizeAvatarUrl(url);
    localStorage.setItem("myProfileAvatar", normalized);
    localStorage.setItem("avatar_url", normalized);
    return normalized;
}

function clearStoredAvatarUrl() {
    localStorage.removeItem("myProfileAvatar");
    localStorage.removeItem("avatar_url");
}

function applyAvatarImage(imgEl, url) {
    if (!imgEl) return;
    imgEl.src = normalizeAvatarUrl(url);
}

function applyAvatarBackground(el, url) {
    if (!el) return;
    const normalized = normalizeAvatarUrl(url);
    el.style.backgroundColor = "#9C7C66";
    el.style.backgroundImage = `url('${normalized}')`;
    el.style.backgroundSize = "cover";
    el.style.backgroundPosition = "center";
    el.innerHTML = "";
}

window.DEFAULT_AVATAR_URL = DEFAULT_AVATAR_URL;
window.normalizeAvatarUrl = normalizeAvatarUrl;
window.getStoredAvatarUrl = getStoredAvatarUrl;
window.setStoredAvatarUrl = setStoredAvatarUrl;
window.clearStoredAvatarUrl = clearStoredAvatarUrl;
window.applyAvatarImage = applyAvatarImage;
window.applyAvatarBackground = applyAvatarBackground;

async function clearLocalAppData() {
    localStorage.clear();

    const dbDeleted = new Promise((resolve) => {
        const request = indexedDB.deleteDatabase(DB_CONFIG.name);
        request.onsuccess = () => resolve(true);
        request.onerror = () => resolve(false);
        request.onblocked = () => resolve(false);
    });

    const cacheDeleted = "caches" in window
        ? caches.keys().then((keys) => Promise.all(keys.map((key) => caches.delete(key)))).catch(() => [])
        : Promise.resolve([]);

    await Promise.all([dbDeleted, cacheDeleted]);
}

// --- 2. 通用資料庫初始化 (整合自 db.js) ---
function initDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_CONFIG.name, DB_CONFIG.version);

        request.onupgradeneeded = (e) => {
            const db = e.target.result;
            // 建立日曆回憶存儲
            if (!db.objectStoreNames.contains("all_photos")) {
                db.createObjectStore("all_photos", { autoIncrement: true });
            }
            // 建立社群貼文存儲
            if (!db.objectStoreNames.contains("posts_timeline")) {
                db.createObjectStore("posts_timeline", { keyPath: "id" });
            }
            // 建立用戶資料存儲
            if (!db.objectStoreNames.contains("user_profile")) {
                db.createObjectStore("user_profile");
            }
        };

        request.onsuccess = (e) => resolve(e.target.result);
        request.onerror = (e) => {
            console.error("IndexedDB 開啟失敗:", e.target.error);
            reject("資料庫開啟失敗");
        };
    });
}

// --- 3. 通用用戶資料儲存工具 ---
async function saveUserData(name, avatarBlob) {
    try {
        const db = await initDB();
        const tx = db.transaction("user_profile", "readwrite");
        const store = tx.objectStore("user_profile");

        if (name) store.put(name, "username");
        if (avatarBlob) store.put(avatarBlob, "avatar");

        return new Promise((resolve) => {
            tx.oncomplete = () => {
                console.log("✅ 用戶資料已更新於 IndexedDB");
                // 通知其他頁面 (如 Social 頁面) 同步頭像與名字
                new BroadcastChannel('memory_update').postMessage('user_updated');
                resolve(true);
            };
        });
    } catch (err) {
        console.error("儲存用戶資料失敗:", err);
        return false;
    }
}
