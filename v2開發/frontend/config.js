// --- 1. 全域配置 ---
function resolveApiBaseUrl() {
    // v2 always uses the backend serving this frontend; ignore stale v1 overrides.
    return window.location.origin + "/api";
}

const DB_CONFIG = {
    name: "FoodiemoV2DB",
    version: 20, // 統一版本號
    apiUrl: resolveApiBaseUrl()
};

window.DB_CONFIG = DB_CONFIG;

const ORIGINAL_FETCH = window.fetch.bind(window);

function isApiRequest(resource) {
    const url = typeof resource === "string" ? resource : resource && resource.url;
    if (!url) return false;
    return url.startsWith(DB_CONFIG.apiUrl) || url.includes(":8001/api") || url.startsWith("/api/");
}

// Account-scoped, bounded metadata cache. Photos and credentials are never stored here.
window.FoodiemoViewCache = {
    clear() { for(const key of Object.keys(sessionStorage)) if(key.startsWith('foodiemo-view:')) sessionStorage.removeItem(key); },
    read(name) { try { const item=JSON.parse(sessionStorage.getItem('foodiemo-view:'+name));
        return item && item.email===localStorage.getItem('myProfileEmail') && Date.now()-item.time<600000 ? item.value : null;
    } catch(e) { return null; } },
    write(name,value) { try { const text=JSON.stringify({email:localStorage.getItem('myProfileEmail'),time:Date.now(),value});
        if(text.length<500000)sessionStorage.setItem('foodiemo-view:'+name,text);
    } catch(e) {} }
};
window.loadFoodiemoRecords = async function(render) {
    const user=await window.FoodiemoSessionReady;
    if(!user)return;
    const cached=FoodiemoViewCache.read('records');
    if(cached!==null)render(cached);
    const generation=sessionStorage.getItem('foodiemo-record-generation');
    const response=await fetch(DB_CONFIG.apiUrl+'/get_memories');
    if(response.status===401){FoodiemoViewCache.clear();window.top.location.replace('login.html');return;}
    if(!response.ok)throw new Error('資料更新失敗，請稍後重試');
    const result=await response.json();
    if(generation!==sessionStorage.getItem('foodiemo-record-generation') || user.email!==localStorage.getItem('myProfileEmail'))return;
    FoodiemoViewCache.write('records',result);
    if(JSON.stringify(cached)!==JSON.stringify(result))render(result);
};

window.fetch = function(resource, options = {}) {
    if (!isApiRequest(resource)) {
        return ORIGINAL_FETCH(resource, options);
    }

    const init={...options,credentials:options.credentials || "include"};
    // The three home frames can request the same records concurrently. Share only
    // the in-flight response, never a persistent cache, and give each reader a clone.
    if (typeof resource==='string' && (options.method||'GET').toUpperCase()==='GET' && !options.signal) {
        const url=new URL(resource,location.href);
        if (url.origin===location.origin && url.pathname==='/api/get_memories') {
            let owner=window;
            try { if(window.top.location.origin===location.origin)owner=window.top; } catch(e) {}
            const requests=owner.FoodiemoRecordRequests ||= new Map();
            url.searchParams.delete('t');url.searchParams.sort();const key=url.href;
            if(!requests.has(key))requests.set(key,ORIGINAL_FETCH(resource,init).finally(()=>requests.delete(key)));
            return requests.get(key).then(response=>response.clone());
        }
    }
    return ORIGINAL_FETCH(resource,init).then(response=>{
        if(response.status===401)FoodiemoViewCache.clear();
        if(response.ok && !['GET','HEAD','OPTIONS'].includes((init.method||'GET').toUpperCase())) {
            sessionStorage.removeItem('foodiemo-view:records');
            sessionStorage.setItem('foodiemo-record-generation',String(Date.now())+Math.random());
        }
        return response;
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
    FoodiemoViewCache.clear();
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
            for (const name of ["posts", "users"]) {
                if (!db.objectStoreNames.contains(name)) db.createObjectStore(name, {keyPath:"id"});
            }
            if (db.objectStoreNames.contains("user_profile") && e.target.transaction.objectStore("user_profile").keyPath !== null) db.deleteObjectStore("user_profile");
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

window.FoodiemoInitDB = initDB;
window.escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

window.refreshFoodiemoSession = async function(redirect = true) {
    try {
        const response = await ORIGINAL_FETCH(DB_CONFIG.apiUrl + '/me', {credentials:'include',cache:'no-store'});
        if (response.status === 401) {
            FoodiemoViewCache.clear();
            localStorage.removeItem('myProfileEmail');
            localStorage.removeItem('myProfileName');
            localStorage.removeItem('isPremiumUser');
            clearStoredAvatarUrl();
            if (redirect) window.top.location.replace('login.html');
            return null;
        }
        if (!response.ok) throw new Error('帳號資料暫時讀取失敗，請稍後重試');
        const user = await response.json();
        if(localStorage.getItem('myProfileEmail')!==user.email)FoodiemoViewCache.clear();
        localStorage.setItem('myProfileEmail',user.email);
        localStorage.setItem('myProfileName',user.name);
        localStorage.setItem('isPremiumUser',String(user.is_premium));
        setStoredAvatarUrl(user.avatar_url);
        return user;
    } catch (error) {
        window.dispatchEvent(new CustomEvent('foodiemo-session-error',{detail:error.message}));
        return null;
    }
};
const publicPages = ['login.html','signup.html','forgot-password.html','otp_verify.html','reset_password.html','search.html'];
window.FoodiemoSessionReady = publicPages.includes(location.pathname.split('/').pop())
    ? Promise.resolve(null) : (window.parent!==window && window.parent.FoodiemoSessionReady ? window.parent.FoodiemoSessionReady : window.refreshFoodiemoSession());

// Match the original editor's upload resizing for the direct shutter/gallery path.
window.prepareFoodiemoPhoto = function(file) {
    if (file.size <= 2*1024*1024) return Promise.resolve(file);
    return new Promise((resolve,reject) => {
        const url=URL.createObjectURL(file),img=new Image();
        img.onerror=()=>{URL.revokeObjectURL(url);reject(new Error('無法讀取照片'));};
        img.onload=()=>{
            URL.revokeObjectURL(url);
            const scale=Math.min(1,1280/Math.max(img.naturalWidth,img.naturalHeight));
            const canvas=document.createElement('canvas');
            canvas.width=Math.max(1,Math.round(img.naturalWidth*scale));canvas.height=Math.max(1,Math.round(img.naturalHeight*scale));
            canvas.getContext('2d').drawImage(img,0,0,canvas.width,canvas.height);
            canvas.toBlob(blob=>blob?resolve(new File([blob],file.name,{type:'image/jpeg'})):reject(new Error('照片處理失敗')),'image/jpeg',0.8);
        };
        img.src=url;
    });
};
