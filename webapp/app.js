// Telegram WebApp Client Script
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
}

let currentUser = null;
let currentOrderId = null;
let currentPhone = "";
let currentCode = "";
let currentPassword = "";
let timerInterval = null;
let remainingSeconds = 300;

// Haptic feedback helper
function haptic(type = 'light') {
    if (tg?.HapticFeedback) {
        if (type === 'success' || type === 'error' || type === 'warning') {
            tg.HapticFeedback.notificationOccurred(type);
        } else {
            tg.HapticFeedback.impactOccurred(type);
        }
    }
}

// Toast helper
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    if (!toast) return;

    toast.className = `fixed top-16 left-1/2 -translate-x-1/2 z-50 transform transition-all duration-300 px-5 py-3 rounded-2xl text-xs font-bold shadow-2xl flex items-center gap-2.5 backdrop-blur-2xl border ${
        type === 'success' ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500/40 shadow-emerald-950/60' : 
        type === 'error' ? 'bg-rose-950/80 text-rose-300 border-rose-500/40 shadow-rose-950/60' : 
        'bg-slate-900/80 text-cyan-300 border-cyan-500/30 shadow-cyan-950/60'
    }`;
    toast.innerHTML = `<span>${type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'}</span><span>${message}</span>`;
    toast.style.opacity = '1';
    toast.style.transform = 'translate(-50%, 0)';

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translate(-50%, -20px)';
    }, 2500);
}

// Clipboard Copy
function copyToClipboard(text, successMsg = "Nusxalandi!") {
    if (!text) return;
    haptic('medium');
    navigator.clipboard.writeText(text).then(() => {
        showToast(successMsg, 'info');
    }).catch(() => {
        showToast(text, 'info');
    });
}

// Tab Switching
function switchTab(tabId) {
    haptic('light');
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

    const targetTab = document.getElementById(`tab-${tabId}`);
    const targetNav = document.getElementById(`nav-${tabId}`);
    if (targetTab) targetTab.classList.remove('hidden');
    if (targetNav) targetNav.classList.add('active');

    if (tabId === 'rating') loadLeaderboard();
    if (tabId === 'history') loadHistory();
    if (tabId === 'withdraw') loadWithdrawals();
}

// Format currency
function formatMoney(amount) {
    return Number(amount || 0).toLocaleString('uz-UZ');
}

// Auth Headers
function getHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    if (tg?.initData) {
        headers['X-Telegram-Init-Data'] = tg.initData;
    }
    // Also include user id if available
    const uid = tg?.initDataUnsafe?.user?.id;
    if (uid) {
        headers['X-User-Id'] = uid;
    }
    return headers;
}

// Initialize Profile Info
function initUserData() {
    const user = tg?.initDataUnsafe?.user || {
        id: 6278841173,
        first_name: "Admin",
        username: "Muxamadiyev"
    };

    currentUser = user;
    const nameElem = document.getElementById('user-name');
    const idElem = document.getElementById('user-tg-id');
    const avatarElem = document.getElementById('user-avatar');

    const fullName = `${user.first_name || ''} ${user.last_name || ''}`.trim() || user.username || "Foydalanuvchi";
    if (nameElem) nameElem.innerHTML = `${fullName} <span class="text-yellow-400">⭐</span>`;
    if (idElem) idElem.innerText = user.id;
    if (avatarElem) avatarElem.innerText = (user.first_name || 'U').charAt(0).toUpperCase();

    fetchUserMe();
}

// API: Fetch User State
async function fetchUserMe() {
    try {
        const uid = currentUser?.id || 0;
        const res = await fetch(`/api/user/me?user_id=${uid}`, { headers: getHeaders() });
        if (!res.ok) return;
        const data = await res.json();

        // Update Balances
        document.getElementById('user-balance').innerText = formatMoney(data.balance);
        document.getElementById('user-premiums-count').innerText = data.successful_premiums || 0;
        document.getElementById('user-total-earned').innerText = `${formatMoney(data.total_earned)} so'm`;
        document.getElementById('withdraw-available-balance').innerText = formatMoney(data.balance);

        // Active Order Handling
        if (data.active_order) {
            showActiveOrder(data.active_order);
        } else {
            hideActiveOrder();
        }
    } catch (err) {
        console.error("fetchUserMe error:", err);
    }
}

// Active Order Display
function showActiveOrder(order) {
    currentOrderId = order.id;
    currentPhone = order.phone_number;
    currentCode = order.code || "";
    currentPassword = order.password || "";

    document.getElementById('get-number-box').classList.add('hidden');
    document.getElementById('active-order-box').classList.remove('hidden');
    document.getElementById('order-phone').innerText = currentPhone;

    // Code & Pass section
    const codeSection = document.getElementById('code-password-section');
    const initBtns = document.getElementById('order-buttons-init');
    const receivedBtns = document.getElementById('order-buttons-received');

    if (currentCode) {
        codeSection.classList.remove('hidden');
        document.getElementById('order-code').innerText = currentCode;
        if (currentPassword) {
            document.getElementById('password-subbox').classList.remove('hidden');
            document.getElementById('order-password').innerText = currentPassword;
        } else {
            document.getElementById('password-subbox').classList.add('hidden');
        }
        initBtns.classList.add('hidden');
        receivedBtns.classList.remove('hidden');
    } else {
        codeSection.classList.add('hidden');
        initBtns.classList.remove('hidden');
        receivedBtns.classList.add('hidden');
    }

    // Start Timer
    startTimer(order.seconds_left || 300);
}

function hideActiveOrder() {
    currentOrderId = null;
    currentPhone = "";
    currentCode = "";
    currentPassword = "";
    clearInterval(timerInterval);

    document.getElementById('active-order-box').classList.add('hidden');
    document.getElementById('get-number-box').classList.remove('hidden');
}

// Timer
function startTimer(seconds) {
    clearInterval(timerInterval);
    remainingSeconds = Math.max(0, seconds);

    function update() {
        if (remainingSeconds <= 0) {
            clearInterval(timerInterval);
            document.getElementById('order-timer').innerText = "00:00";
            hideActiveOrder();
            fetchUserMe();
            return;
        }
        const m = Math.floor(remainingSeconds / 60);
        const s = remainingSeconds % 60;
        document.getElementById('order-timer').innerText = 
            `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        remainingSeconds--;
    }

    update();
    timerInterval = setInterval(update, 1000);
}

// API: Request Number
async function requestNumber() {
    const btn = document.getElementById('btn-main-get-number');
    btn.disabled = true;
    btn.innerHTML = `<span>⏳</span><span>Raqam olinmoqda...</span>`;
    haptic('medium');

    try {
        const uid = currentUser?.id || 0;
        const res = await fetch('/api/order/get_number', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ user_id: uid })
        });
        const data = await res.json();

        if (data.success && data.order) {
            haptic('success');
            showToast("Raqam olindi! 📱");
            showActiveOrder(data.order);
        } else {
            haptic('error');
            showToast(data.error || "Raqam olishda xatolik!", 'error');
        }
    } catch (err) {
        haptic('error');
        showToast("Server bilan aloqa yo'q!", 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<span class="text-2xl animate-bounce">📱</span><span>Number Olish</span>`;
    }
}

// API: Request Code
async function requestCode() {
    if (!currentOrderId) return;
    haptic('medium');
    showToast("Kod so'ralmoqda...", 'info');

    try {
        const res = await fetch('/api/order/get_code', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ order_id: currentOrderId })
        });
        const data = await res.json();

        if (data.success) {
            haptic('success');
            showToast("Kod keldi! 🔑", 'success');
            currentCode = data.code;
            currentPassword = data.password || "";
            showActiveOrder({
                id: currentOrderId,
                phone_number: currentPhone,
                code: currentCode,
                password: currentPassword,
                seconds_left: remainingSeconds
            });
        } else {
            haptic('warning');
            showToast(data.error || "Kod hali kelmadi, kuting...", 'error');
        }
    } catch (err) {
        showToast("Xatolik yuz berdi!", 'error');
    }
}

// API: Confirm Received
async function confirmReceived() {
    if (!currentOrderId) return;
    haptic('medium');
    showToast("Premium tekshirilmoqda...", 'info');

    try {
        const res = await fetch('/api/order/received', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ order_id: currentOrderId })
        });
        const data = await res.json();

        if (data.success) {
            haptic('success');
            showToast("🎉 Tabriklaymiz! 40,000 so'm qo'shildi!", 'success');
            hideActiveOrder();
            fetchUserMe();
        } else {
            haptic('error');
            showToast(data.error || "Premium hali tasdiqlanmadi!", 'error');
        }
    } catch (err) {
        showToast("Server xatosi!", 'error');
    }
}

// API: Freeze Order
async function freezeOrder() {
    if (!currentOrderId) return;
    if (!confirm("Raqamni muzlatishni (Freeze) tasdiqlaysizmi?")) return;
    haptic('warning');

    try {
        const res = await fetch('/api/order/freeze', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ order_id: currentOrderId })
        });
        const data = await res.json();
        if (data.success) {
            haptic('success');
            showToast("Raqam muzlatildi 🧊", 'info');
            hideActiveOrder();
            fetchUserMe();
        }
    } catch (err) {
        showToast("Xatolik!", 'error');
    }
}

// API: Cancel Order
async function cancelOrder() {
    if (!currentOrderId) return;
    if (!confirm("Raqamni bekor qilishni tasdiqlaysizmi?")) return;
    haptic('warning');

    try {
        const res = await fetch('/api/order/cancel', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ order_id: currentOrderId })
        });
        const data = await res.json();
        if (data.success) {
            haptic('success');
            showToast("Raqam bekor qilindi ❌", 'info');
            hideActiveOrder();
            fetchUserMe();
        }
    } catch (err) {
        showToast("Xatolik!", 'error');
    }
}

// API: Load Leaderboard
async function loadLeaderboard() {
    const list = document.getElementById('leaderboard-list');
    list.innerHTML = `<div class="p-4 text-center text-xs text-slate-500">Yuklanmoqda...</div>`;

    try {
        const res = await fetch('/api/rating');
        const data = await res.json();
        if (!data.leaders || data.leaders.length === 0) {
            list.innerHTML = `<div class="p-6 text-center text-xs text-slate-500 glass-card rounded-2xl">Hozircha reytingda hech kim yo'q. Birinchi bo'ling!</div>`;
            return;
        }

        list.innerHTML = data.leaders.map((u, i) => `
            <div class="liquid-glass rounded-2xl p-4 flex items-center justify-between">
                <div class="flex items-center gap-3">
                    <div class="w-9 h-9 rounded-xl liquid-blue-icon font-mono font-black text-xs text-cyan-300">
                        #${i + 1}
                    </div>
                    <div>
                        <b class="text-xs text-white block">${u.display_name}</b>
                        <span class="text-[10px] text-slate-400">ID: ${u.user_id}</span>
                    </div>
                </div>
                <div class="text-right">
                    <span class="text-xs font-bold text-cyan-300 font-mono">${u.count} ta</span>
                    <span class="text-[10px] text-slate-400 block">${formatMoney(u.count * 40000)} so'm</span>
                </div>
            </div>
        `).join('');
    } catch (err) {
        list.innerHTML = `<div class="p-4 text-center text-xs text-rose-400">Yuklashda xatolik</div>`;
    }
}

// API: Load History
async function loadHistory() {
    const list = document.getElementById('history-list');
    list.innerHTML = `<div class="p-4 text-center text-xs text-slate-500">Yuklanmoqda...</div>`;

    try {
        const uid = currentUser?.id || 0;
        const res = await fetch(`/api/history?user_id=${uid}`, { headers: getHeaders() });
        const data = await res.json();

        if (!data.history || data.history.length === 0) {
            list.innerHTML = `<div class="p-6 text-center text-xs text-slate-500 liquid-glass rounded-2xl">Buyurtmalar tarixi mavjud emas</div>`;
            return;
        }

        const statusMap = {
            'completed': { label: 'Oldim (Tasdiqlangan)', color: 'text-cyan-300', iconClass: 'liquid-blue-icon', iconSvg: '<svg class=\"w-3.5 h-3.5\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.5\" viewBox=\"0 0 24 24\"><path stroke-linecap=\"round\" stroke-linejoin=\"round\" d=\"M5 13l4 4L19 7\"/></svg>' },
            'frozen': { label: 'Muzlatilgan', color: 'text-sky-300', iconClass: 'liquid-blue-icon', iconSvg: '<span class=\"text-xs\">🧊</span>' },
            'cancelled': { label: 'Bekor qilingan', color: 'text-rose-400', iconClass: 'liquid-red-icon', iconSvg: '<span class=\"text-xs\">✕</span>' },
            'expired': { label: 'Vaqti o\'tgan', color: 'text-amber-400', iconClass: 'liquid-gold-icon', iconSvg: '<span class=\"text-xs\">⏱</span>' },
            'active': { label: 'Faol', color: 'text-cyan-400', iconClass: 'liquid-blue-icon', iconSvg: '<span class=\"w-2 h-2 rounded-full bg-cyan-400 animate-ping\"></span>' }
        };

        list.innerHTML = data.history.map(item => {
            const st = statusMap[item.status] || { label: item.status, color: 'text-slate-400', iconClass: 'liquid-blue-icon', iconSvg: '•' };
            return `
                <div class="liquid-glass rounded-2xl p-4 flex items-center justify-between">
                    <div class="flex items-center gap-3">
                        <div class="w-8 h-8 rounded-xl ${st.iconClass}">
                            ${st.iconSvg}
                        </div>
                        <div>
                            <div class="text-xs font-mono font-bold text-white tracking-wider">
                                ${item.phone}
                            </div>
                            <span class="text-[10px] text-slate-400 mt-0.5 block">${item.created_at ? item.created_at.substring(0, 16) : ''}</span>
                        </div>
                    </div>
                    <div class="text-right">
                        <span class="text-[11px] font-semibold ${st.color}">${st.label}</span>
                    </div>
                </div>
            `;
        }).join('');
    } catch (err) {
        list.innerHTML = `<div class="p-4 text-center text-xs text-rose-400">Yuklashda xatolik</div>`;
    }
}

// API: Submit Withdraw
async function submitWithdraw() {
    const card = document.getElementById('input-card-number').value.replace(/\s+/g, '');
    const amount = Number(document.getElementById('input-withdraw-amount').value);

    if (!card || card.length < 16) {
        showToast("Karta raqami noto'g'ri!", 'error');
        return;
    }
    if (!amount || amount < 100000) {
        showToast("Minimal yechish summasi: 100,000 so'm", 'error');
        return;
    }

    haptic('medium');
    try {
        const uid = currentUser?.id || 0;
        const res = await fetch('/api/withdraw', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({
                user_id: uid,
                amount: amount,
                card_details: card
            })
        });
        const data = await res.json();
        if (data.success) {
            haptic('success');
            showToast("Ariza qabul qilindi! Admin tekshirmoqda.", 'success');
            document.getElementById('input-withdraw-amount').value = '';
            document.getElementById('input-card-number').value = '';
            fetchUserMe();
            loadWithdrawals();
        } else {
            haptic('error');
            showToast(data.error || "Xatolik!", 'error');
        }
    } catch (err) {
        showToast("Server xatosi!", 'error');
    }
}

// API: Load Withdrawals
async function loadWithdrawals() {
    const list = document.getElementById('withdraw-history-list');
    try {
        const uid = currentUser?.id || 0;
        const res = await fetch(`/api/withdrawals?user_id=${uid}`, { headers: getHeaders() });
        const data = await res.json();

        if (!data.withdrawals || data.withdrawals.length === 0) {
            list.innerHTML = `<div class="text-slate-500 text-center py-2">So'rovlar mavjud emas</div>`;
            return;
        }

        list.innerHTML = data.withdrawals.map(w => `
            <div class="flex items-center justify-between py-2 border-b border-sky-400/10 last:border-none">
                <div class="flex items-center gap-2.5">
                    <div class="w-7 h-7 rounded-xl liquid-blue-icon">
                        <svg class="w-3.5 h-3.5 text-cyan-300" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"/></svg>
                    </div>
                    <div>
                        <span class="font-mono text-slate-200 text-xs">${w.card_details}</span>
                        <span class="text-[10px] text-slate-500 block">${w.date ? w.date.substring(0, 16) : ''}</span>
                    </div>
                </div>
                <div class="text-right">
                    <b class="text-cyan-300 font-mono text-xs block">${formatMoney(w.amount)} so'm</b>
                    <span class="text-[10px] font-semibold ${w.status === 'completed' ? 'text-cyan-400' : w.status === 'rejected' ? 'text-rose-400' : 'text-amber-400'}">
                        ${w.status === 'completed' ? 'To\'landi' : w.status === 'rejected' ? 'Rad etildi' : 'Kutilmoqda'}
                    </span>
                </div>
            </div>
        `).join('');
    } catch (err) {}
}

// Format card number on input
document.addEventListener('DOMContentLoaded', () => {
    initUserData();

    const cardInput = document.getElementById('input-card-number');
    if (cardInput) {
        cardInput.addEventListener('input', (e) => {
            let val = e.target.value.replace(/\D/g, '').substring(0, 16);
            let formatted = val.match(/.{1,4}/g)?.join(' ') || val;
            e.target.value = formatted;
        });
    }
});
