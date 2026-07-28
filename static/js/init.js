// =====================================================================
//  File Server — shared page init (P2-3 modularization)
//  Called by each page after its own view handlers are defined.
// =====================================================================

function initApp() {
    applyI18n();
    updateLangBtn();
    // Keep the style-switch (theme) button in sync with the persisted theme.
    // On the SPA the header is rendered later, so this is also re-run in
    // startRouter(); on the legacy pages the header is static and already in
    // the DOM at this point, so this call alone is enough.
    if (typeof syncThemeBtn === 'function') syncThemeBtn();
    if (authToken) {
        // Real session: a valid token always takes precedence and clears any
        // lingering anonymous flag.
        localStorage.removeItem('fs_anon');
        showApp();
        if (authRole === 'admin' || authRole === 'reviewer') startPendingPoll();
        if (typeof onAppReady === 'function') onAppReady();
    } else if (localStorage.getItem('fs_anon') === '1') {
        // Re-enter anonymous guest mode on a fresh page load (no token) so the
        // state survives navigation between index/files/users pages.
        authRole = 'anonymous';
        showApp();
        if (typeof onAppReady === 'function') onAppReady();
    } else {
        // No session at all — send the visitor to the standalone login page.
        // Use replace (not push) so a logged-out view cannot be re-entered via
        // Back after navigating deeper into the SPA history.
        window.location.replace('login.html');
    }
    if (typeof updateUploadHint === 'function') updateUploadHint();
}

// P1：让带 role="button" 的可点击 div（首页卡片、上传入口、文件行、分类标签等）
// 支持键盘操作。原生 <button>/<a> 自身已处理 Enter/Space，这里只覆盖 div。
// 这些元素的 onclick 直接绑在元素上，触发 el.click() 即可复用同一逻辑。
document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    var el = e.target;
    if (el && el.getAttribute && el.getAttribute('role') === 'button' && el.tabIndex >= 0) {
        e.preventDefault();
        el.click();
    }
});
