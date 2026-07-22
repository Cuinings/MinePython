// =====================================================================
//  File Server — toast notifications (P2-3 modularization)
// =====================================================================

function toast(msg, err) {
    var el = document.createElement('div');
    el.className = 'toast';
    el.textContent = msg;
    if (err) el.style.borderColor = 'var(--danger)';
    document.body.appendChild(el);
    setTimeout(function() { el.remove(); }, 2500);
}
