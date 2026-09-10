// ==========================================
// 1. 全域變數設定
// ==========================================
const wrapper = document.getElementById('swipeWrapper');
window.isLocked = false; 

// 這裡統一：0 = Memories, 1 = Home/Profile, 2 = Social
window.currentIndex = 1; 
let startX = 0;
window.startY = 0; // 確保全域定義
let isDragging = false;

// ==========================================
// 2. 核心滑動邏輯
// ==========================================

function updateView(animate = true) {
    if (!wrapper) return;
    wrapper.style.transition = animate ? 'transform 0.4s cubic-bezier(0.25, 1, 0.5, 1)' : 'none';
    const offset = -window.currentIndex * window.innerWidth;
    wrapper.style.transform = `translateX(${offset}px)`;
}

window.switchTab = function(target, animate = true) {
    if (target === 'memories') window.currentIndex = 0;
    else if (target === 'social') window.currentIndex = 2;
    else window.currentIndex = 1; 
    
    updateView(animate);
};

// ==========================================
// 3. 手勢事件 (關鍵修正：確保 startY 被記錄)
// ==========================================

window.addEventListener('touchstart', handleTouchStart, { passive: false });
window.addEventListener('touchmove', handleTouchMove, { passive: false });
window.addEventListener('touchend', handleTouchEnd, { passive: true });

function handleTouchStart(e) {
    // 即使鎖定了也要記錄起點，否則 diffX/diffY 會計算錯誤
    startX = e.touches[0].clientX;
    window.startY = e.touches[0].clientY; 

    if (window.isLocked) return; 
    
    isDragging = true;
    wrapper.style.transition = 'none';
}

function handleTouchMove(e) {
    if (window.isLocked) {
        const currentX = e.touches[0].clientX;
        const currentY = e.touches[0].clientY;
        
        const diffX = Math.abs(currentX - startX);
        const diffY = Math.abs(currentY - window.startY);

        // 如果橫向位移大於縱向位移，視為嘗試側滑返回 -> 鎖死
        if (diffX > diffY) {
            if (e.cancelable) e.preventDefault(); 
            return;
        }
        
        // 縱向位移（下拉關閉）時不做處理，讓 iframe 內部的手勢接管
        return;
    }
    
    if (!isDragging) return;
    
    const currentX = e.touches[0].clientX;
    const diff = currentX - startX;
    
    const move = (-window.currentIndex * window.innerWidth) + diff;
    wrapper.style.transform = `translateX(${move}px)`;
}

function handleTouchEnd(e) {
    if (!isDragging) return;
    isDragging = false;
    const endX = e.changedTouches[0].clientX;
    const diff = endX - startX;

    if (Math.abs(diff) > window.innerWidth * 0.2) {
        if (diff > 0 && window.currentIndex > 0) {
            window.currentIndex--;
        } else if (diff < 0 && window.currentIndex < 2) {
            window.currentIndex++;
        }
    }
    updateView(true);
}

// ==========================================
// 4. 初始化與通訊
// ==========================================

window.addEventListener('load', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const tab = urlParams.get('tab');
    
    if (tab === 'social') window.currentIndex = 2; 
    else if (tab === 'memories') window.currentIndex = 0; 
    else window.currentIndex = 1;

    updateView(false); 
});

window.addEventListener('resize', () => updateView(false));

// 接收來自各個 iframe 的狀態與導航請求
window.addEventListener('message', (e) => {
    if (e.data === 'lockSwiping') window.isLocked = true;
    if (e.data === 'unlockSwiping') window.isLocked = false;

    if (e.data === 'goHome' || e.data === 'goProfile') {
        window.isLocked = false;
        window.switchTab('profile');
    }

    if (e.data && e.data.type === 'paymentSuccess') {
        window.isLocked = false;
        window.switchTab(e.data.tab === 'social' ? 'social' : 'profile');
    }
});