// =====================================================================
//  MinePython — SPA shell controller (Phase A)
//  - Renders the shared header ONCE (single source of truth; replaces the
//    5 duplicated hand-written headers across index/files/users/audit/settings).
//  - Swaps views via hash routing (#/home #/files #/users #/audit #/settings,
//    supports #/users?tab=usermgmt). Hash routes never hit the server, so the
//    backend (combined.py / common.py) is untouched and the legacy *.html
//    pages keep working as deep-link fallbacks.
//  - Each view's markup lives in a <template id="tpl-<name>"> in index.html;
//    its logic lives in static/js/views/<name>.js and is registered as
//    window.Views.<name> = { mount(root, params), unmount() }.
// =====================================================================

// ---- Shared header (rendered once; preserves every ID the other scripts use) ----
function renderHeader() {
    var host = document.getElementById('appHeader');
    if (!host || host.dataset.rendered) return;
    host.dataset.rendered = '1';
    // Top bar keeps only the 建议 (Suggest) entry plus the two global
    // controls: 语言切换 (Language switch) and 风格切换 (Style switch).
    // 组织架构 and 用户中心 live on the home page as cards, so they are no
    // longer in the top bar. The language button reflects the current language
    // live via updateLangBtn() (called from startRouter after this header is
    // mounted).
    host.innerHTML =
        '<div class="app-header">' +
            '<h1 data-i18n="h1">📁 MinePython</h1>' +
            '<div class="header-right">' +
            (authToken && authRole && authRole !== 'anonymous'
                ? '<button class="ucenter-btn" onclick="goSuggest()" title="功能需求建议"><span>💡</span> <span data-i18n="nav_suggest">建议</span></button>'
                : '') +
                '<button class="theme-btn" onclick="toggleTheme()" id="themeBtn" title="切换风格" aria-label="切换风格" aria-pressed="false">🌙</button>' +
                '<div class="lang-wrapper">' +
                    '<button class="lang-btn" onclick="toggleLangMenu(event)" id="langBtn" aria-haspopup="true" aria-expanded="false">中文</button>' +
                    '<div class="lang-menu" id="langMenu">' +
                        '<button class="lang-menu-item" data-lang="zh" onclick="switchToLang(\'zh\')">中文</button>' +
                        '<button class="lang-menu-item" data-lang="en" onclick="switchToLang(\'en\')">English</button>' +
                        '<button class="lang-menu-item" data-lang="ru" onclick="switchToLang(\'ru\')">Русский</button>' +
                    '</div>' +
                '</div>' +
            '</div>' +
        '</div>';
}

// ---- Global nav (names preserved so every existing onclick="goXxx()" works) ----
window.goFiles = function () { location.hash = '#/files'; };
window.goAudit = function () { location.hash = '#/audit'; };
window.goSettings = function () { location.hash = '#/settings'; };
window.goUserCenter = function (tab) { location.hash = '#/users' + (tab ? ('?tab=' + tab) : ''); };
window.goApi = function () { window.location.href = '/api'; };
window.goSuggest = function () { location.hash = '#/suggest'; };
window.goOrg = function () { location.hash = '#/org'; };

// ---- Router ----
var _currentView = null;

function _parseHash() {
    var raw = location.hash || '';
    raw = raw.replace(/^#\/?/, '');               // strip leading "#" and optional "/"
    var q = raw.indexOf('?');
    var name = q >= 0 ? raw.slice(0, q) : raw;
    var qs = q >= 0 ? raw.slice(q + 1) : '';
    var params = {};
    qs.split('&').forEach(function (kv) {
        if (!kv) return;
        var p = kv.split('=');
        params[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || '');
    });
    if (!name) name = 'home';
    return { name: name, params: params };
}

function _mountView(route) {
    var name = route.name;
    var root = document.getElementById('viewRoot');
    if (!root) return;
    var view = window.Views && window.Views[name];
    if (!view) { name = 'home'; view = window.Views.home; }

    // Tear down the previous view (clear timers / listeners it registered).
    if (_currentView && typeof _currentView.unmount === 'function') {
        try { _currentView.unmount(); } catch (e) { console.error('unmount', e); }
    }

    // Clone the view's markup from its <template> into the live root.
    var tpl = document.getElementById('tpl-' + name);
    root.innerHTML = '';
    if (tpl && tpl.content) {
        root.appendChild(tpl.content.cloneNode(true));
    }

    // The template was just cloned into the live DOM, so translate any
    // data-i18n / data-i18n-title / data-i18n-placeholder inside it now.
    // applyI18n() (i18n.js) only walked the document at initApp() time, when
    // these <template> contents were NOT yet in the DOM — without this call the
    // initial view would show the raw HTML fallback text until a language
    // switch or async setAppName() re-runs applyI18n().
    if (typeof applyI18n === 'function') {
        try { applyI18n(); } catch (e) { console.error('applyI18n after mount', e); }
    }

    // Phase 1 (F): retrigger the view entrance animation on every mount.
    // Class removal + forced reflow restarts the CSS animation reliably.
    root.classList.remove('view-enter');
    void root.offsetWidth;
    root.classList.add('view-enter');

    window.scrollTo(0, 0);
    _currentView = view;
    try {
        if (typeof view.mount === 'function') view.mount(root, route.params || {});
    } catch (e) {
        console.error('mount ' + name, e);
        root.innerHTML = '<div class="empty">加载失败：' + (e && e.message ? e.message : e) + '</div>';
    }
}

function _route() { _mountView(_parseHash()); }

// Called by init.js's initApp() once the session is established (authed or
// anonymous). Not authed -> initApp already redirected to login.html, so this
// only runs inside the app.
function startRouter() {
    renderHeader();
    // The shared header is now in the DOM, so refresh the controls that must
    // reflect persisted state:
    //  - language button: show the CURRENT language (init.js ran updateLangBtn()
    //    long before the header existed, so it was a no-op).
    //  - style button: show the CURRENT theme icon/aria (initTheme() in theme.js
    //    applied the body class but the button did not exist yet at parse time).
    if (typeof updateLangBtn === 'function') { try { updateLangBtn(); } catch (e) {} }
    if (typeof syncThemeBtn === 'function') { try { syncThemeBtn(); } catch (e) {} }
    if (typeof applyAccountUi === 'function') { try { applyAccountUi(); } catch (e) {} }
    window.addEventListener('hashchange', _route);
    _route();
}

window.onAppReady = startRouter;
