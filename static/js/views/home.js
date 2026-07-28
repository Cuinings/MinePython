// =====================================================================
//  Home view (dashboard). Markup lives in <template id="tpl-home"> in
//  index.html; this file fetches real data and renders the dashboard:
//  greeting + role + storage, role-aware stat cards, permission-gated
//  module groups, and a recent-files strip. Falls back to skeleton / empty
//  states while loading and on error.
// =====================================================================
(function () {
    window.Views = window.Views || {};

    // ---- module-level state (so language switch can re-render) ----
    var _root = null;
    var _lastStats = null;
    var _lastPerms = [];
    var _lastRole = '';
    var _lastIp = '';
    var _lastNick = '';

    var ROLE_LABEL = { admin: '管理员', reviewer: '审核员', user: '成员', anonymous: '匿名' };
    var CAT_EMOJI = {
        '图片': '🖼', '文档': '📄', '视频': '🎬', '音频': '🎵',
        '压缩包': '🗜️', '代码': '💻', '安装包': '📦', '其他': '📁'
    };

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function tp(key, vars) {
        return (t(key) || key).replace(/\{(\w+)\}/g, function (_, m) {
            return vars && vars[m] != null ? vars[m] : m;
        });
    }
    function catEmoji(c) { return CAT_EMOJI[c] || '📁'; }

    function fmtSize(bytes) {
        bytes = Number(bytes) || 0;
        if (bytes < 1024) return bytes + ' B';
        var u = ['KB', 'MB', 'GB', 'TB'];
        var i = -1, v = bytes;
        do { i++; v /= 1024; } while (v >= 1024 && i < u.length - 1);
        return (v < 10 ? v.toFixed(1) : Math.round(v)) + ' ' + u[i];
    }

    function timeAgo(iso) {
        if (!iso) return '';
        var then = new Date(iso.indexOf('T') < 0 ? iso.replace(' ', 'T') : iso).getTime();
        if (isNaN(then)) return '';
        var diff = (Date.now() - then) / 1000;
        if (diff < 60) return t('home_just_now') || '刚刚';
        if (diff < 3600) return Math.floor(diff / 60) + (t('home_min_ago') || '分钟前');
        if (diff < 86400) return Math.floor(diff / 3600) + (t('home_hr_ago') || '小时前');
        if (diff < 86400 * 7) return Math.floor(diff / 86400) + (t('home_day_ago') || '天前');
        var d = new Date(then);
        return (d.getMonth() + 1) + '-' + d.getDate();
    }

    function greetKey() {
        var h = new Date().getHours();
        if (h < 6) return 'home_greet_night';
        if (h < 12) return 'home_greet_morning';
        if (h < 14) return 'home_greet_noon';
        if (h < 18) return 'home_greet_afternoon';
        return 'home_greet_evening';
    }

    // ---- Hero (greeting / avatar / role / last IP) ----
    function setHero(nick, role, ip) {
        var greetEl = document.getElementById('hdGreet');
        var avatarEl = document.getElementById('hdAvatar');
        var roleEl = document.getElementById('hdRole');
        var ipEl = document.getElementById('hdLastIp');
        var name = nick || role || '';
        if (greetEl) {
            greetEl.innerHTML = esc(t(greetKey())) + '，<span class="name">' + esc(name) + '</span> 👋';
        }
        if (avatarEl) avatarEl.textContent = (name || '?').charAt(0).toUpperCase();
        if (roleEl) {
            var label = ROLE_LABEL[role] || role;
            roleEl.textContent = label ? (label + ' · ' + role) : role;
        }
        if (ipEl) ipEl.textContent = ip ? (t('home_last_login') + ' ' + ip) : '';
    }

    // ---- Permission gating (module cards + admin group) ----
    function applyGating(perms, role) {
        if (!_root) return;
        perms = perms || [];
        var mods = _root.querySelectorAll('.hd-mod[data-perm], .hd-mod[data-role]');
        mods.forEach(function (m) {
            var p = m.getAttribute('data-perm');
            var r = m.getAttribute('data-role');
            var show = true;
            if (p) show = perms.indexOf(p) >= 0;
            if (r) show = (role === r);
            m.style.display = show ? '' : 'none';
        });
        var anyAdmin = false;
        _root.querySelectorAll('#hdGroupAdmin .hd-mod').forEach(function (m) {
            if (m.style.display !== 'none') anyAdmin = true;
        });
        _root.querySelectorAll('.hd-group-admin').forEach(function (el) {
            el.style.display = anyAdmin ? '' : 'none';
        });
    }

    // ---- Stat cards ----
    function renderStats(d, role) {
        var el = document.getElementById('hdStats');
        if (!el) return;
        var isApprover = (role === 'admin' || role === 'reviewer');
        var cards = [
            { label: t('home_stat_total'), num: d.total_files, sub: '' },
            { label: t('home_stat_mine'), num: d.my_files, sub: '' },
            {
                label: t('home_stat_storage'),
                num: fmtSize(d.my_size),
                sub: d.quota_mb > 0
                    ? (Math.round(d.my_size / (d.quota_mb * 1024 * 1024) * 100) + '%')
                    : t('home_quota_off')
            }
        ];
        if (isApprover) {
            cards.push({
                label: t('home_stat_pending'),
                num: d.pending_users,
                danger: d.pending_users > 0,
                sub: d.pending_users > 0 ? tp('home_pending_sub', { n: d.pending_users }) : '—'
            });
        } else {
            cards.push({ label: t('home_stat_myperms'), num: '—', sub: '上传 / 下载 / 预览' });
        }
        el.innerHTML = cards.map(function (c) {
            return '<div class="hd-stat">' +
                '<div class="hd-stat-label">' + esc(c.label) + '</div>' +
                '<div class="hd-stat-num' + (c.danger ? ' danger' : '') + '">' + esc(c.num) + '</div>' +
                '<div class="hd-stat-sub">' + esc(c.sub || '') + '</div>' +
                '</div>';
        }).join('');
    }

    // ---- Storage bar (in hero) ----
    function renderStorage(d) {
        var el = document.getElementById('hdStorage');
        if (!el) return;
        if (d.quota_mb > 0) {
            var total = d.quota_mb * 1024 * 1024;
            var pct = Math.min(100, Math.round(d.my_size / total * 100));
            el.innerHTML =
                '<div class="hd-storage-top"><span>' + esc(t('home_storage')) + '</span>' +
                '<span><b>' + esc(fmtSize(d.my_size)) + '</b> / ' + esc(fmtSize(total)) + '（' + pct + '%）</span></div>' +
                '<div class="hd-storage-track"><div class="hd-storage-fill" style="width:' + pct + '%"></div></div>';
        } else {
            el.innerHTML =
                '<div class="hd-storage-top"><span>' + esc(t('home_storage')) + '</span>' +
                '<span><b>' + esc(fmtSize(d.my_size)) + '</b> · ' + esc(t('home_quota_off')) + '</span></div>';
        }
    }

    // ---- Recent files ----
    function renderRecent(list) {
        var el = document.getElementById('hdRecent');
        if (!el) return;
        if (!list || !list.length) {
            el.innerHTML = '<div class="hd-rec-empty">' + esc(t('home_no_recent')) + '</div>';
            return;
        }
        el.innerHTML = list.map(function (f) {
            var emoji = catEmoji(f.category);
            return '<div class="hd-rec">' +
                '<div class="hd-rec-icon">' + emoji + '</div>' +
                '<div class="hd-rec-main" onclick="goFiles()">' +
                    '<div class="hd-rec-name">' + esc(f.filename) + '</div>' +
                    '<div class="hd-rec-meta">' +
                        '<span>' + emoji + ' ' + esc(f.category || '') + '</span>' +
                        '<span>' + esc(f.uploader_nickname || '') + '</span>' +
                        '<span>' + esc(timeAgo(f.uploaded_at)) + '</span>' +
                        '<span>' + esc(f.size_human || '') + '</span>' +
                    '</div>' +
                '</div>' +
                '<div class="hd-rec-actions">' +
                    '<a class="icon-btn" title="' + esc(t('btn_preview')) + '" href="/api/preview/' +
                        encodeURIComponent(f.path) + getTokenParam() + '" target="_blank" rel="noopener">👁</a>' +
                    '<a class="icon-btn" title="' + esc(t('btn_dl')) + '" href="' +
                        downloadUrl(f.path) + '" target="_blank" rel="noopener">⬇</a>' +
                '</div>' +
            '</div>';
        }).join('');
    }

    // ---- Load dashboard data ----
    async function loadStats() {
        try {
            var res = await fetch('/api/stats/home');
            if (!res.ok) throw new Error('stats ' + res.status);
            var d = await res.json();
            _lastStats = d;
            renderStats(d, _lastRole);
            renderStorage(d);
            renderRecent(d.recent || []);
        } catch (e) {
            var sEl = document.getElementById('hdStats');
            if (sEl) sEl.innerHTML = '<div class="hd-rec-empty">' + esc(t('net_error') || '加载失败') + '</div>';
            var rEl = document.getElementById('hdRecent');
            if (rEl) rEl.innerHTML = '<div class="hd-rec-empty">' + esc(t('net_error') || '加载失败') + '</div>';
        }
    }

    function goSearchFiles() {
        window.location.hash = '#/files';
        setTimeout(function () {
            var i = document.getElementById('searchInput');
            if (i) i.focus();
        }, 400);
    }

    // Language-switch re-render hook (overrides the global no-op).
    function refreshHome() {
        setHero(_lastNick || authNick || authUser, _lastRole || authRole, _lastIp);
        applyGating(_lastPerms.length ? _lastPerms : authPerms, _lastRole || authRole);
        if (_lastStats) {
            renderStats(_lastStats, _lastRole || authRole);
            renderStorage(_lastStats);
            renderRecent(_lastStats.recent || []);
        }
    }

    window.Views.home = {
        mount: function (root) {
            _root = root;
            _lastRole = authRole || 'anonymous';
            _lastPerms = authPerms || [];
            _lastNick = authNick || authUser || '';

            // Render hero immediately from global session state.
            setHero(_lastNick, _lastRole, '');
            applyGating(_lastPerms, _lastRole);

            // Refine with the live /api/auth/me (nickname / role / last IP / perms).
            fetch('/api/auth/me').then(function (r) { return r.ok ? r.json() : null; })
                .then(function (me) {
                    if (me && me.ok) {
                        _lastNick = me.nickname || me.username || _lastNick;
                        _lastRole = me.role || _lastRole;
                        _lastPerms = me.permissions || _lastPerms;
                        _lastIp = me.last_login_ip || '';
                        setHero(_lastNick, _lastRole, _lastIp);
                        applyGating(_lastPerms, _lastRole);
                    }
                }).catch(function () {});

            // Dashboard stats.
            loadStats();

            // Search shortcut.
            var sb = document.getElementById('hdSearchBtn');
            if (sb) sb.addEventListener('click', goSearchFiles);

            // Re-render on language switch.
            window.refreshUI = refreshHome;
        },
        unmount: function () {
            _root = null;
            _lastStats = null;
            window.refreshUI = function () {};
        }
    };
})();
