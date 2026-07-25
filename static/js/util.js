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

// 防抖：连续触发时只在最后一次后 wait 毫秒执行（P1 搜索防抖）。
function debounce(fn, wait) {
    var timer = null;
    var wrapped = function () {
        var ctx = this, args = arguments;
        if (timer) clearTimeout(timer);
        timer = setTimeout(function () { timer = null; fn.apply(ctx, args); }, wait);
    };
    wrapped.cancel = function () { if (timer) { clearTimeout(timer); timer = null; } };
    return wrapped;
}
