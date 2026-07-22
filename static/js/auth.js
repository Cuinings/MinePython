// =====================================================================
//  MinePython — auth state + login / logout (P2-3 modularization)
//  Kept as a classic script because the per-page inline scripts read the
//  mutable globals (authToken / authRole / authUser) directly; a closed ES
//  module would not reflect those mutations on window. The shared state stays
//  global on purpose.
// =====================================================================

var authToken = localStorage.getItem('fs_token') || '';
var authUser = localStorage.getItem('fs_user') || '';
var authRole = localStorage.getItem('fs_role') || '';
var authNick = localStorage.getItem('fs_nick') || '';

// The auth UI now lives on standalone pages (login.html / register.html).
// Anything that used to reveal the inline login screen now bounces there.
function showLogin() {
    window.location.href = 'login.html';
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

function skipLogin() {
    // Enter as an anonymous (read-only guest) visitor. Clear any stale
    // credentials, mark the anonymous session, and jump straight into the app.
    authToken = ''; authUser = ''; authNick = ''; authRole = 'anonymous';
    localStorage.removeItem('fs_token');
    localStorage.removeItem('fs_user');
    localStorage.removeItem('fs_role');
    localStorage.removeItem('fs_nick');
    localStorage.setItem('fs_anon', '1');
    stopPendingPoll();
    window.location.href = 'index.html';
}

// Small helpers shared by doLogin / doRegister.
function showAuthError(el, msg, ok) {
    if (!el) return;
    el.textContent = msg;
    el.style.color = ok ? 'var(--green)' : 'var(--danger)';
    el.style.display = 'block';
}
function clearAuthFields() {
    var u = document.getElementById('loginUser');
    var p = document.getElementById('loginPass');
    var n = document.getElementById('loginNick');
    if (u) u.value = '';
    if (p) p.value = '';
    if (n) n.value = '';
}

async function doLogin() {
    var u = document.getElementById('loginUser').value.trim();
    var p = document.getElementById('loginPass').value.trim();
    var errEl = document.getElementById('loginError');
    if (!u || !p) { showAuthError(errEl, t('fill_fields') || 'Fill all fields'); return; }

    try {
        var res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username: u, password: p})
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
            localStorage.removeItem('fs_anon');
            if (data.require_password_change) {
                // First login on default/weak credentials: force a change
                // before the user can reach anything.
                showForcePwChange();
            } else {
                window.location.href = 'index.html';
            }
        } else {
            showAuthError(errEl, data.message || data.detail || 'Error');
        }
    } catch (e) {
        showAuthError(errEl, t('net_error') || 'Network error');
    }
}

async function doRegister() {
    var u = document.getElementById('loginUser').value.trim();
    var p = document.getElementById('loginPass').value.trim();
    var errEl = document.getElementById('loginError');
    if (!u || !p) { showAuthError(errEl, t('fill_fields') || 'Fill all fields'); return; }

    var body = {username: u, password: p};
    var nick = document.getElementById('loginNick');
    if (nick && nick.value.trim()) body.nickname = nick.value.trim();

    try {
        var res = await fetch('/api/auth/register', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        var data = await res.json();
        if (data.ok && data.token) {
            // Auto-activated account: log straight in.
            authToken = data.token;
            authUser = u;
            authRole = data.role || '';
            authNick = data.nickname || '';
            localStorage.setItem('fs_token', authToken);
            localStorage.setItem('fs_user', authUser);
            localStorage.setItem('fs_role', authRole);
            localStorage.setItem('fs_nick', authNick);
            localStorage.removeItem('fs_anon');
            window.location.href = 'index.html';
        } else if (data.ok && !data.token) {
            // Pending admin approval: tell the user, then send them to login.
            clearAuthFields();
            showAuthError(errEl, t('pending_approval') || 'Registration submitted, pending admin approval', true);
            setTimeout(function () { window.location.href = 'login.html'; }, 1800);
        } else {
            showAuthError(errEl, data.message || data.detail || 'Error');
        }
    } catch (e) {
        showAuthError(errEl, t('net_error') || 'Network error');
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
            // The auth page has no app screen — go to the app after the change.
            window.location.href = 'index.html';
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

// Enter-to-submit is wired per page (login.html / register.html) so each
// page can call the correct handler.

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
