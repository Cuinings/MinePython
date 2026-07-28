// =====================================================================
//  Suggestion board view (功能需求建议栏)
//  Markup: <template id="tpl-suggest"> in index.html.
//  Navigation owned by shell.js (#/suggest).
// =====================================================================

var _suggestCache = [];
var _canViewAll = false;   // may view/inspect all rows (admin OR reviewer)
var _canManage = false;    // may change status / delete any row (admin only)
var _suggestCat = 'feature';  // currently selected category in the submit form

// ---------------------------------------------------------------------
// Submit
// ---------------------------------------------------------------------
function submitSuggestion() {
    var titleEl = document.getElementById('suggestTitle');
    var bodyEl = document.getElementById('suggestBody');
    var errEl = document.getElementById('suggestErr');
    var title = (titleEl && titleEl.value || '').trim();
    if (!title) {
        if (errEl) { errEl.textContent = t('suggest_title_required') || '请填写标题'; errEl.style.display = 'block'; }
        return;
    }
    if (errEl) errEl.style.display = 'none';
    var payload = {
        title: title,
        category: _suggestCat,
        body: bodyEl ? bodyEl.value.trim() : ''
    };
    fetch('/api/suggest', {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
        body: JSON.stringify(payload)
    }).then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    }).then(function (res) {
        if (!res.ok) {
            if (errEl) { errEl.textContent = (res.d.detail || t('toast_failed')); errEl.style.display = 'block'; }
            return;
        }
        toast(t('suggest_submitted') || '已提交，感谢你的建议');
        if (titleEl) titleEl.value = '';
        if (bodyEl) bodyEl.value = '';
        setSuggestCat('feature');
        loadSuggestions();
    }).catch(function () {
        toast(t('toast_failed') || 'Failed');
    });
}

// Segmented category selector in the submit form.
function setSuggestCat(val) {
    _suggestCat = val;
    var group = document.getElementById('suggestCategory');
    if (!group) return;
    group.querySelectorAll('.sg-seg-btn').forEach(function (b) {
        b.classList.toggle('active', b.getAttribute('data-val') === val);
    });
}

// ---------------------------------------------------------------------
// List
// ---------------------------------------------------------------------
function loadSuggestions() {
    var list = document.getElementById('suggestList');
    if (!list) return;
    var params = new URLSearchParams();
    params.set('page', '1');
    params.set('page_size', '100');
    var statusEl = document.getElementById('suggestStatus');
    if (statusEl && statusEl.value) params.set('status', statusEl.value);
    var searchEl = document.getElementById('suggestSearch');
    if (searchEl && searchEl.value.trim()) params.set('search', searchEl.value.trim());
    if (_canViewAll) {
        var scopeEl = document.getElementById('suggestScope');
        var v = scopeEl ? scopeEl.value : 'self';
        if (v === 'self') params.set('scope', 'self');
        else if (v === 'all') params.set('scope', 'all');
    }
    fetch('/api/suggest?' + params.toString(), { headers: getAuthHeaders() })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            _suggestCache = data.items || [];
            renderSuggestions(_suggestCache);
        })
        .catch(function () {
            if (list) list.innerHTML = '<div class="empty">' + (t('toast_failed') || 'Failed') + '</div>';
        });
}

// ---------------------------------------------------------------------
// Labels
// ---------------------------------------------------------------------
function suggestStatusLabel(s) {
    var cur = (localStorage.getItem('fs_lang') || 'zh');
    var map = {
        zh: { pending: '待处理', accepted: '已采纳', rejected: '已拒绝', done: '已实现' },
        en: { pending: 'Pending', accepted: 'Accepted', rejected: 'Rejected', done: 'Done' },
        ru: { pending: 'Ожидание', accepted: 'Принято', rejected: 'Отклонено', done: 'Готово' }
    };
    var label = (map[cur] || map.zh)[s] || s || '—';
    var cls = 'tag-neutral';
    if (s === 'pending') cls = 'tag-warn';
    else if (s === 'accepted') cls = 'tag-ok';
    else if (s === 'rejected') cls = 'tag-danger';
    else if (s === 'done') cls = 'tag-info';
    return { label: label, cls: cls };
}

function suggestCatLabel(c) {
    var cur = (localStorage.getItem('fs_lang') || 'zh');
    var map = {
        zh: { feature: '功能新增', ux: '体验优化', bug: 'Bug 反馈', other: '其他' },
        en: { feature: 'New feature', ux: 'UX improvement', bug: 'Bug report', other: 'Other' },
        ru: { feature: 'Новая функция', ux: 'Улучшение UX', bug: 'Ошибка', other: 'Другое' }
    };
    return { label: (map[cur] || map.zh)[c] || c || '—' };
}

// ---------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------
function renderSuggestions(items) {
    var list = document.getElementById('suggestList');
    if (!list) return;
    if (!items || !items.length) {
        list.innerHTML = '<div class="empty">' + (t('suggest_empty') || '暂无建议') + '</div>';
        renderSuggestStats(items || []);
        return;
    }
    var html = '';
    items.forEach(function (s) {
        var st = suggestStatusLabel(s.status);
        var cat = suggestCatLabel(s.category);
        var mine = (s.username === authUser);
        var initial = ((s.nickname || s.username || '?').trim().charAt(0) || '?').toUpperCase();

        html += '<div class="sg-card is-' + s.status + (mine ? ' is-mine' : '') + '">';

        // header: title + status badge
        html += '<div class="sg-card-head">';
        html += '<div class="sg-title-wrap">';
        html += '<span class="sg-cat-badge">' + escHtml(cat.label) + '</span>';
        html += '<div class="sg-title">' + escHtml(s.title || '') + '</div>';
        html += '</div>';
        html += '<span class="tag ' + st.cls + '">' + escHtml(st.label) + '</span>';
        html += '</div>';

        // meta: author avatar + name + time
        html += '<div class="sg-meta">';
        html += '<span class="sg-avatar">' + escHtml(initial) + '</span>';
        html += '<span>' + escHtml(s.nickname || s.username) + '</span>';
        html += '<span>·</span><span>' + escHtml(s.created_at || '') + '</span>';
        html += '</div>';

        if (s.body) {
            html += '<div class="sg-body">' + escHtml(s.body) + '</div>';
        }
        if (s.admin_note) {
            html += '<div class="sg-note">' + escHtml(t('suggest_admin_note') || '管理员备注') +
                '：' + escHtml(s.admin_note) + '</div>';
        }

        // actions: status buttons (admin only) + delete (owner or admin)
        html += '<div class="sg-actions">';
        if (_canManage) {
            html += '<div class="sg-status-btns">';
            ['pending', 'accepted', 'rejected', 'done'].forEach(function (v) {
                var active = (s.status === v) ? ' active' : '';
                html += '<button class="sg-status-btn sg-' + v + active +
                    '" onclick="setSuggestionStatus(' + s.id + ',\'' + v + '\')">' +
                    escHtml(suggestStatusLabel(v).label) + '</button>';
            });
            html += '</div>';
        }
        if (mine || _canManage) {
            html += '<button class="sg-del" onclick="deleteSuggestion(' + s.id + ')">' +
                escHtml(t('suggest_delete') || '删除') + '</button>';
        }
        html += '</div>';

        html += '</div>';
    });
    list.innerHTML = html;
    renderSuggestStats(items);
}

// ---------------------------------------------------------------------
// Summary stat strip (counts per status, based on the current list)
// ---------------------------------------------------------------------
function renderSuggestStats(items) {
    var el = document.getElementById('suggestStats');
    if (!el) return;
    var counts = { pending: 0, accepted: 0, rejected: 0, done: 0 };
    (items || []).forEach(function (s) {
        if (counts.hasOwnProperty(s.status)) counts[s.status]++;
    });
    var defs = ['pending', 'accepted', 'rejected', 'done'];
    var html = '';
    defs.forEach(function (k) {
        var m = suggestStatusLabel(k);
        html += '<div class="sg-stat ' + k + '">' +
            '<span class="dot"></span>' +
            '<span class="num">' + counts[k] + '</span>' +
            '<span>' + escHtml(m.label) + '</span></div>';
    });
    el.innerHTML = html;
}

// ---------------------------------------------------------------------
// Admin status update / delete
// ---------------------------------------------------------------------
function setSuggestionStatus(id, status) {
    // Skip a redundant PATCH when the button already reflects the current state.
    for (var i = 0; i < _suggestCache.length; i++) {
        if (_suggestCache[i].id === id && _suggestCache[i].status === status) return;
    }
    fetch('/api/suggest/' + id, {
        method: 'PATCH',
        headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
        body: JSON.stringify({ status: status })
    }).then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    }).then(function (res) {
        if (!res.ok) { toast(res.d.detail || t('toast_failed')); return; }
        toast(t('suggest_updated') || '状态已更新');
        loadSuggestions();
    }).catch(function () { toast(t('toast_failed') || 'Failed'); });
}

function deleteSuggestion(id) {
    if (!confirm((t('suggest_delete_confirm') || '确定删除这条建议吗？'))) return;
    fetch('/api/suggest/' + id, {
        method: 'DELETE',
        headers: getAuthHeaders()
    }).then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    }).then(function (res) {
        if (!res.ok) { toast(res.d.detail || t('toast_failed')); return; }
        toast(t('suggest_deleted') || '已删除');
        loadSuggestions();
    }).catch(function () { toast(t('toast_failed') || 'Failed'); });
}

// ---------------------------------------------------------------------
// mount / unmount (SPA)
// ---------------------------------------------------------------------
window.Views = window.Views || {};
window.Views.suggest = {
    mount: function (root) {
        if (!authToken || authRole === 'anonymous') { location.hash = '#/home'; return; }
        _canViewAll = (authRole === 'admin' || authRole === 'reviewer');
        _canManage = (authRole === 'admin');
        var scopeBar = document.getElementById('suggestScope');
        if (scopeBar) {
            scopeBar.style.display = _canViewAll ? '' : 'none';
            // Viewers with cross-user access should see everyone's suggestions by default.
            if (_canViewAll) scopeBar.value = 'all';
        }
        loadSuggestions();
    },
    unmount: function () {}
};
