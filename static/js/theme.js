// =====================================================================
//  File Server — theme toggle (P2-3 modularization)
//  Classic script so toggleTheme() / initTheme() stay global.
// =====================================================================

function toggleTheme() {
    var isLight = document.body.classList.toggle('light');
    localStorage.setItem('fs_theme', isLight ? 'light' : 'dark');
    var tb = document.getElementById('themeBtn');
    if (tb) tb.textContent = isLight ? '☀️' : '🌙';
}

(function initTheme() {
    if (localStorage.getItem('fs_theme') === 'light') {
        document.body.classList.add('light');
        var tb = document.getElementById('themeBtn');
        if (tb) tb.textContent = '☀️';
    }
})();

// Click outside to close the language dropdown
document.addEventListener('click', function(e) {
    var menu = document.getElementById('langMenu');
    var btn = document.getElementById('langBtn');
    if (menu && btn && !menu.contains(e.target) && !btn.contains(e.target)) {
        menu.classList.remove('show');
    }
});
