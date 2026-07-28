// =====================================================================
//  Organization structure view (组织架构)
//  Markup: <template id="tpl-org"> in index.html.
//  Navigation owned by shell.js (#/org).
//  Backend CRUD: /api/org/*  (see modules/org/org.py)
// =====================================================================

var _orgTreeCache = [];   // nested tree (for display)
var _orgDeptsFlat = [];   // flat list (for parent dropdown)
var _orgCurDeptId = null;
var _orgCanManage = false;

// ---------------------------------------------------------------------
// Tree building / sorting (client-side, from the flat /departments list)
// ---------------------------------------------------------------------
function _buildOrgTree(depts) {
    var map = {};
    depts.forEach(function (d) {
        map[d.id] = Object.assign({}, d);
        map[d.id].children = [];
    });
    var roots = [];
    depts.forEach(function (d) {
        if (d.parent_id && map[d.parent_id]) map[d.parent_id].children.push(map[d.id]);
        else roots.push(map[d.id]);
    });
    function sort(nodes) {
        nodes.sort(function (a, b) {
            return (a.sort_order - b.sort_order) || (a.name < b.name ? -1 : (a.name > b.name ? 1 : 0));
        });
        nodes.forEach(function (n) { sort(n.children); });
    }
    sort(roots);
    return roots;
}

// ---------------------------------------------------------------------
// Load department list + render tree
// ---------------------------------------------------------------------
function loadOrgTree() {
    var treeEl = document.getElementById('orgTree');
    fetch('/api/org/departments', { headers: getAuthHeaders(), cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            _orgDeptsFlat = data.departments || [];
            _orgTreeCache = _buildOrgTree(_orgDeptsFlat);
            renderOrgTree();
        })
        .catch(function () {
            if (treeEl) treeEl.innerHTML = '<div class="empty">' + (t('toast_failed') || 'Failed') + '</div>';
        });
}

function renderOrgTree() {
    var treeEl = document.getElementById('orgTree');
    if (!treeEl) return;
    if (!_orgTreeCache.length) {
        treeEl.innerHTML = '<div class="empty">' + (t('org_empty') || '暂无部门') + '</div>';
        return;
    }
    var html = '';
    function walk(list, depth) {
        list.forEach(function (n) {
            var pad = 6 + depth * 16;
            html += '<div class="org-node">';
            html += '<div class="org-node-row' + (n.id === _orgCurDeptId ? ' org-node-active' : '') + '" style="padding-left:' + pad + 'px" onclick="selectDept(' + n.id + ')">';
            html += '<span class="org-node-name">' + escHtml(n.name || '') + '</span>';
            html += '<span class="tag tag-neutral org-count">' + (n.member_count || 0) + '</span>';
            if (_orgCanManage) {
                html += '<span class="org-node-actions">';
                html += '<button class="btn btn-xs" title="' + (t('btn_edit') || 'Edit') + '" onclick="event.stopPropagation();openDeptModal(' + n.id + ')" style="border-color:var(--border)">✎</button> ';
                html += '<button class="btn btn-xs" title="' + (t('org_delete_dept') || 'Delete') + '" onclick="event.stopPropagation();deleteDept(' + n.id + ', \'' + escHtml(n.name || '') + '\')" style="color:var(--danger);border-color:var(--danger)">🗑</button>';
                html += '</span>';
            }
            html += '</div>';
            if (n.children && n.children.length) walk(n.children, depth + 1);
            html += '</div>';
        });
    }
    walk(_orgTreeCache, 0);
    treeEl.innerHTML = html;
}

// ---------------------------------------------------------------------
// Select department -> load its members
// ---------------------------------------------------------------------
function selectDept(id) {
    _orgCurDeptId = id;
    renderOrgTree();
    var dept = _orgDeptsFlat.find(function (d) { return d.id === id; });
    var nameEl = document.getElementById('orgCurDeptName');
    if (nameEl) nameEl.textContent = dept ? (dept.name || '') : '—';
    loadDeptMembers(id, '');
}

function loadDeptMembers(id, search) {
    var list = document.getElementById('orgMembers');
    if (!list) return;
    list.innerHTML = '<div class="center-loading"><div class="spinner"></div></div>';
    var params = new URLSearchParams();
    params.set('department_id', String(id));
    if (search) params.set('search', search);
    fetch('/api/org/members?' + params.toString(), { headers: getAuthHeaders(), cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            renderOrgMembers(data.members || []);
        })
        .catch(function () {
            list.innerHTML = '<div class="empty">' + (t('toast_failed') || 'Failed') + '</div>';
        });
}

function renderOrgMembers(members) {
    var list = document.getElementById('orgMembers');
    if (!list) return;
    if (!members.length) {
        list.innerHTML = '<div class="empty">' + (t('org_no_members') || '该部门暂无成员') + '</div>';
        return;
    }
    var html = '';
    members.forEach(function (m) {
        html += '<div class="file-card" style="padding:12px;margin-bottom:10px;display:flex;justify-content:space-between;gap:10px;align-items:center">';
        html += '<div>';
        html += '<div style="font-weight:600;font-size:14px">' + escHtml(m.nickname || m.username) + '</div>';
        html += '<div style="font-size:12px;color:var(--dim)">' + escHtml(m.username) + (m.role ? ' · ' + escHtml(m.role) : '') + '</div>';
        if (m.title) {
            html += '<div style="margin-top:4px"><span class="tag tag-info">' + escHtml(m.title) + '</span></div>';
        }
        html += '</div>';
        if (_orgCanManage) {
            html += '<div style="display:flex;gap:6px;white-space:nowrap">';
            html += '<button class="btn btn-xs" onclick="openTransferModal(' + m.id + ', \'' + escHtml(m.nickname || m.username) + '\')" style="border-color:var(--border)">' + (t('org_transfer') || '调岗') + '</button>';
            html += '<button class="btn btn-xs" onclick="removeMember(' + m.id + ')" style="color:var(--danger);border-color:var(--danger)">' + (t('org_remove_member') || '移除') + '</button>';
            html += '</div>';
        }
        html += '</div>';
    });
    list.innerHTML = html;
}

// ---------------------------------------------------------------------
// Department modal (create / edit)
// ---------------------------------------------------------------------
function openDeptModal(id) {
    if (!_orgCanManage) return;
    var isEdit = !!id;
    var dept = isEdit ? _orgDeptsFlat.find(function (d) { return d.id === id; }) : null;
    var titleEl = document.getElementById('orgDeptModalTitle');
    if (titleEl) titleEl.textContent = isEdit ? (t('org_edit_dept') || '编辑部门') : (t('org_add_dept') || '新建部门');
    document.getElementById('orgDeptName').value = dept ? (dept.name || '') : '';
    document.getElementById('orgDeptSort').value = dept ? (dept.sort_order || 0) : 0;
    document.getElementById('orgDeptDesc').value = dept ? (dept.description || '') : '';
    // Parent dropdown (exclude self + descendants when editing)
    var sel = document.getElementById('orgDeptParent');
    var parentVal = dept ? (dept.parent_id || 0) : 0;
    sel.innerHTML = '<option value="0" data-i18n="org_root">（顶级部门）</option>';
    function walk(list, depth) {
        list.forEach(function (n) {
            if (isEdit && n.id === id) return; // skip subtree of the edited node
            var indent = '　'.repeat(depth);
            var opt = document.createElement('option');
            opt.value = String(n.id);
            opt.textContent = indent + (n.name || '');
            if (n.id === parentVal) opt.selected = true;
            sel.appendChild(opt);
            walk(n.children, depth + 1);
        });
    }
    walk(_orgTreeCache, 0);
    document.getElementById('orgDeptErr').style.display = 'none';
    document.getElementById('orgDeptModal').dataset.editId = isEdit ? String(id) : '';
    document.getElementById('orgDeptModal').classList.add('show');
}

function closeOrgDeptModal() {
    var m = document.getElementById('orgDeptModal');
    if (m) m.classList.remove('show');
}

function saveDept() {
    if (!_orgCanManage) return;
    var nameEl = document.getElementById('orgDeptName');
    var errEl = document.getElementById('orgDeptErr');
    var name = (nameEl && nameEl.value || '').trim();
    if (!name) {
        errEl.textContent = t('org_name_required') || '请输入部门名称';
        errEl.style.display = 'block';
        return;
    }
    errEl.style.display = 'none';
    var parentRaw = parseInt(document.getElementById('orgDeptParent').value, 10) || 0;
    var body = {
        name: name,
        parent_id: parentRaw,
        sort_order: parseInt(document.getElementById('orgDeptSort').value, 10) || 0,
        description: document.getElementById('orgDeptDesc').value.trim()
    };
    // Determine edit vs create by looking at the title text — simpler: we always
    // POST for new and PUT for edit. We track via a data attribute on the modal.
    var editingId = document.getElementById('orgDeptModal').dataset.editId || '';
    var url, method;
    if (editingId) { url = '/api/org/departments/' + editingId; method = 'PUT'; }
    else { url = '/api/org/departments'; method = 'POST'; }
    fetch(url, {
        method: method,
        headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
        body: JSON.stringify(body)
    }).then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    }).then(function (res) {
        if (!res.ok) { errEl.textContent = res.d.detail || (t('toast_failed')); errEl.style.display = 'block'; return; }
        closeOrgDeptModal();
        toast(t('org_saved') || '已保存');
        loadOrgTree();
    }).catch(function () { toast(t('toast_failed') || 'Failed'); });
}

function deleteDept(id, name) {
    if (!_orgCanManage) return;
    if (!confirm((t('org_confirm_delete_dept') || '确定删除该部门吗？') + (name ? '「' + name + '」' : ''))) return;
    fetch('/api/org/departments/' + id, {
        method: 'DELETE',
        headers: getAuthHeaders()
    }).then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    }).then(function (res) {
        if (!res.ok) { toast(res.d.detail || t('toast_failed')); return; }
        if (_orgCurDeptId === id) {
            _orgCurDeptId = null;
            var nameEl = document.getElementById('orgCurDeptName');
            if (nameEl) nameEl.textContent = '—';
            document.getElementById('orgMembers').innerHTML = '<div class="empty">' + (t('org_pick_dept') || '请选择左侧部门查看成员') + '</div>';
        }
        toast(t('org_deleted') || '已删除');
        loadOrgTree();
    }).catch(function () { toast(t('toast_failed') || 'Failed'); });
}

// ---------------------------------------------------------------------
// Member modal (add)
// ---------------------------------------------------------------------
function openMemberModal() {
    if (!_orgCanManage) return;
    if (!_orgCurDeptId) { toast(t('org_pick_dept_first') || '请先选择部门'); return; }
    var sel = document.getElementById('orgMemberUser');
    sel.innerHTML = '<option value="">' + (t('org_loading_users') || '加载用户…') + '</option>';
    document.getElementById('orgMemberTitle').value = '';
    document.getElementById('orgMemberErr').style.display = 'none';
    fetch('/api/org/users', { headers: getAuthHeaders(), cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            sel.innerHTML = '';
            (data.users || []).forEach(function (u) {
                var opt = document.createElement('option');
                opt.value = String(u.id);
                var label = (u.nickname || u.username) + ' (' + u.username + ')';
                // 一名成员只能属于一个部门：已分配的用户标注所在部门，
                // 但仍可选择——选中后会在保存时自动调岗到当前部门。
                if (u.department_id) {
                    label += ' — ' + (t('org_in_dept') || '已在') + ' ' + (u.department_name || '');
                }
                opt.textContent = label;
                sel.appendChild(opt);
            });
            // Preselect the first assignable user
            var firstFree = Array.prototype.find.call(sel.options, function (o) { return !o.disabled; });
            if (firstFree) sel.value = firstFree.value;
        })
        .catch(function () {
            sel.innerHTML = '<option value="">' + (t('toast_failed') || 'Failed') + '</option>';
        });
    document.getElementById('orgMemberModal').classList.add('show');
}

function closeOrgMemberModal() {
    var m = document.getElementById('orgMemberModal');
    if (m) m.classList.remove('show');
}

function addMember() {
    if (!_orgCanManage) return;
    var sel = document.getElementById('orgMemberUser');
    var errEl = document.getElementById('orgMemberErr');
    var uid = parseInt(sel.value, 10);
    if (!uid) { errEl.textContent = t('org_pick_user') || '请选择用户'; errEl.style.display = 'block'; return; }
    errEl.style.display = 'none';
    var body = {
        department_id: _orgCurDeptId,
        user_id: uid,
        title: document.getElementById('orgMemberTitle').value.trim()
    };
    fetch('/api/org/members', {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
        body: JSON.stringify(body)
    }).then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    }).then(function (res) {
        if (!res.ok) { errEl.textContent = res.d.detail || (t('toast_failed')); errEl.style.display = 'block'; return; }
        closeOrgMemberModal();
        toast(res.d.transferred ? (t('org_member_moved') || '已将该成员调整到此部门') : (t('org_member_added') || '已添加成员'));
        loadDeptMembers(_orgCurDeptId, '');
        loadOrgTree();
    }).catch(function () { toast(t('toast_failed') || 'Failed'); });
}

function removeMember(id) {
    if (!_orgCanManage) return;
    if (!confirm((t('org_confirm_remove_member') || '确定移除该成员吗？'))) return;
    fetch('/api/org/members/' + id, {
        method: 'DELETE',
        headers: getAuthHeaders()
    }).then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    }).then(function (res) {
        if (!res.ok) { toast(res.d.detail || t('toast_failed')); return; }
        toast(t('org_member_removed') || '已移除');
        if (_orgCurDeptId) loadDeptMembers(_orgCurDeptId, '');
        loadOrgTree();
    }).catch(function () { toast(t('toast_failed') || 'Failed'); });
}

// ---------------------------------------------------------------------
// Transfer modal (调岗 — a member belongs to exactly one department)
// ---------------------------------------------------------------------
function openTransferModal(memberId, displayName) {
    if (!_orgCanManage) return;
    var modal = document.getElementById('orgTransferModal');
    modal.dataset.memberId = String(memberId);
    document.getElementById('orgTransferWho').textContent = displayName || '';
    document.getElementById('orgTransferErr').style.display = 'none';
    var sel = document.getElementById('orgTransferDept');
    // 每次都从后端拉最新部门树，确保「刚新建的部门」也出现在目标列表中
    sel.innerHTML = '<option value="">' + (t('org_loading_users') || '加载中…') + '</option>';
    modal.classList.add('show');
    fetch('/api/org/departments', { headers: getAuthHeaders(), cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            var depts = data.departments || [];
            _orgDeptsFlat = depts;
            _orgTreeCache = _buildOrgTree(depts);
            sel.innerHTML = '';
            function walk(list, depth) {
                list.forEach(function (n) {
                    var opt = document.createElement('option');
                    opt.value = String(n.id);
                    opt.textContent = '　'.repeat(depth) + (n.name || '');
                    if (n.id === _orgCurDeptId) opt.disabled = true; // current dept — no-op move
                    sel.appendChild(opt);
                    walk(n.children, depth + 1);
                });
            }
            walk(_orgTreeCache, 0);
            var firstFree = Array.prototype.find.call(sel.options, function (o) { return !o.disabled; });
            if (firstFree) sel.value = firstFree.value;
            else sel.innerHTML = '<option value="">' + (t('org_no_other_dept') || '暂无其他部门可转入') + '</option>';
        })
        .catch(function () {
            sel.innerHTML = '<option value="">' + (t('toast_failed') || 'Failed') + '</option>';
        });
}

function closeOrgTransferModal() {
    var m = document.getElementById('orgTransferModal');
    if (m) m.classList.remove('show');
}

function saveTransfer() {
    if (!_orgCanManage) return;
    var modal = document.getElementById('orgTransferModal');
    var errEl = document.getElementById('orgTransferErr');
    var memberId = parseInt(modal.dataset.memberId, 10);
    var deptId = parseInt(document.getElementById('orgTransferDept').value, 10);
    if (!memberId || !deptId) { errEl.textContent = t('org_pick_dept') || '请选择部门'; errEl.style.display = 'block'; return; }
    errEl.style.display = 'none';
    fetch('/api/org/members/' + memberId, {
        method: 'PUT',
        headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
        body: JSON.stringify({ department_id: deptId })
    }).then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    }).then(function (res) {
        if (!res.ok) { errEl.textContent = res.d.detail || (t('toast_failed')); errEl.style.display = 'block'; return; }
        closeOrgTransferModal();
        toast(t('org_transferred') || '已调岗');
        if (_orgCurDeptId) loadDeptMembers(_orgCurDeptId, '');
        loadOrgTree();
    }).catch(function () { toast(t('toast_failed') || 'Failed'); });
}

// ---------------------------------------------------------------------
// Search (filters members of the selected department)
// ---------------------------------------------------------------------
function orgSearch() {
    var q = (document.getElementById('orgSearch') || {}).value || '';
    if (_orgCurDeptId) loadDeptMembers(_orgCurDeptId, q);
    else loadOrgTree();
}

// ---------------------------------------------------------------------
// mount / unmount (SPA)
// ---------------------------------------------------------------------
window.Views = window.Views || {};
window.Views.org = {
    mount: function () {
        if (!authToken || authRole === 'anonymous') { location.hash = '#/home'; return; }
        _orgCanManage = (authRole === 'admin');
        var addDeptBtn = document.getElementById('orgAddDeptBtn');
        var addMemberBtn = document.getElementById('orgAddMemberBtn');
        if (addDeptBtn) addDeptBtn.style.display = _orgCanManage ? '' : 'none';
        if (addMemberBtn) addMemberBtn.style.display = _orgCanManage ? '' : 'none';
        loadOrgTree();
    },
    unmount: function () {}
};
