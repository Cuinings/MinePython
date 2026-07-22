// =====================================================================
//  File Server — shared page init (P2-3 modularization)
//  Called by each page after its own view handlers are defined.
// =====================================================================

function initApp() {
    applyI18n();
    updateLangBtn();
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
        showLogin();
    }
    if (typeof updateUploadHint === 'function') updateUploadHint();
}
