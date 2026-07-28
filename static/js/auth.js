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
// Opaque refresh token (ARCH-9). Used only to renew the access token; never
// sent as a Bearer credential. Stored separately so the global fetch
// interceptor can rotate sessions silently on a 401.
var authRefresh = localStorage.getItem('fs_refresh') || '';
// Effective permission codes for the current user (refreshed on renew).
var authPerms = [];
// Whether the current account is the protected bootstrap/default account.
// Default accounts cannot be deactivated, so the UI hides that entry for them.
var authIsDefault = localStorage.getItem('fs_isdef') === '1';
// The configured bootstrap admin username (exposed by /api/auth/me). Kept in
// memory only: if the DB is_default flag is missing on a legacy database, the
// UI can still fall back to matching the known built-in admin name.
var authBootstrapAdmin = 'admin';

// Keep the default-account flag in sync with a fresh profile payload.
function applyAccountFlags(d) {
    authIsDefault = !!(d && d.is_default);
    if (d && d.admin_username) authBootstrapAdmin = d.admin_username;
    try { localStorage.setItem('fs_isdef', authIsDefault ? '1' : '0'); } catch (e) {}
}

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
    // The "用户中心" entry is shown to every authenticated user (including
    // anonymous guests, who are bounced back to home from the center page).
    // Hide it only for the truly unauthenticated corner cases.
    // Audit-log entry is for ANY authenticated user (but NOT anonymous guests).
    var homeAuditCard = document.getElementById('homeAuditCard');
    if (homeAuditCard) homeAuditCard.style.display = (authRole && authRole !== 'anonymous') ? '' : 'none';
    if (authRole === 'admin' || authRole === 'reviewer') startPendingPoll();
}

// Navigate to the User Center. Optional `tab` deep-links to a panel
// ('userinfo' | 'usermgmt' | 'settings'), e.g. from the pending-approvals bar.
function goUserCenter(tab) {
    var url = 'users.html' + (tab ? ('?tab=' + tab) : '');
    window.location.href = url;
}

function skipLogin() {
    // Enter as an anonymous (read-only guest) visitor. Clear any stale
    // credentials, mark the anonymous session, and jump straight into the app.
    authToken = ''; authUser = ''; authNick = ''; authRole = 'anonymous'; authIsDefault = false; authRefresh = ''; authPerms = [];
    localStorage.removeItem('fs_token');
    localStorage.removeItem('fs_user');
    localStorage.removeItem('fs_role');
    localStorage.removeItem('fs_nick');
    localStorage.removeItem('fs_isdef');
    localStorage.removeItem('fs_refresh');
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
            if (data.refresh_in_cookie) {
                // Refresh token lives in an httpOnly cookie (XSS can't read it).
                authRefresh = ''; localStorage.removeItem('fs_refresh');
            } else if (data.refresh_token) {
                authRefresh = data.refresh_token; localStorage.setItem('fs_refresh', authRefresh);
            }
            if (data.permissions) authPerms = data.permissions;
            applyAccountFlags(data);
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
                // replace() drops the login page from history so the back
                // button can't return to it after a successful login.
                window.location.replace('index.html');
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
            if (data.refresh_in_cookie) {
                authRefresh = ''; localStorage.removeItem('fs_refresh');
            } else if (data.refresh_token) {
                authRefresh = data.refresh_token; localStorage.setItem('fs_refresh', authRefresh);
            }
            if (data.permissions) authPerms = data.permissions;
            applyAccountFlags(data);
            localStorage.setItem('fs_token', authToken);
            localStorage.setItem('fs_user', authUser);
            localStorage.setItem('fs_role', authRole);
            localStorage.setItem('fs_nick', authNick);
            localStorage.removeItem('fs_anon');
            // replace() so the register page is dropped from history on a
            // successful auto-login — back button won't return to it.
            window.location.replace('index.html');
        } else if (data.ok && !data.token) {
            // Pending admin approval: tell the user, then send them to login.
            clearAuthFields();
            showAuthError(errEl, t('pending_approval') || 'Registration submitted, pending admin approval', true);
            setTimeout(function () { window.location.replace('login.html'); }, 1800);
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
        '<div class="modal-card" style="width:340px;max-width:92%;padding:24px">' +
        '<h3 style="margin:0 0 8px;font-size:16px;color:var(--text)">请修改默认密码</h3>' +
        '<p style="font-size:13px;color:var(--dim);margin:0 0 14px;line-height:1.5;">出于安全考虑，首次登录必须修改默认密码后才能继续使用。</p>' +
        '<input id="fpwOld" type="password" placeholder="当前密码">' +
        '<input id="fpwNew" type="password" placeholder="新密码">' +
        '<input id="fpwNew2" type="password" placeholder="确认新密码">' +
        '<div id="fpwErr" style="color:var(--danger);font-size:12px;min-height:16px;margin-bottom:6px;"></div>' +
        '<button id="fpwSubmit" style="width:100%;padding:10px;background:var(--accent);color:#fff;border:none;border-radius:var(--r-sm);cursor:pointer;font-size:14px">修改密码</button>' +
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
            // replace() so the forced login/change screen is not in the back
            // stack and the user can't return to it after landing in the app.
            window.location.replace('index.html');
        } else {
            err.textContent = data.message || data.detail || '修改失败';
        }
    } catch (e) {
        err.textContent = '网络错误';
    }
}

function doLogout() {
    var tkn = authToken;
    var rft = authRefresh;
    authToken = ''; authUser = ''; authRole = ''; authNick = ''; authIsDefault = false; authRefresh = ''; authPerms = [];
    localStorage.removeItem('fs_token');
    localStorage.removeItem('fs_user');
    localStorage.removeItem('fs_role');
    localStorage.removeItem('fs_nick');
    localStorage.removeItem('fs_isdef');
    localStorage.removeItem('fs_refresh');
    localStorage.removeItem('fs_anon');
    stopPendingPoll();
    if (tkn) {
        // Revoke the refresh token so the session cannot be renewed (ARCH-9).
        // credentials: 'same-origin' also clears the httpOnly refresh cookie
        // when REFRESH_TOKEN_IN_COOKIE is enabled.
        try {
            fetch('/api/auth/logout', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tkn },
                credentials: 'same-origin',
                body: JSON.stringify({ refresh_token: rft || '' })
            });
        } catch (e) {}
    }
    // Use replace (not push) so the app page is wiped from the history stack:
    // after logout, pressing Back cannot return to any in-app page.
    window.location.replace('login.html');
}

// Global "session expired / must re-login" modal. Called by forceLogout so the
// user gets a clear, non-jarring interaction instead of a silent hard redirect
// to the login page. The current page stays visible behind the overlay until
// the user clicks "重新登录".
function showSessionExpiredModal(reason) {
    if (document.getElementById('sessionExpiredModal')) return;  // dedupe
    var overlay = document.createElement('div');
    overlay.id = 'sessionExpiredModal';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.55);' +
        'display:flex;align-items:center;justify-content:center;z-index:99999;';
    var title = t('session_expired_title') || '登录已失效';
    var msg = reason || (t('session_expired_msg') || '您的登录状态已过期，请重新登录以继续。');
    var btnLabel = t('relogin') || '重新登录';
    overlay.innerHTML =
        '<div style="width:360px;max-width:92%;background:var(--card);color:var(--text);' +
        'border:1px solid var(--border);border-radius:var(--r-md,12px);padding:24px;' +
        'box-shadow:0 12px 40px rgba(0,0,0,.35);text-align:center;">' +
        '<div style="font-size:34px;line-height:1;margin-bottom:10px;">🔒</div>' +
        '<h3 style="margin:0 0 10px;font-size:17px;">' + title + '</h3>' +
        '<p style="margin:0 0 12px;font-size:13px;color:var(--dim);line-height:1.6;">' + msg + '</p>' +
        '<div id="seCountdown" style="font-size:12px;color:var(--dim);margin-bottom:16px;min-height:16px;"></div>' +
        '<button id="seReloginBtn" style="width:100%;padding:11px;background:var(--accent);' +
        'color:#fff;border:none;border-radius:var(--r-sm,8px);cursor:pointer;font-size:14px;">' +
        btnLabel + '</button>' +
        '</div>';
    document.body.appendChild(overlay);
    // Auto-redirect to login after a short countdown; the button is always
    // available for an immediate jump. Clearing the interval on click avoids a
    // second navigation after the manual one.
    var secs = 5;
    var cd = document.getElementById('seCountdown');
    function tick() {
        if (cd) cd.textContent = (t('relogin_auto') || '将在 {n} 秒后自动跳转').replace('{n}', secs);
    }
    tick();
    var timer = setInterval(function () {
        secs -= 1;
        if (secs <= 0) {
            clearInterval(timer);
            showLogin();
        } else {
            tick();
        }
    }, 1000);
    var btn = document.getElementById('seReloginBtn');
    if (btn) btn.addEventListener('click', function () {
        clearInterval(timer);
        showLogin();
    });
}

// Called when the server rejects the current token (401), the refresh token is
// dead, or the account was force-changed/deactivated. Clears local state and
// shows a clear "session expired" interaction instead of a silent hard redirect
// (the old code wrote the message onto the page being unloaded, so the user
// never saw it) or a silent 401 leak to the caller.
function forceLogout(reason) {
    authToken = ''; authUser = ''; authRole = ''; authNick = ''; authIsDefault = false; authRefresh = ''; authPerms = [];
    localStorage.removeItem('fs_token');
    localStorage.removeItem('fs_user');
    localStorage.removeItem('fs_role');
    localStorage.removeItem('fs_nick');
    localStorage.removeItem('fs_isdef');
    localStorage.removeItem('fs_refresh');
    localStorage.removeItem('fs_anon');
    stopPendingPoll();
    showSessionExpiredModal(reason);
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

// ---------------------------------------------------------------------------
// Global fetch interceptor (ARCH-9): transparent token refresh.
// Every page loads this classic script, so patching window.fetch once here
// covers all API calls app-wide — no per-page refactor needed.
//
//   * injects `Authorization: Bearer <access>` on every request that has one,
//   * on a 401, silently calls /api/auth/refresh ONCE and retries the request
//     with the new access token (rotation),
//   * if refresh fails (or there is no refresh token), force-logs the user out.
// Browser-native requests (<img src>, <a download>) keep using ?token=<access>
// via getTokenParam() and are NOT intercepted — those simply re-auth on next
// full page load if the access token has lapsed.
// ---------------------------------------------------------------------------
(function () {
    if (window.__fsFetchPatched) return;
    window.__fsFetchPatched = true;
    var _nativeFetch = window.fetch ? window.fetch.bind(window) : null;
    if (!_nativeFetch) return;  // ancient browser without fetch — leave as-is.

    // Try to swap the expired access token for a fresh pair. Returns the new
    // access token string, or null on failure. Uses the raw native fetch so we
    // never recurse into this interceptor.
    async function _silentRefresh() {
        // In cookie mode the refresh token is sent automatically as an httpOnly
        // cookie (credentials: 'same-origin'); in localStorage mode we pass it
        // in the body. Either way the call renews the access token.
        var bodyObj = authRefresh ? { refresh_token: authRefresh } : {};
        try {
            var r = await _nativeFetch('/api/auth/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify(bodyObj)
            });
            if (!r.ok) return null;
            var d = await r.json();
            if (!d || !d.ok || !d.access_token) return null;
            authToken = d.access_token;
            if (d.username) authUser = d.username;
            if (d.role) authRole = d.role;
            if (d.nickname) authNick = d.nickname;
            if (d.permissions) authPerms = d.permissions;
            if (d.refresh_in_cookie) {
                authRefresh = ''; localStorage.removeItem('fs_refresh');
            } else if (d.refresh_token) {
                authRefresh = d.refresh_token; localStorage.setItem('fs_refresh', authRefresh);
            }
            localStorage.setItem('fs_token', authToken);
            if (d.nickname) localStorage.setItem('fs_nick', d.nickname);
            return authToken;
        } catch (e) {
            return null;
        }
    }

    window.fetch = async function (input, init) {
        init = init || {};
        // Copy headers from either the provided init or a Request object, so we
        // never strip headers the caller already set.
        var src = (init && init.headers) ? init.headers : (input && input.headers);
        var headers = new Headers(src || {});
        if (authToken && !headers.has('Authorization')) {
            headers.set('Authorization', 'Bearer ' + authToken);
        }
        init.headers = headers;

        var resp = await _nativeFetch(input, init);

        if (resp.status === 401) {
            if (authRefresh) {
                // Only attempt one silent renewal to avoid refresh storms.
                var newTok = await _silentRefresh();
                if (newTok) {
                    headers.set('Authorization', 'Bearer ' + newTok);
                    init.headers = headers;
                    resp = await _nativeFetch(input, init);
                } else {
                    // Refresh failed — the session is dead; surface it.
                    forceLogout(t('session_expired_msg') || '登录已失效，请重新登录');
                }
            } else {
                // No refresh token (e.g. httpOnly cookie lost / anonymous edge):
                // previously this fell through and leaked a raw 401 to the
                // caller, leaving the page to fail silently. Treat the session
                // as dead and prompt re-login.
                forceLogout(t('session_expired_msg') || '登录已失效，请重新登录');
            }
        }
        return resp;
    };
})();
