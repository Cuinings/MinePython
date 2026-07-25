// =====================================================================
//  File Server — theme toggle (P2-3 modularization)
//  Classic script so toggleTheme() / initTheme() stay global.
// =====================================================================

function toggleTheme() {
    var isLight = document.body.classList.toggle('light');
    localStorage.setItem('fs_theme', isLight ? 'light' : 'dark');
    syncThemeBtn();
}

// Reflect the CURRENT theme on the style-switch button. Used both at load
// (after the shared header is mounted) and after every toggle.
function syncThemeBtn() {
    var isLight = document.body.classList.contains('light');
    var tb = document.getElementById('themeBtn');
    if (tb) {
        tb.textContent = isLight ? '☀️' : '🌙';
        tb.setAttribute('aria-label', isLight ? '切换到深色主题' : '切换到浅色主题');
        tb.setAttribute('aria-pressed', isLight ? 'true' : 'false');
    }
}

(function initTheme() {
    if (localStorage.getItem('fs_theme') === 'light') {
        document.body.classList.add('light');
    }
    // The button does not exist yet at script-parse time (it is rendered later
    // by shell.js into #appHeader). The actual button text/aria is synced in
    // startRouter() via syncThemeBtn() once the header is in the DOM.
})();

// Click outside to close the language dropdown
document.addEventListener('click', function(e) {
    var menu = document.getElementById('langMenu');
    var btn = document.getElementById('langBtn');
    if (menu && btn && !menu.contains(e.target) && !btn.contains(e.target)) {
        menu.classList.remove('show');
    }
});
