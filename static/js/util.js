// =====================================================================
//  File Server — shared utility helpers (P2-3 modularization)
//  HTML/CSV escaping used across pages. Loaded as a classic script so the
//  symbols stay on the global scope (the per-page inline scripts rely on it).
// =====================================================================

function escHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function csvCell(v) {
    v = (v == null ? '' : String(v));
    if (/[",\n\r]/.test(v)) v = '"' + v.replace(/"/g, '""') + '"';
    return v;
}
