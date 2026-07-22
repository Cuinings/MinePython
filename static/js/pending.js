// =====================================================================
//  File Server — pending-approval poll (admin + reviewer) (P2-3)
// =====================================================================

var pendingTimer = null;

async function checkPending() {
    if (authRole !== 'admin' && authRole !== 'reviewer') return;
    try {
        var res = await fetch('/api/admin/pending', { headers: getAuthHeaders() });
        if (!res.ok) return;
        var data = await res.json();
        var bar = document.getElementById('pendingBar');
        if (!bar) return;
        if (data.count > 0) {
            bar.classList.add('show');
            var cnt = document.getElementById('pendingCount');
            var usr = document.getElementById('pendingUsers');
            if (cnt) cnt.textContent = (t('pending_alert') || 'New approvals') + ': ' + data.count;
            if (usr) usr.textContent = data.users.map(function(u) { return u.username; }).join(', ');
        } else {
            bar.classList.remove('show');
        }
    } catch(e) {}
}

function startPendingPoll() {
    if (authRole !== 'admin' && authRole !== 'reviewer') return;
    checkPending();
    if (pendingTimer) clearInterval(pendingTimer);
    pendingTimer = setInterval(checkPending, 30000); // every 30s
}

function stopPendingPoll() {
    if (pendingTimer) { clearInterval(pendingTimer); pendingTimer = null; }
}
