// =====================================================================
//  Settings view (Phase A SPA split of settings.html)
//  Markup: <template id="tpl-settings"> in index.html.
//  Navigation is owned by shell.js (goSettings -> location.hash '#/settings').
// =====================================================================

// ==================== Site settings (admin only) ====================
async function loadSiteName() {
    if (authRole !== 'admin') return;
    try {
        var res = await fetch('/api/admin/site', { headers: getAuthHeaders() });
        if (res.ok) {
            var d = await res.json();
            var inp = document.getElementById('siteNameInput');
            if (inp && d.name) inp.value = d.name;
        } else {
            onSettingLoadFail(res.status);
        }
    } catch (e) {
        toast('加载站点名称失败：网络错误', true);
    }
}

async function saveSiteName() {
    var inp = document.getElementById('siteNameInput');
    if (!inp) return;
    var name = inp.value.trim();
    if (!name) { toast(t('fill_fields') || 'Fill all fields', true); return; }
    var btn = document.getElementById('saveSiteBtn');
    if (btn) btn.disabled = true;
    try {
        var res = await fetch('/api/admin/site', {
            method: 'PUT',
            headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
            body: JSON.stringify({ name: name })
        });
        var data = null;
        try { data = await res.json(); } catch (e) { data = {}; }
        if (res.ok && data && data.ok) {
            try { setAppName(data.name || name); } catch (e) {}
            var msg = (t('site_saved') || 'Saved');
            if (data.persisted === false) msg += '（未持久化，重启后可能失效）';
            toast(msg);
            var hint = document.getElementById('siteSavedHint');
            if (hint) { hint.style.display = 'block'; hint.textContent = (t('site_saved') || 'Saved'); }
        } else {
            onSettingSaveFail(res.status, data);
        }
    } catch (e) {
        var detail = (e && e.message) ? e.message : '';
        toast((t('net_error') || 'Network error') + (detail ? (': ' + detail) : ''), true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

// ==================== Max upload size (admin only) ====================
async function loadUploadLimit() {
    if (authRole !== 'admin') return;
    try {
        var res = await fetch('/api/admin/setting/max_upload_size_mb', { headers: getAuthHeaders() });
        if (res.ok) {
            var d = await res.json();
            var inp = document.getElementById('maxUploadMbInput');
            if (inp && typeof d.value !== 'undefined') inp.value = d.value;
        } else {
            onSettingLoadFail(res.status);
        }
    } catch (e) {
        toast('加载上传上限失败：网络错误', true);
    }
}

async function saveUploadLimit() {
    var inp = document.getElementById('maxUploadMbInput');
    if (!inp) return;
    var raw = (inp.value || '').trim();
    if (!raw) { toast(t('fill_fields') || 'Fill all fields', true); return; }
    var mb = parseInt(raw, 10);
    if (isNaN(mb) || mb < 1) { toast('最小 1 MB', true); return; }
    var btn = document.getElementById('saveUploadBtn');
    if (btn) btn.disabled = true;
    try {
        var res = await fetch('/api/admin/setting/max_upload_size_mb', {
            method: 'PUT',
            headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
            body: JSON.stringify({ value: mb })
        });
        var data = null;
        try { data = await res.json(); } catch (e) { data = {}; }
        if (res.ok && data && data.ok) {
            var shown = (data.value != null) ? data.value : mb;
            var msg = (t('upload_saved') || 'Saved') + '：' + shown + ' MB';
            if (data.persisted === false) msg += '（未持久化，重启后可能失效）';
            toast(msg);
            var hint = document.getElementById('uploadLimitHint');
            if (hint) { hint.style.display = 'inline'; hint.textContent = (t('upload_saved') || 'Saved'); }
        } else {
            onSettingSaveFail(res.status, data);
        }
    } catch (e) {
        var detail = (e && e.message) ? e.message : '';
        toast((t('net_error') || 'Network error') + (detail ? (': ' + detail) : ''), true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

// ==================== Per-user quota (admin only) ====================
async function loadQuota() {
    if (authRole !== 'admin') return;
    try {
        var res = await fetch('/api/admin/setting/max_user_upload_mb', { headers: getAuthHeaders() });
        if (res.ok) {
            var d = await res.json();
            var inp = document.getElementById('maxUploadQuotaMbInput');
            if (inp && typeof d.value !== 'undefined') inp.value = d.value;
        } else { onSettingLoadFail(res.status); }
    } catch (e) { toast('加载容量配额失败：网络错误', true); }
}

async function saveQuota() {
    var inp = document.getElementById('maxUploadQuotaMbInput');
    if (!inp) return;
    var raw = (inp.value || '').trim();
    if (!raw) { toast('请填写数值（0=关闭）', true); return; }
    var mb = parseInt(raw, 10);
    if (isNaN(mb) || mb < 0) { toast('数值需 ≥ 0', true); return; }
    var btn = document.getElementById('saveQuotaBtn');
    if (btn) btn.disabled = true;
    try {
        var res = await fetch('/api/admin/setting/max_user_upload_mb', {
            method: 'PUT',
            headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
            body: JSON.stringify({ value: mb })
        });
        var data = null; try { data = await res.json(); } catch (e) { data = {}; }
        if (res.ok && data && data.ok) {
            var shown = (data.value != null) ? data.value : mb;
            var msg = '配额已保存：' + shown + ' MB';
            if (data.persisted === false) msg += '（未持久化，重启后可能失效）';
            toast(msg);
            var hint = document.getElementById('quotaHint');
            if (hint) { hint.style.display = 'inline'; hint.textContent = '已保存'; }
        } else {
            onSettingSaveFail(res.status, data);
        }
    } catch (e) {
        var detail = (e && e.message) ? e.message : '';
        toast('网络错误' + (detail ? (': ' + detail) : ''), true);
    } finally { if (btn) btn.disabled = false; }
}

// ==================== Upload rate limit (admin only) ====================
async function loadRateLimit() {
    if (authRole !== 'admin') return;
    try {
        var res = await fetch('/api/admin/setting/upload_rate_limit', { headers: getAuthHeaders() });
        if (res.ok) {
            var d = await res.json();
            var inp = document.getElementById('uploadRateInput');
            if (inp && typeof d.value !== 'undefined') inp.value = d.value;
        } else { onSettingLoadFail(res.status); }
    } catch (e) { toast('加载上传频控失败：网络错误', true); }
}

async function saveRateLimit() {
    var inp = document.getElementById('uploadRateInput');
    if (!inp) return;
    var raw = (inp.value || '').trim();
    if (!raw) { toast('请填写数值（0=关闭）', true); return; }
    var n = parseInt(raw, 10);
    if (isNaN(n) || n < 0) { toast('数值需 ≥ 0', true); return; }
    var btn = document.getElementById('saveRateBtn');
    if (btn) btn.disabled = true;
    try {
        var res = await fetch('/api/admin/setting/upload_rate_limit', {
            method: 'PUT',
            headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
            body: JSON.stringify({ value: n })
        });
        var data = null; try { data = await res.json(); } catch (e) { data = {}; }
        if (res.ok && data && data.ok) {
            var shown = (data.value != null) ? data.value : n;
            var msg = '上传频控已保存：' + shown + ' 次/窗口';
            if (data.persisted === false) msg += '（未持久化，重启后可能失效）';
            toast(msg);
            var hint = document.getElementById('rateHint');
            if (hint) { hint.style.display = 'inline'; hint.textContent = '已保存'; }
        } else {
            onSettingSaveFail(res.status, data);
        }
    } catch (e) {
        var detail = (e && e.message) ? e.message : '';
        toast('网络错误' + (detail ? (': ' + detail) : ''), true);
    } finally { if (btn) btn.disabled = false; }
}

// ----- Shared admin-settings helpers -----
function onSettingLoadFail(status) {
    if (status === 401 || status === 403) {
        toast('会话已过期或权限不足，请重新登录', true);
        forceLogout('会话已过期，请重新登录');
    } else {
        toast('加载设置失败（HTTP ' + status + '）', true);
    }
}

function onSettingSaveFail(status, data) {
    if (status === 401 || status === 403) {
        toast('会话已过期或权限不足，请重新登录', true);
        forceLogout('会话已过期，请重新登录');
    } else if (status === 404) {
        toast('服务端未找到该设置项，请重启服务后重试', true);
    } else {
        var msg = (data && (data.detail || data.message)) || '保存失败';
        toast(msg, true);
    }
}

async function ensureAdminSession() {
    if (authRole !== 'admin') return false;
    try {
        var res = await fetch('/api/auth/me', { headers: getAuthHeaders() });
        if (!res.ok) {
            onSettingLoadFail(res.status);
            return false;
        }
        return true;
    } catch (e) {
        toast('无法连接服务器，请确认服务已启动', true);
        return false;
    }
}

// Show the site-settings editor only for admin accounts; everyone else
// sees the generic "module under development" placeholder instead.
async function setupSettingsView() {
    var isAdmin = (authRole === 'admin');
    var panelSite = document.getElementById('panelSite');
    var noSettings = document.getElementById('noSettingsMsg');
    if (panelSite) panelSite.style.display = isAdmin ? 'block' : 'none';
    if (noSettings) noSettings.style.display = isAdmin ? 'none' : 'block';
    if (!isAdmin) return;
    if (!await ensureAdminSession()) return;
    loadSiteName(); loadUploadLimit(); loadQuota(); loadRateLimit();
}

// ---- mount / unmount (SPA) ----
window.Views = window.Views || {};
window.Views.settings = {
    mount: function () {
        setupSettingsView();
    },
    unmount: function () {}
};
