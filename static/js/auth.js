// =====================================================================
//  File Server — auth state + login / logout (P2-3 modularization)
//  Kept as a classic script because the per-page inline scripts read the
//  mutable globals (authToken / authRole / authUser) directly; a closed ES
//  module would not reflect those mutations on window. The shared state stays
//  global on purpose.
// =====================================================================

var authToken = localStorage.getItem('fs_token') || '';
var authUser = localStorage.getItem('fs_user') || '';
var authRole = localStorage.getItem('fs_role') || '';
var authNick = localStorage.getItem('fs_nick') || '';
var authMode = 'login'; // login | register

function showLogin() {
    var ls = document.getElementById('loginScreen');
    var app = document.getElementById('appScreen');
    if (ls) ls.style.display = 'flex';
    if (app) app.classList.remove('active');
    applyI18n();
}

function showApp() {
    var ls = document.getElementById('loginScreen');
    var app = document.getElementById('appScreen');
    if (ls) ls.style.display = 'none';
    if (app) app.classList.add('active');
    var ud = document.getElementById('userDisplay');
    if (ud) ud.textContent = authNick || authUser || t('anonymous');
    // User-management entry is for admin + reviewer (home page only)
    var homeUsersCard = document.getElementById('homeUsersCard');
    if (homeUsersCard) homeUsersCard.style.display = (authRole === 'admin' || authRole === 'reviewer') ? 'block' : 'none';
    // Audit-log entry is for ANY authenticated user (but NOT anonymous guests).
    var homeAuditCard = document.getElementById('homeAuditCard');
    if (homeAuditCard) homeAuditCard.style.display = (authRole && authRole !== 'anonymous') ? 'block' : 'none';
    if (authRole === 'admin' || authRole === 'reviewer') startPendingPoll();
}

function switchAuthMode() {
    authMode = authMode === 'login' ? 'register' : 'login';
    var btn = document.getElementById('loginSubmitBtn');
    var sw = document.getElementById('loginSwitch');
    if (btn) btn.textContent = authMode === 'login' ? t('login') : t('register');
    if (sw) sw.textContent = authMode === 'login' ? t('no_account') : t('has_account');
    var sub = document.querySelector('.sub');
    if (sub) sub.textContent = authMode === 'login' ? t('login_sub') : t('register_sub');
    var err = document.getElementById('loginError');
    if (err) err.style.display = 'none';
    var nickRow = document.getElementById('loginNickRow');
    if (nickRow) nickRow.style.display = authMode === 'register' ? 'block' : 'none';
}

function skipLogin() {
    // Enter as an anonymous (read-only guest) visitor. Clear any stale
    // credentials, mark the anonymous session, and load the page content the
    // same way a real login would (otherwise the file list / views never render).
    authToken = ''; authUser = ''; authNick = ''; authRole = 'anonymous';
    localStorage.removeItem('fs_token');
    localStorage.removeItem('fs_user');
    localStorage.removeItem('fs_role');
    localStorage.removeItem('fs_nick');
    localStorage.setItem('fs_anon', '1');
    stopPendingPoll();
    showApp();
    if (typeof onAppReady === 'function') onAppReady();
}

async function doAuth() {
    var u = document.getElementById('loginUser').value.trim();
    var p = document.getElementById('loginPass').value.trim();
    var errEl = document.getElementById('loginError');

    if (!u || !p) { if (errEl) { errEl.textContent = t('fill_fields') || 'Fill all fields'; errEl.style.display = 'block'; } return; }

    var body = {username: u, password: p};
    if (authMode === 'register') {
        var nick = document.getElementById('loginNick').value.trim();
        if (nick) body.nickname = nick;
    }

    var url = authMode === 'login' ? '/api/auth/login' : '/api/auth/register';
    try {
        var res = await fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        var data = await res.json();
        if (data.ok && data.token) {
            authToken = data.token;
            authUser = u;
            authRole = data.role || '';
            authNick = data.nickname || '';
            localStorage.setItem('fs_token', authToken);
            localStorage.setItem('fs_user', authUser);
            localStorage.setItem('fs_role', authRole);
            localStorage.setItem('fs_nick', authNick);
            if (data.require_password_change) {
                // First login on default/weak credentials: force a change
                // before the user can reach anything.
                showForcePwChange();
            } else {
                localStorage.removeItem('fs_anon');
                stopPendingPoll();
                showApp();
                if (authRole === 'admin' || authRole === 'reviewer') startPendingPoll();
                if (typeof onAppReady === 'function') onAppReady();
            }
        } else if (data.ok && !data.token) {
            if (errEl) {
                errEl.textContent = t('pending_approval') || 'Registration submitted, pending admin approval';
                errEl.style.color = 'var(--green)';
                errEl.style.display = 'block';
            }
            document.getElementById('loginUser').value = '';
            document.getElementById('loginPass').value = '';
            switchAuthMode();
            authMode = 'login';
        } else {
            if (errEl) {
                errEl.textContent = data.message || data.detail || 'Error';
                errEl.style.color = 'var(--danger)';
                errEl.style.display = 'block';
            }
        }
    } catch(e) {
        if (errEl) { errEl.textContent = t('net_error') || 'Network error'; errEl.style.display = 'block'; }
    }
}

// Force a password change on first login (default/weak credentials).
function showForcePwChange() {
    if (document.getElementById('forcePwModal')) return;
    var div = document.createElement('div');
    div.id = 'forcePwModal';
    div.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:9999;';
    div.innerHTML =
        '<div style="background:#fff;padding:24px;border-radius:12px;width:340px;max-width:92%;box-shadow:0 8px 30px rgba(0,0,0,.2);">' +
        '<h3 style="margin:0 0 8px;font-size:16px;">请修改默认密码</h3>' +
        '<p style="font-size:13px;color:#666;margin:0 0 14px;line-height:1.5;">出于安全考虑，首次登录必须修改默认密码后才能继续使用。</p>' +
        '<input id="fpwOld" type="password" placeholder="当前密码" style="width:100%;padding:9px;margin-bottom:8px;box-sizing:border-box;border:1px solid #ccc;border-radius:8px;">' +
        '<input id="fpwNew" type="password" placeholder="新密码" style="width:100%;padding:9px;margin-bottom:8px;box-sizing:border-box;border:1px solid #ccc;border-radius:8px;">' +
        '<input id="fpwNew2" type="password" placeholder="确认新密码" style="width:100%;padding:9px;margin-bottom:8px;box-sizing:border-box;border:1px solid #ccc;border-radius:8px;">' +
        '<div id="fpwErr" style="color:#c0392b;font-size:12px;min-height:16px;margin-bottom:6px;"></div>' +
        '<button id="fpwSubmit" style="width:100%;padding:10px;background:#185FA5;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;">修改密码</button>' +
        '</div>';
    document.body.appendChild(div);
    document.getElementById('fpwSubmit').addEventListener('click', submitForcePwChange);
    var o = document.getElementById('fpwOld'); if (o) o.focus();
}

async function submitForcePwChange() {
    var old = document.getElementById('fpwOld').value;
    var n1 = document.getElementById('fpwNew').value;
    var n2 = document.getElementById('fpwNew2').value;
    var err = document.getElementById('fpwErr');
    if (!old || !n1 || !n2) { err.textContent = '请填写所有字段'; return; }
    if (n1 !== n2) { err.textContent = '两次输入的新密码不一致'; return; }
    if (n1.length < 3) { err.textContent = '新密码至少 3 位'; return; }
    try {
        var res = await fetch('/api/auth/me/password', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + authToken},
            body: JSON.stringify({old_password: old, new_password: n1})
        });
        var data = await res.json();
        if (res.ok) {
            var m = document.getElementById('forcePwModal'); if (m) m.remove();
            localStorage.removeItem('fs_anon');
            stopPendingPoll();
            showApp();
            if (authRole === 'admin' || authRole === 'reviewer') startPendingPoll();
            if (typeof onAppReady === 'function') onAppReady();
        } else {
            err.textContent = data.message || data.detail || '修改失败';
        }
    } catch (e) {
        err.textContent = '网络错误';
    }
}

function doLogout() {
    var tkn = authToken;
    authToken = ''; authUser = ''; authRole = ''; authNick = '';
    localStorage.removeItem('fs_token');
    localStorage.removeItem('fs_user');
    localStorage.removeItem('fs_role');
    localStorage.removeItem('fs_nick');
    localStorage.removeItem('fs_anon');
    stopPendingPoll();
    if (tkn) {
        try { fetch('/api/auth/logout', { method: 'POST', headers: { 'Authorization': 'Bearer ' + tkn } }); } catch (e) {}
    }
    showLogin();
}

// Called when the server rejects the current token (401). Clears local state
// and returns to the login screen instead of showing a misleading message.
function forceLogout(reason) {
    authToken = ''; authUser = ''; authRole = ''; authNick = '';
    localStorage.removeItem('fs_token');
    localStorage.removeItem('fs_user');
    localStorage.removeItem('fs_role');
    localStorage.removeItem('fs_nick');
    localStorage.removeItem('fs_anon');
    stopPendingPoll();
    showLogin();
    var errEl = document.getElementById('loginError');
    if (errEl) {
        errEl.textContent = reason || (t('login_required') || 'Session expired, please log in again');
        errEl.style.display = 'block';
    }
}

// Enter key on login
document.addEventListener('keydown', function(e) {
    var ls = document.getElementById('loginScreen');
    if (e.key === 'Enter' && ls && ls.style.display !== 'none') {
        doAuth();
    }
});

function getAuthHeaders() {
    return authToken ? {'Authorization': 'Bearer ' + authToken} : {};
}

// Token query param for browser-native requests (<img src>, <a download>) that
// cannot carry an Authorization header. The backend also accepts ?token=.
function getTokenParam() {
    return authToken ? ('?token=' + encodeURIComponent(authToken)) : '';
}

// Build an authenticated download URL usable by <img>/<a>.
function downloadUrl(path) {
    return '/api/download/' + encodeURIComponent(path) + getTokenParam();
}
