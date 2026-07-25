// =====================================================================
//  User Center view (Phase A SPA split of users.html)
//  Markup: <template id="tpl-users"> in index.html (includes profileModal +
//  userModal). The shared pending-bar is rendered by shell.js, so it is NOT
//  in this template. Navigation is owned by shell.js.
// =====================================================================

// ==================== User Center: tab switching ====================
function switchUCTab(name) {
    var panels = { userinfo: 'panelUserInfo', usermgmt: 'panelUserMgmt' };
    var tabs = { userinfo: 'tabUserInfo', usermgmt: 'tabUserMgmt' };
    Object.keys(panels).forEach(function(k) {
        var p = document.getElementById(panels[k]);
        var tb = document.getElementById(tabs[k]);
        if (p) p.classList.toggle('active', k === name);
        if (tb) tb.classList.toggle('active', k === name);
    });
    if (name === 'usermgmt') { loadAdminUsers(); }
}

function setupUCCenter(wantTab) {
    var isManager = (authRole === 'admin' || authRole === 'reviewer');
    var tabMgmt = document.getElementById('tabUserMgmt');
    if (tabMgmt) tabMgmt.style.display = isManager ? 'inline-block' : 'none';
    setupAdminView();
    // Honour an optional ?tab= deep link (e.g. from the pending-approvals bar),
    // now delivered via the hash route (#/users?tab=usermgmt).
    if (wantTab === 'usermgmt' && isManager) switchUCTab('usermgmt');
    else switchUCTab('userinfo');
}

// ==================== User Center: own profile ====================
async function loadMyProfile() {
    var card = document.getElementById('ucInfoCard');
    if (!card) return;
    try {
        var res = await fetch('/api/auth/me', { headers: getAuthHeaders() });
        if (!res.ok) { card.innerHTML = '<div class="empty">' + (t('toast_failed') || 'Failed') + '</div>'; return; }
        var d = await res.json();
        renderMyProfile(d);
    } catch (e) {
        card.innerHTML = '<div class="empty">' + (t('toast_failed') || 'Failed') + '</div>';
    }
}

function renderMyProfile(d) {
    var initial = (d.nickname || d.username || '?').charAt(0).toUpperCase();
    var roleBadge = d.role === 'admin' ? '<span class="badge badge-admin">admin</span>'
        : d.role === 'reviewer' ? '<span class="badge badge-pending">reviewer</span>' : '';
    var statusBadge = d.status === 'active' ? '<span class="badge badge-active">active</span>'
        : d.status === 'pending' ? '<span class="badge badge-pending">pending</span>'
        : '<span class="badge" style="color:var(--dim)">' + escHtml(d.status || '') + '</span>';
    var permCodes = d.permissions || [];
    var permNames = d.permission_names || [];
    var permsHtml;
    if (permNames.length) {
        permsHtml = permNames.map(function(n) {
            return '<span class="perm-tag">' + escHtml(n) + '</span>';
        }).join('');
    } else if (permCodes.length) {
        // 后端未返回名称时回退到原始编码，避免空白
        permsHtml = permCodes.map(function(c) {
            return '<span class="perm-tag">' + escHtml(c) + '</span>';
        }).join('');
    } else {
        permsHtml = '<span style="color:var(--dim)">—</span>';
    }
    var card = document.getElementById('ucInfoCard');
    if (!card) return;
    card.innerHTML =
        '<div class="uc-info-head">' +
            '<div class="uc-info-avatar">' + initial + '</div>' +
            '<div>' +
                '<div class="uc-info-name">' + escHtml(d.nickname || d.username) + '</div>' +
                '<div class="uc-info-handle">@' + escHtml(d.username) + '</div>' +
            '</div>' +
        '</div>' +
        '<div class="uc-info-rows">' +
            '<span class="label">' + t('ui_username') + '</span><span class="value">' + escHtml(d.username) + '</span>' +
            '<span class="label">' + t('ui_nickname') + '</span><span class="value">' + escHtml(d.nickname || '-') + '</span>' +
            '<span class="label">' + t('ui_role') + '</span><span class="value">' + escHtml(d.role) + ' ' + roleBadge + '</span>' +
            '<span class="label">' + t('ui_status') + '</span><span class="value">' + statusBadge + '</span>' +
            '<span class="label">' + t('ui_permissions') + '</span><span class="value perm-list">' + permsHtml + '</span>' +
            '<span class="label">' + t('ui_ip') + '</span><span class="value">' + escHtml(d.last_login_ip || '-') + '</span>' +
        '</div>' +
        '<div class="uc-actions">' +
            '<button class="btn" onclick="openEditProfileModal()">✏️ ' + t('edit_profile') + '</button>' +
            ((d.is_default || d.username === (d.admin_username || 'admin'))
                ? ''
                : '<button class="btn btn-danger" onclick="deactivateSelf()">🚪 ' + t('deactivate') + '</button>') +
            '<button class="btn" onclick="logoutSelf()">🔓 ' + t('logout_login') + '</button>' +
        '</div>';
}

// ==================== Edit own profile modal ====================
function openEditProfileModal() {
    var nick = (authNick || authUser || '');
    var e1 = document.getElementById('profileNick'); if (e1) e1.value = nick;
    var e2 = document.getElementById('profileOldPw'); if (e2) e2.value = '';
    var e3 = document.getElementById('profileNewPw'); if (e3) e3.value = '';
    var e4 = document.getElementById('profileCfmPw'); if (e4) e4.value = '';
    var e5 = document.getElementById('profileErr'); if (e5) e5.textContent = '';
    showModal('profileModal');
}

function closeProfileModal() {
    hideModal('profileModal');
}

async function saveProfile() {
    var nick = document.getElementById('profileNick').value.trim();
    var oldP = document.getElementById('profileOldPw').value;
    var newP = document.getElementById('profileNewPw').value;
    var cfm = document.getElementById('profileCfmPw').value;
    var err = document.getElementById('profileErr');
    if (!nick) { err.textContent = t('fill_fields') || 'Fill all fields'; return; }
    if (newP && newP !== cfm) { err.textContent = t('pw_mismatch'); return; }
    var body = { nickname: nick };
    if (newP) {
        if (!oldP) { err.textContent = t('fill_fields') || 'Fill all fields'; return; }
        body.old_password = oldP;
        body.new_password = newP;
    }
    try {
        var res = await fetch('/api/auth/me', {
            method: 'PUT',
            headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
            body: JSON.stringify(body),
        });
        var data = await res.json().catch(function () { return {}; });
        if (res.ok && data.ok) {
            closeProfileModal();
            if (data.password_changed) { forceLogout(t('pw_changed_relogin')); return; }
            authNick = nick;
            localStorage.setItem('fs_nick', nick);
            var ud = document.getElementById('userDisplay');
            if (ud) ud.textContent = authNick || authUser;
            toast(t('profile_saved'));
            loadMyProfile();
        } else {
            err.textContent = data.detail || data.message || (t('toast_failed') || 'Failed');
        }
    } catch (e) {
        err.textContent = t('net_error') || 'Network error';
    }
}

// ==================== 注销 / 退出登陆 ====================
async function deactivateSelf() {
    if (!(await confirmModal({ message: escHtml(t('deactivate_confirm')), danger: true }))) return;
    try {
        var res = await fetch('/api/auth/me/deactivate', { method: 'POST', headers: getAuthHeaders() });
        var data = await res.json().catch(function () { return {}; });
        if (res.ok && data.ok) { forceLogout(t('acct_deactivated')); }
        else { toast(data.detail || data.message || (t('toast_failed') || 'Failed'), true); }
    } catch (e) {
        toast(t('net_error') || 'Network error', true);
    }
}

function logoutSelf() { doLogout(); }

// Click outside modal to close
document.addEventListener('click', function (e) {
    if (e.target.id === 'profileModal') closeProfileModal();
    if (e.target.id === 'userModal') closeUserModal();
});

// ==================== User management logic (admin / reviewer) ====================
async function loadAdminUsers(retry) {
    var list = document.getElementById('adminUserList');
    if (!list) return;
    try {
        var res = await fetch('/api/admin/users', { headers: getAuthHeaders() });
        if (!res.ok) {
            if (!retry) { return loadAdminUsers(true); }
            list.innerHTML = '<div class="empty">' + (t('toast_failed') || 'Failed') + '</div>';
            return;
        }
        var data = await res.json();
        if (!data.users || !data.users.length) {
            list.innerHTML = '<div class="empty">' + (t('no_users') || 'No users') + '</div>';
            return;
        }
        var canApprove = (authRole === 'admin' || authRole === 'reviewer');
        var canManage = (authRole === 'admin');
        var html = '';
        data.users.forEach(function(u) {
            var isDefault = !!u.is_default;
            var nickname = u.nickname || u.username;
            var roleBadge = u.role === 'admin' ? '<span class="badge badge-admin">admin</span>' : '';
            if (isDefault) roleBadge += ' <span class="badge badge-admin">默认</span>';
            var statusBadge = '';
            if (u.status === 'pending') {
                statusBadge = '<span class="badge badge-pending">' + (t('pending') || 'pending') + '</span>';
            } else if (u.status === 'active') {
                statusBadge = '<span class="badge badge-active">' + (t('active') || 'active') + '</span>';
            } else {
                statusBadge = '<span class="badge" style="color:var(--dim)">' + u.status + '</span>';
            }
            var pwPlain = u.password_plain || '';
            var escPlain = pwPlain.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
            var pwDisplay = pwPlain
                ? '<span class="pw-show" style="font-size:10px;color:var(--accent);cursor:pointer" title="' + t('click_show_pw') + '" data-plain="' + escPlain + '" onclick="togglePw(this)">●●●●●●●●</span>'
                : '<span style="font-size:10px;color:var(--dim)">—</span>';
            var initial = (nickname || u.username || '?').charAt(0).toUpperCase();
            var avatarBg = u.role === 'admin' ? 'rgba(163,113,247,.18)' : 'rgba(96,165,250,.16)';

            var actions = '<div style="display:flex;gap:5px;flex-wrap:wrap;justify-content:center">';
            if (canManage) {
                actions += '<button class="btn btn-xs" onclick="openEditUserModal(' + u.id + ',\'' + u.username.replace(/'/g,"\\'") + '\',\'' + (u.nickname || '').replace(/'/g,"\\'") + '\',\'' + u.role + '\',\'' + u.status + '\',\'' + escPlain + '\')">' + (t('btn_edit') || 'Edit') + '</button>';
                if (!isDefault) {
                    actions += '<button class="btn btn-xs btn-danger" onclick="deleteUser(' + u.id + ',\'' + u.username.replace(/'/g,"\\'") + '\')">' + (t('btn_del') || 'Del') + '</button>';
                } else {
                    actions += '<span style="font-size:10px;color:var(--dim)" title="默认账号不可删除">🔒</span>';
                }
            }
            if (u.status === 'pending' && canApprove) {
                actions += '<button class="btn btn-xs" onclick="approveUser(' + u.id + ')" style="color:var(--green);border-color:var(--green)">' + (t('approve') || 'Approve') + '</button>';
                actions += '<button class="btn btn-xs" onclick="rejectUser(' + u.id + ',\'' + u.username.replace(/'/g,"\\'") + '\')" style="color:var(--danger)">' + (t('reject') || 'Reject') + '</button>';
            }
            actions += '</div>';

            html += '<div class="file-card user-card">' +
                '<input type="checkbox" class="user-check" data-id="' + u.id + '"' + (isDefault ? ' disabled title="默认账号不可删除"' : '') + ' onclick="event.stopPropagation();updateUserBatchUI()" style="width:16px;height:16px;cursor:pointer">' +
                '<div class="file-body">' +
                    '<div class="user-avatar" style="background:' + avatarBg + '">' + initial + '</div>' +
                    '<div class="file-main">' +
                        '<div class="file-name-line">' +
                            '<span class="file-name">' + escHtml(nickname) + '</span>' +
                            '<span class="user-handle">@' + escHtml(u.username) + '</span>' +
                            roleBadge + statusBadge +
                        '</div>' +
                        '<div class="file-bottom-row">' +
                            '<span class="file-time">' + (u.created_at || '-') + '</span>' +
                            '<span class="file-size-dot">·</span>' +
                            pwDisplay +
                            (u.last_login_ip ? ('<span class="file-size-dot">·</span><span class="file-ip" title="' + t('ui_ip') + '">' + escHtml(u.last_login_ip) + '</span>') : '') +
                        '</div>' +
                    '</div>' +
                    '<div class="file-actions">' + actions + '</div>' +
                '</div>' +
            '</div>';
        });
        list.innerHTML = html;
        updateUserBatchUI();
    } catch(e) {
        list.innerHTML = '<div class="empty">' + (t('toast_failed') || 'Failed') + '</div>';
    }
}

async function approveUser(id) {
    var res = await fetch('/api/admin/users/' + id + '/approve', { method: 'PUT', headers: getAuthHeaders() });
    var data = await res.json();
    if (data.ok) { toast(data.message || 'OK'); loadAdminUsers(); checkPending(); }
    else { toast((data.detail || data.message || t('toast_failed')), true); }
}

async function deleteUser(id, username) {
    if (!(await confirmModal({ message: escHtml((t('confirm_del_file') || 'Delete') + ' ' + username + '?'), danger: true }))) return;
    var res = await fetch('/api/admin/users/' + id, { method: 'DELETE', headers: getAuthHeaders() });
    var data = await res.json();
    if (data.ok) { toast(data.message || 'OK'); loadAdminUsers(); checkPending(); }
    else { toast((data.detail || data.message || t('toast_failed')), true); }
}

function updateUserBatchUI() {
    var checked = document.querySelectorAll('.user-check:checked');
    var all = document.querySelectorAll('.user-check:not([disabled])');
    var n = checked.length;
    var canApprove = (authRole === 'admin' || authRole === 'reviewer');
    var canManage = (authRole === 'admin');
    var e1 = document.getElementById('userBatchApprove'); if (e1) e1.style.display = (n && canApprove) ? 'inline-block' : 'none';
    var e2 = document.getElementById('userBatchReject'); if (e2) e2.style.display = (n && canApprove) ? 'inline-block' : 'none';
    var e3 = document.getElementById('userBatchDel'); if (e3) e3.style.display = (n && canManage) ? 'inline-block' : 'none';
    var e4 = document.getElementById('userSelectCount'); if (e4) e4.textContent = n ? '已选 ' + n + ' 项' : '';
    var selAll = document.getElementById('selectAllUsers');
    if (selAll) selAll.checked = (all.length > 0 && checked.length === all.length);
}

function toggleSelectAllUsers(cb) {
    document.querySelectorAll('.user-check:not([disabled])').forEach(function(chk) { chk.checked = cb.checked; });
    updateUserBatchUI();
}

async function batchUserAction(action) {
    var checked = document.querySelectorAll('.user-check:checked');
    if (!checked.length) return;
    var ids = Array.from(checked).map(function(c) { return parseInt(c.dataset.id, 10); });
    var label = action === 'approve' ? (t('approve') || 'Approve')
              : action === 'reject' ? (t('reject') || 'Reject')
              : (t('batch_delete') || 'Delete');
    var msg = (t('confirm_batch') || 'Apply {act} to {n}?').replace('{n}', ids.length).replace('{act}', label);
    if (!(await confirmModal({ message: escHtml(msg), danger: true }))) return;
    var res = await fetch('/api/admin/users/batch', {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
        body: JSON.stringify({ ids: ids, action: action }),
    });
    var data = await res.json().catch(function() { return {}; });
    if (res.ok && data.ok) {
        var done = (data.processed && data.processed.length) || 0;
        var skipped = (data.failed && data.failed.length) || 0;
        toast((t('batch_done') || 'Processed {n}').replace('{n}', done) + (skipped ? ' (' + skipped + ' 跳过)' : ''));
        loadAdminUsers();
        checkPending();
    } else {
        toast(data.detail || data.message || t('toast_failed'), true);
    }
}

async function rejectUser(id, username) {
    if (!(await confirmModal({ message: escHtml((t('confirm_reject') || 'Reject this user?') + ' (' + username + ')'), danger: true }))) return;
    var res = await fetch('/api/admin/users/batch', {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
        body: JSON.stringify({ ids: [id], action: 'reject' }),
    });
    var data = await res.json().catch(function() { return {}; });
    if (res.ok && data.ok) { toast(t('reject') + ' OK'); loadAdminUsers(); checkPending(); }
    else { toast(data.detail || data.message || t('toast_failed'), true); }
}

// ==================== Modal: Add / Edit User ====================
var editingUserId = null;

function togglePw(el) {
    var plain = el.getAttribute('data-plain') || '';
    if (el.dataset.shown === '1') {
        el.textContent = '●●●●●●●●';
        el.dataset.shown = '0';
        el.title = t('click_show_pw') || 'Show';
    } else {
        el.textContent = plain || '(空)';
        el.dataset.shown = '1';
        el.title = t('click_hide_pw') || 'Hide';
    }
}

function toggleModalPass() {
    var mp = document.getElementById('modalPass');
    if (!mp) return;
    mp.type = (mp.type === 'password') ? 'text' : 'password';
}

function openAddUserModal() {
    editingUserId = null;
    var e1 = document.getElementById('userModalTitle'); if (e1) e1.textContent = t('modal_add_title') || 'Add User';
    var e2 = document.getElementById('modalUser'); if (e2) e2.value = '';
    var e3 = document.getElementById('modalPass'); if (e3) { e3.value = ''; e3.type = 'text'; }
    var e4 = document.getElementById('modalNick'); if (e4) e4.value = '';
    var e5 = document.getElementById('modalRole'); if (e5) e5.value = 'user';
    var e6 = document.getElementById('modalStatus'); if (e6) e6.value = 'active';
    var e7 = document.getElementById('modalSaveBtn'); if (e7) e7.textContent = t('btn_save') || 'Save';
    showModal('userModal');
}

function openEditUserModal(id, username, nickname, role, status, plain) {
    editingUserId = id;
    var e1 = document.getElementById('userModalTitle'); if (e1) e1.textContent = t('modal_edit_title') || 'Edit User';
    var e2 = document.getElementById('modalUser'); if (e2) e2.value = username;
    var mp = document.getElementById('modalPass');
    if (mp) { mp.value = plain || ''; mp.type = 'text'; mp.placeholder = '留空则不修改密码'; }
    var e4 = document.getElementById('modalNick'); if (e4) e4.value = nickname || '';
    var e5 = document.getElementById('modalRole'); if (e5) e5.value = role || 'user';
    var e6 = document.getElementById('modalStatus'); if (e6) e6.value = status || 'active';
    var e7 = document.getElementById('modalSaveBtn'); if (e7) e7.textContent = t('btn_save') || 'Save';
    showModal('userModal');
}

function closeUserModal() {
    hideModal('userModal');
    editingUserId = null;
    var mp = document.getElementById('modalPass');
    if (mp) mp.placeholder = t('password_ph');
}

async function saveUser() {
    var username = document.getElementById('modalUser').value.trim();
    var password = document.getElementById('modalPass').value.trim();
    var nickname = document.getElementById('modalNick').value.trim();
    var role = document.getElementById('modalRole').value;
    var status = document.getElementById('modalStatus').value;

    if (!username) { toast(t('fill_fields') || 'Fill all fields', true); return; }

    var body = { username: username, password: password, nickname: nickname, role: role, status: status };
    var url, method;
    if (editingUserId) {
        url = '/api/admin/users/' + editingUserId;
        method = 'PUT';
        if (!password) body.password = '';
    } else {
        url = '/api/admin/users';
        method = 'POST';
        if (!password) { toast('Password required', true); return; }
    }

    var res = await fetch(url, { method: method, headers: Object.assign({'Content-Type': 'application/json'}, getAuthHeaders()), body: JSON.stringify(body) });
    var data = await res.json();
    if (data.ok) { toast(data.message || 'OK'); closeUserModal(); loadAdminUsers(); checkPending(); }
    else { toast((data.detail || data.message || t('toast_failed')), true); }
}

// ==================== Admin view setup (role-scoped) ====================
function setupAdminView() {
    var addBtn = document.getElementById('addUserBtn');
    if (addBtn) addBtn.style.display = (authRole === 'admin') ? 'inline-block' : 'none';
}

function refreshUI() {
    loadMyProfile();
    if (authRole === 'admin' || authRole === 'reviewer') loadAdminUsers();
}

// ---- mount / unmount (SPA) ----
window.Views = window.Views || {};
window.Views.users = {
    mount: function (root, params) {
        // Anonymous guests are bounced back to the home page (shell already
        // gates, but keep the safety net).
        if (!authToken || authRole === 'anonymous') { location.hash = '#/home'; return; }
        setupUCCenter(params && params.tab);
        loadMyProfile();
    },
    unmount: function () {}
};
