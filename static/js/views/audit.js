// =====================================================================
//  Audit log view (Phase A SPA split of audit.html)
//  Markup: <template id="tpl-audit"> in index.html.
//  Navigation is owned by shell.js.
// =====================================================================

var _auditCache = [];
var _canViewAll = false;
var _canPurge = false;

// The audit page requires a real logged-in account. Anonymous guests are
// bounced back to the home page (mount-level safety net; the shell already
// gates, but this keeps deep links safe).
function setupAuditPage() {
    var userScope = document.getElementById('userScope');
    var selfNote = document.getElementById('selfNote');
    if (_canViewAll) {
        if (userScope) {
            userScope.style.display = '';
            userScope.value = '';        // default: 全部用户
            loadUserScopeOptions();
        }
        if (selfNote) selfNote.style.display = 'none';
    } else {
        if (userScope) userScope.style.display = 'none';
        if (selfNote) selfNote.style.display = 'block';
    }
}

// Populate the single dropdown with every account (reviewer/admin only), so the
// one control covers 仅本人 / 全部用户 / 具体用户. Idempotent.
async function loadUserScopeOptions() {
    var sel = document.getElementById('userScope');
    if (!sel) return;
    try {
        var res = await fetch('/api/admin/users', { headers: getAuthHeaders() });
        if (!res.ok) return;
        var data = await res.json();
        var keep = Array.prototype.slice.call(sel.options, 0, 2);  // 仅本人 + 全部用户
        sel.innerHTML = '';
        keep.forEach(function (o) { sel.appendChild(o); });
        (data.users || []).forEach(function (u) {
            var uname = u.username || u;
            if (!uname) return;
            var opt = document.createElement('option');
            opt.value = uname;
            opt.textContent = u.nickname || uname;
            sel.appendChild(opt);
        });
    } catch (e) { /* non-fatal: keep the two default scopes */ }
}

async function loadAuditPublic(retry) {
    var list = document.getElementById('auditList');
    if (!list) return;
    var params = new URLSearchParams();
    params.set('page', '1');
    params.set('page_size', '100');
    var action = document.getElementById('auditAction');
    if (action && action.value) params.set('action', action.value);
    var search = document.getElementById('auditSearch');
    if (search && search.value.trim()) params.set('search', search.value.trim());

    // Non-admins are server-scoped to their own rows. Admins/reviewers drive
    // the single dropdown: 'self' -> own, '' -> all, <username> -> that account.
    if (_canViewAll) {
        var sel = document.getElementById('userScope');
        var v = sel ? sel.value : '';
        if (v === 'self') {
            params.set('user_filter', authUser);
        } else if (v) {
            params.set('user_filter', v);
        }
    }

    try {
        var res = await fetch('/api/audit/logs?' + params.toString(), { headers: getAuthHeaders() });
        if (!res.ok) {
            if (!retry) { return loadAuditPublic(true); }
            list.innerHTML = '<div class="empty">' + (t('toast_failed') || 'Failed') + '</div>';
            return;
        }
    var data = await res.json();
    _auditCache = data.logs || [];
    _canPurge = !!data.can_purge;
    if (typeof toggleClearBtn === 'function') toggleClearBtn();
    renderAuditList(_auditCache);
    } catch (e) {
        list.innerHTML = '<div class="empty">' + (t('toast_failed') || 'Failed') + '</div>';
    }
}

function toggleClearBtn() {
    var btn = document.getElementById('btnClearAudit');
    if (btn) btn.style.display = _canPurge ? 'inline-block' : 'none';
}

async function clearAudit() {
    if (!_canPurge) return;
    var msg = (t('audit_clear_confirm') ||
        '确定要清空全部审计日志吗？此操作不可逆，且会记录一条「审计已清空」的留存记录。');
    if (!confirm(msg)) return;
    // Second, explicit confirmation guard against accidental clicks.
    if (!confirm((t('audit_clear_confirm2') || '再次确认：所有审计记录将被永久删除，无法恢复。'))) return;
    try {
        var res = await fetch('/api/admin/audit/clear', {
            method: 'POST',
            headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
            body: JSON.stringify({ confirm: true }),
        });
        var data = await res.json().catch(function () { return {}; });
        if (!res.ok) {
            toast((data.detail || t('toast_failed') || 'Failed'));
            return;
        }
        toast((t('audit_cleared') || '审计日志已清空') + '（' + (data.cleared || 0) + ' 条）');
        await loadAuditPublic();
    } catch (e) {
        toast(t('toast_failed') || 'Failed');
    }
}

function renderAuditList(logs) {
    var list = document.getElementById('auditList');
    if (!list) return;
    if (!logs.length) {
        list.innerHTML = '<div class="empty">' + (t('no_audit') || 'No audit records') +
            '<div style="margin-top:12px"><button class="btn btn-xs" onclick="loadAuditPublic()">' + (t('audit_refresh') || 'Refresh') + '</button></div></div>';
        return;
    }
    var html = '<div class="audit-row audit-head">' +
        '<span>' + (t('audit_time') || 'Time') + '</span>' +
        '<span>' + (t('audit_user') || 'User') + '</span>' +
        '<span>' + (t('audit_action') || 'Action') + '</span>' +
        '<span>' + (t('audit_target') || 'Target') + '</span>' +
        '<span>' + (t('audit_ip') || 'IP') + '</span>' +
        '</div>';
    logs.forEach(function(l) {
        var tag = auditTag(l.action);
        html += '<div class="audit-row">' +
            '<span class="audit-time">' + escHtml(l.created_at || '') + '</span>' +
            '<span>' + auditOperator(l) + '</span>' +
            '<span><span class="tag ' + tag.cls + '">' + escHtml(tag.label) + '</span></span>' +
            '<span class="audit-target" title="' + escHtml(l.target || '') + '">' + escHtml(l.target || '') + '</span>' +
            '<span>' + escHtml(l.ip || '') + '</span>' +
            '</div>';
    });
    list.innerHTML = html;
}

// Prefer nickname for the operator column; fall back to username, and localize
// the special "anonymous" actor (e.g. tokenless downloads).
function auditOperator(l) {
    if (l.username === 'anonymous') return escHtml(t('anonymous') || '匿名');
    return escHtml(l.nickname || l.username || '');
}

function auditTag(action) {
    var a = (action || '').toLowerCase();
    var curLang = (localStorage.getItem('fs_lang') || 'zh');
    var labels = {
        zh: {login:'登录', login_fail:'登录失败', logout:'登出', register:'注册', create_user:'创建用户', update_user:'更新用户', delete_user:'删除用户', password_change:'修改密码', deactivate:'注销', approve:'通过', reject:'拒绝', upload:'上传', upload_multiple:'批量上传', download:'下载', delete:'删除', batch_delete:'批量删除', adb_install:'ADB安装', delete_category:'删除分类', organize:'整理归类', cleanup:'清理', update_site:'更新站点', update_upload_limit:'更新上传限制', update_setting:'更新设置', audit_clear:'审计已清空', password:'改密', create:'创建', update:'更新', batch:'批量', suggest_create:'提交建议', suggest_status:'建议状态', suggest_delete:'删除建议'},
        en: {login:'Login', login_fail:'Login failed', logout:'Logout', register:'Register', create_user:'Create user', update_user:'Update user', delete_user:'Delete user', password_change:'Password change', deactivate:'Deactivate', approve:'Approve', reject:'Reject', upload:'Upload', upload_multiple:'Batch upload', download:'Download', delete:'Delete', batch_delete:'Batch delete', adb_install:'ADB install', delete_category:'Delete category', organize:'Organize', cleanup:'Cleanup', update_site:'Update site', update_upload_limit:'Update upload limit', update_setting:'Update setting', audit_clear:'Audit cleared', password:'Pwd', create:'Create', update:'Update', batch:'Batch', suggest_create:'Submit', suggest_status:'Status', suggest_delete:'Delete'},
        ru: {login:'Вход', login_fail:'Ошибка входа', logout:'Выход', register:'Рег.', create_user:'Созд. польз.', update_user:'Изм. польз.', delete_user:'Удал. польз.', password_change:'Смена пароля', deactivate:'Удал.', approve:'ОК', reject:'Откл.', upload:'Загр.', upload_multiple:'Пакетн. загр.', download:'Выгр.', delete:'Удал.', batch_delete:'Пакетн. удал.', adb_install:'ADB уст.', delete_category:'Удал. катег.', organize:'Организ.', cleanup:'Очистка', update_site:'Обнов. сайта', update_upload_limit:'Лимит загр.', update_setting:'Настройки', audit_clear:'Аудит очищен', password:'Пароль', create:'Созд.', update:'Изм.', batch:'Пакет', suggest_create:'Предлож.', suggest_status:'Статус', suggest_delete:'Удал.'}
    };
    var lbl = (labels[curLang] || labels.zh)[a] || action || '—';
    var cls = 'tag-neutral';
    if (a === 'approve') cls = 'tag-ok';
    else if (a === 'audit_clear') cls = 'tag-danger';
    else if (a === 'reject' || a.indexOf('delete') >= 0) cls = 'tag-danger';
    else if (a.indexOf('password') >= 0 || a === 'register' || a === 'deactivate') cls = 'tag-warn';
    else if (a === 'upload' || a === 'download' || a === 'login' || a === 'logout') cls = 'tag-info';
    return { cls: cls, label: lbl };
}

function exportAuditCSV() {
    if (!_auditCache || !_auditCache.length) { toast(t('no_audit') || 'No records'); return; }
    var headers = ['time', 'user', 'nickname', 'action', 'target', 'ip'];
    var csv = [headers.join(',')].concat(_auditCache.map(function(l) {
        return [l.created_at || '', l.username || '', l.nickname || '', l.action || '', l.target || '', l.ip || '']
            .map(csvCell).join(',');
    })).join('\n');
    var blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'audit_log_' + new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-') + '.csv';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// ---- mount / unmount (SPA) ----
window.Views = window.Views || {};
window.Views.audit = {
    mount: function (root) {
        if (!authToken || authRole === 'anonymous') { location.hash = '#/home'; return; }
        _canViewAll = (authRole === 'admin' || authRole === 'reviewer');
        setupAuditPage();
        loadAuditPublic();
    },
    unmount: function () {}
};
