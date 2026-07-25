// =====================================================================
//  File management view (Phase A SPA split of files.html)
//  Markup: <template id="tpl-files"> in index.html.
//  Functions are global (the template's onclick="..." reference them) and a
//  mount/unmount pair is registered on window.Views.files.
//  Navigation is owned by shell.js (goFiles -> location.hash '#/files').
// =====================================================================

var viewMode = 'files'; // files | upload | detail
var activeCat = 'auto';
var currentPage = 1;
var currentSearch = '';
var pageSize = 20;
var dropZone = null, fileInput = null, fileList = null, uploadHint = null;

function buildCatBar(containerId) {
    var bar = document.getElementById(containerId);
    if (!bar) return;
    fetch('/api/categories', { headers: getAuthHeaders() }).then(function(res) { return res.json(); }).then(function(data) {
        var total = data.categories.reduce(function(s, c) { return s + c.count; }, 0);
        var totalHtml = total ? '<span class="count">' + total + '</span>' : '';
        bar.innerHTML =
            '<span class="cat-tag auto ' + (activeCat==='auto'?'active':'') + '" data-cat="auto" role="button" tabindex="0" onclick="selectCategory(\'auto\')">' +
                t('auto_tag') + totalHtml +
            '</span>' +
            data.categories.map(function(c) {
                return '<span class="cat-tag ' + (activeCat===c.category?'active':'') + '" data-cat="' + c.category + '" role="button" tabindex="0" onclick="selectCategory(\'' + c.category + '\')">' +
                    c.category + '<span class="count">' + c.count + '</span>' +
                    '<span class="cat-del" title="' + t('del_title') + '" onclick="delCat(event,\'' + c.category + '\')">✕</span>' +
                '</span>';
            }).join('') +
            '<span class="cat-new" role="button" tabindex="0" onclick="newCategory()">' + t('new_tag') + '</span>';
    });
}

function selectCategory(cat) {
    activeCat = cat;
    currentPage = 1;
    updateUploadHint();
    buildCatBar('catBar');
    buildCatBar('uploadCatBar');
    if (viewMode === 'files') loadFiles();
}

async function newCategory() {
    var name = await promptModal({ title: (t('new_tag') || '新建分类'), label: t('prompt_cat') });
    if (!name) return;
    activeCat = name.trim();
    buildCatBar('catBar');
    buildCatBar('uploadCatBar');
    if (viewMode === 'files') loadFiles();
    updateUploadHint();
}

async function delCat(e, cat) {
    e.stopPropagation();
    if (!(await confirmModal({ title: (t('del_title') || '删除分类'), message: escHtml(t('confirm_del_cat') + cat + t('and_all_files')), danger: true }))) return;
    var res = await fetch('/api/categories/' + encodeURIComponent(cat), { method: 'DELETE', headers: getAuthHeaders() });
    if (res.ok) {
        if (activeCat === cat) activeCat = 'auto';
        toast(t('toast_deleted'));
        buildCatBar('catBar');
        buildCatBar('uploadCatBar');
        if (viewMode === 'files') loadFiles();
        updateUploadHint();
    } else { toast(t('toast_del_failed'), true); }
}

function updateUploadHint() {
    if (!uploadHint) return;
    if (activeCat === 'auto') {
        uploadHint.textContent = t('hint_auto');
        uploadHint.style.background = 'rgba(163,113,247,.15)';
        uploadHint.style.color = 'var(--purple)';
    } else {
        uploadHint.textContent = t('hint_target') + activeCat;
        uploadHint.style.background = 'rgba(88,166,255,.15)';
        uploadHint.style.color = 'var(--accent)';
    }
}

// Upload each file as its own request so it gets its own progress bar, while
// running a bounded number of them concurrently. Atomicity is per-file now
// (each POST /api/upload commits independently) — a failed file no longer
// rolls back the others, which is the accepted trade-off for per-file UX.
var UPLOAD_CONCURRENCY = 6;

function uploadFiles(files) {
    files = Array.prototype.slice.call(files || []);
    if (!files.length) return;
    var cat = activeCat || 'auto';

    var overlay = document.getElementById('uploadOverlay');
    if (overlay && overlay._hideTimer) { clearTimeout(overlay._hideTimer); }
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'uploadOverlay';
        overlay.style.cssText = 'position:fixed;right:20px;bottom:20px;width:340px;' +
            'max-height:60vh;display:flex;flex-direction:column;' +
            'background:var(--card,#1c2128);border:1px solid var(--border);' +
            'border-radius:var(--r-md,12px);box-shadow:0 8px 30px rgba(0,0,0,.35);' +
            'z-index:9999;overflow:hidden;font-size:13px;color:var(--text,#e6edf3)';
        document.body.appendChild(overlay);
    }
    overlay.innerHTML = '';
    overlay.style.display = 'flex';

    var header = document.createElement('div');
    header.style.cssText = 'padding:10px 14px;font-weight:600;' +
        'border-bottom:1px solid var(--border);' +
        'display:flex;justify-content:space-between;align-items:center;gap:10px';
    var titleEl = document.createElement('span');
    titleEl.textContent = '上传中…';
    var counterEl = document.createElement('span');
    counterEl.style.cssText = 'color:var(--dim);font-weight:400;font-size:12px';
    counterEl.textContent = '0 / ' + files.length;
    var left = document.createElement('span');
    left.style.cssText = 'display:flex;align-items:center;gap:8px';
    left.appendChild(titleEl);
    left.appendChild(counterEl);
    var closeBtn = document.createElement('button');
    closeBtn.textContent = '×';
    closeBtn.title = '收起';
    closeBtn.style.cssText = 'border:none;background:transparent;color:var(--dim);' +
        'font-size:18px;line-height:1;cursor:pointer;padding:0 4px';
    closeBtn.onclick = function() {
        if (overlay._hideTimer) clearTimeout(overlay._hideTimer);
        overlay.style.display = 'none';
    };
    header.appendChild(left);
    header.appendChild(closeBtn);
    overlay.appendChild(header);

    var list = document.createElement('div');
    list.style.cssText = 'padding:10px 14px;overflow-y:auto';
    overlay.appendChild(list);

    var total = files.length;
    var done = 0, ok = 0, fail = 0;
    var idx = 0, active = 0;

    function makeRow(name) {
        var row = document.createElement('div');
        row.style.marginBottom = '10px';
        var head = document.createElement('div');
        head.style.cssText = 'display:flex;justify-content:space-between;font-size:12px;' +
            'color:var(--dim);margin-bottom:4px';
        var nameEl = document.createElement('span');
        nameEl.textContent = name;
        nameEl.style.cssText = 'max-width:78%;overflow:hidden;text-overflow:ellipsis;' +
            'white-space:nowrap';
        var pctEl = document.createElement('span');
        pctEl.textContent = '0%';
        head.appendChild(nameEl);
        head.appendChild(pctEl);
        var track = document.createElement('div');
        track.style.cssText = 'height:6px;background:var(--border);' +
            'border-radius:var(--r-xs,4px);overflow:hidden';
        var bar = document.createElement('div');
        bar.style.cssText = 'height:100%;background:var(--accent);width:0;transition:width .2s';
        track.appendChild(bar);
        row.appendChild(head);
        row.appendChild(track);
        list.appendChild(row);
        return { bar: bar, pct: pctEl };
    }

    function uploadOne(file, refs) {
        return new Promise(function(resolve) {
            var fd = new FormData();
            fd.append('category', cat);
            fd.append('file', file);
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/api/upload');
            var authHeaders = getAuthHeaders();
            if (authHeaders.Authorization) xhr.setRequestHeader('Authorization', authHeaders.Authorization);
            xhr.upload.onprogress = function(e) {
                if (e.lengthComputable) {
                    var pct = Math.round(e.loaded / e.total * 100);
                    refs.bar.style.width = pct + '%';
                    refs.pct.textContent = pct + '%';
                }
            };
            xhr.onload = function() {
                if (xhr.status >= 200 && xhr.status < 300) {
                    ok++;
                    refs.bar.style.width = '100%';
                    refs.pct.textContent = '100%';
                    refs.bar.style.background = 'var(--ok, #3fb950)';
                } else {
                    fail++;
                    refs.bar.style.background = 'var(--err, #f85149)';
                    refs.pct.textContent = (xhr.status === 413) ? '过大' : '失败';
                }
                finishOne();
                resolve();
            };
            xhr.onerror = function() {
                fail++;
                refs.bar.style.background = 'var(--err, #f85149)';
                refs.pct.textContent = '失败';
                finishOne();
                resolve();
            };
            xhr.send(fd);
        });
    }

    function finishOne() {
        done++;
        counterEl.textContent = done + ' / ' + total;
        if (done === total) allDone();
    }

    function allDone() {
        fileInput.value = '';
        titleEl.textContent = fail ? '上传完成（有失败）' : '上传完成';
        overlay._hideTimer = setTimeout(function() {
            if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
        }, 1800);
        if (ok > 0) {
            var extra = fail ? '（' + ok + ' 成功 / ' + fail + ' 失败）' : '';
            toast(t('toast_upload_ok') + (cat === 'auto' ? t('auto_label') : cat) + extra);
            buildCatBar('catBar');
            buildCatBar('uploadCatBar');
            showFilesView();
        } else {
            toast(t('toast_upload_fail'), true);
        }
    }

    function pump() {
        while (idx < total && active < UPLOAD_CONCURRENCY) {
            var i = idx++;
            active++;
            var refs = makeRow(files[i].name);
            uploadOne(files[i], refs).then(function() {
                active--;
                pump();
            });
        }
    }
    pump();
}

// File list
var PREVIEW_ICONS = {
    '图片': '🖼️', '文档': '📄', '视频': '🎥',
    '音频': '🎵', '压缩包': '📦', '代码': '💻',
    '安装包': '📦', '其他': '📁'
};
var IMAGE_EXTS = ['.jpg','.jpeg','.png','.gif','.webp','.bmp','.svg','.ico'];

function getPreviewHtml(f) {
    var ext = '.' + f.filename.split('.').pop().toLowerCase();
    var catClass = ' file-preview-' + (f.category || 'other');
    if (IMAGE_EXTS.indexOf(ext) >= 0) {
        return '<div class="file-preview file-preview-img' + catClass + '"><img src="' + downloadUrl(f.path) + '" loading="lazy" onerror="this.parentElement.innerHTML=\'' + (PREVIEW_ICONS[f.category] || '📁') + '\'"></div>';
    }
    return '<div class="file-preview' + catClass + '">' + (PREVIEW_ICONS[f.category] || '📁') + '</div>';
}

var currentDetailFile = null;
// Indexable cache of the current file listing (P2 XSS fix): the detail view is
// opened by row index instead of embedding the (attacker-controlled) filename
// into an HTML attribute / JS string literal.
var _fileRows = [];
function showFileDetailIdx(i) {
    var f = _fileRows[i];
    if (f) showFileDetail(f);
}

function canDeleteFile(f) {
    if (!authUser || !authRole || authRole === 'anonymous') return false;
    if (authRole === 'admin') return true;
    return (f.uploaded_by || 'anonymous') === authUser;
}

function showFileDetail(f) {
    currentDetailFile = f;
    viewMode = 'detail';
    var vf = document.getElementById('viewFiles'); if (vf) vf.style.display = 'none';
    var vu = document.getElementById('viewUpload'); if (vu) vu.style.display = 'none';
    var vd = document.getElementById('viewDetail'); if (vd) vd.style.display = 'block';

    var preview = buildInlinePreviewHtml(f.path, f.filename);

    var dc = document.getElementById('detailContent');
    if (dc) dc.innerHTML =
        '<div class="detail-preview">' + preview + '</div>' +
        '<div class="detail-info">' +
            '<div class="label">' + (t('detail_name') || 'Filename') + '</div><div class="value">' + escHtml(f.filename) + '</div>' +
            '<div class="label">' + (t('detail_category') || 'Category') + '</div><div class="value">' + f.category + '</div>' +
            '<div class="label">' + (t('detail_path') || 'Path') + '</div><div class="value">' + f.path + '</div>' +
            '<div class="label">' + (t('detail_size') || 'Size') + '</div><div class="value">' + f.size_human + ' (' + (f.size || 0) + ' bytes)</div>' +
            '<div class="label">' + (t('detail_uploader') || 'Uploader') + '</div><div class="value">' + (f.uploader_nickname || f.uploaded_by || 'anonymous') + '</div>' +
            '<div class="label">' + (t('detail_ip') || 'IP') + '</div><div class="value">' + (f.uploaded_ip || '-') + '</div>' +
            '<div class="label">' + (t('detail_time') || 'Time') + '</div><div class="value">' + (f.uploaded_at || '-') + '</div>' +
        '</div>' +
        '<div class="detail-actions">' +
            '<a class="btn" href="' + downloadUrl(f.path) + '" download>' + t('btn_dl') + '</a>' +
            (canAdbInstall() && isApk(f.path) ? '<button class="btn" onclick="adbStart(\'' + f.path.replace(/'/g, "\\'") + '\')">' + t('btn_adb_install') + '</button>' : '') +
            (canDeleteFile(f) ? '<button class="btn btn-danger" onclick="delFileFromDetail()">' + t('btn_del') + '</button>' : '') +
        '</div>';
}

async function delFileFromDetail() {
    if (!currentDetailFile) return;
    var f = currentDetailFile;
    if (!(await confirmModal({ message: escHtml(t('confirm_del_file') + f.path + '"?'), danger: true }))) return;
    var res = await fetch('/api/files/' + encodeURIComponent(f.path), { method: 'DELETE', headers: getAuthHeaders() });
    if (res.ok) { toast(t('toast_deleted')); showFilesView(); }
    else toast(t('toast_del_failed'), true);
}

async function loadFiles() {
    var params = new URLSearchParams();
    if (activeCat && activeCat !== 'auto') params.set('category', activeCat);
    if (currentSearch) params.set('search', currentSearch);
    params.set('page', currentPage);
    params.set('page_size', pageSize);
    if (fileList) fileList.innerHTML = renderFileSkeleton();
    var url = '/api/files?' + params.toString();
    var res = await fetch(url, { headers: getAuthHeaders() });
    if (!res.ok) {
        if (res.status === 401) {
            forceLogout();
        } else {
            if (fileList) fileList.innerHTML = '<div class="empty">' + (t('toast_failed') || 'Failed') + '</div>';
        }
        return;
    }
    var data = await res.json();
    _fileRows = data.files;

    var lt = document.getElementById('listTitle');
    if (lt) lt.textContent =
        (activeCat && activeCat !== 'auto')
            ? t('cat_label') + activeCat + ' (' + data.total + ')'
            : t('all_files') + ' (' + data.total + ')';

    if (!data.files.length) {
        if (fileList) fileList.innerHTML = '<div class="empty">' + t('no_files') +
            '<div style="margin-top:14px"><button class="btn" onclick="goUpload()">' + t('upload_entry') + '</button></div></div>';
        var pg = document.getElementById('pagination'); if (pg) pg.innerHTML = '';
        updateBatchUI();
        return;
    }
    var showCat = !activeCat || activeCat === 'auto';
    var html = '';
    data.files.forEach(function(f, i) {
        var by = f.uploaded_by === 'anonymous' ? t('anonymous') : (f.uploader_nickname || f.uploaded_by);
        var preview = getPreviewHtml(f);
        var typeLabel = f.category || 'file';
        var dotIdx = f.filename.lastIndexOf('.');
        var ext = (dotIdx > 0) ? f.filename.slice(dotIdx + 1).toUpperCase() : '';
        var previewable = isPreviewable(f.path);
        html += '<div class="file-card">' +
            '<input type="checkbox" class="file-check" data-path="' + f.path + '" onclick="event.stopPropagation();updateBatchUI()">' +
            '<div class="file-body" role="button" tabindex="0" onclick="showFileDetailIdx(' + i + ')">' +
            preview +
            '<div class="file-main">' +
                '<div class="file-name-line">' +
                    '<span class="file-name" title="' + escHtml(f.path) + '">' + escHtml(f.filename) + '</span>' +
                    (ext ? '<span class="file-ext-badge">' + escHtml(ext) + '</span>' : '') +
                '</div>' +
                '<div class="file-meta-row">' +
                    (showCat ? '<span class="file-type" title="' + t('detail_category') + '">' + typeLabel + '</span>' : '') +
                    '<span class="file-uploader" title="IP: ' + (f.uploaded_ip || '-') + '">● ' + escHtml(by) + '</span>' +
                '</div>' +
                '<div class="file-bottom-row">' +
                    '<span class="file-time" title="' + (f.uploaded_at || '') + '">' + (f.uploaded_at || '-') + '</span>' +
                    '<span class="file-size-dot">·</span>' +
                    '<span class="file-size-val">' + f.size_human + '</span>' +
                '</div>' +
            '</div>' +
            '<div class="file-actions">' +
                (previewable ? '<button class="btn btn-xs" onclick="event.stopPropagation();openPreview(\'' + f.path + '\')">' + t('btn_preview') + '</button>' : '') +
                (canAdbInstall() && isApk(f.path) ? '<button class="btn btn-xs" onclick="event.stopPropagation();adbStart(\'' + f.path.replace(/'/g, "\\'") + '\')">' + t('btn_adb_install') + '</button>' : '') +
                '<a class="btn btn-xs" href="' + downloadUrl(f.path) + '" download onclick="event.stopPropagation()">' + t('btn_dl') + '</a>' +
                (canDeleteFile(f) ? '<button class="btn btn-xs btn-danger" onclick="event.stopPropagation();delFile(\'' + f.path + '\')">' + t('btn_del') + '</button>' : '') +
            '</div>' +
            '</div></div>';
    });
    if (fileList) fileList.innerHTML = html;

    var totalPages = Math.ceil(data.total / pageSize) || 1;
    var pg = document.getElementById('pagination');
    if (pg) pg.innerHTML = buildPagination(currentPage, totalPages);
    updateBatchUI();
}

function onSearch() {
    currentSearch = (document.getElementById('searchInput') ? document.getElementById('searchInput').value : '').trim();
    currentPage = 1;
    loadFiles();
}

// P1：搜索输入防抖，避免每键一次请求（250ms）
var onSearchDebounced = debounce(onSearch, 250);

function goPage(p) {
    currentPage = p;
    loadFiles();
}

// P1：窗口式分页，避免文件数多时渲染上百个页码按钮。
function buildPagination(cur, total) {
    if (total <= 1) return '';
    var html = '';
    html += '<button class="btn btn-xs" onclick="goPage(' + Math.max(1, cur - 1) + ')"' +
        (cur <= 1 ? ' disabled' : '') + '>◀</button>';

    var pages = [];
    if (total <= 7) {
        for (var i = 1; i <= total; i++) pages.push(i);
    } else {
        pages.push(1);
        var start = Math.max(2, cur - 1), end = Math.min(total - 1, cur + 1);
        if (start > 2) pages.push('...');
        for (var j = start; j <= end; j++) pages.push(j);
        if (end < total - 1) pages.push('...');
        pages.push(total);
    }
    pages.forEach(function (p) {
        if (p === '...') {
            html += '<span class="pag-ellipsis">…</span>';
        } else {
            var active = (p === cur);
            html += '<button class="btn btn-xs" onclick="goPage(' + p + ')"' +
                (active ? ' style="background:var(--accent);color:#fff"' : '') + '>' + p + '</button>';
        }
    });

    html += '<button class="btn btn-xs" onclick="goPage(' + Math.min(total, cur + 1) + ')"' +
        (cur >= total ? ' disabled' : '') + '>▶</button>';
    html += '<span class="pag-jump">跳至<input type="number" min="1" max="' + total +
        '" class="pag-jump-input" onchange="var v=parseInt(this.value,10);if(v>=1&&v<=' + total + ')goPage(v)">页</span>';
    return html;
}

// P2：文件列表骨架屏（替代纯文字「加载中…」，减少布局跳动）
function renderFileSkeleton() {
    var h = '';
    for (var i = 0; i < 6; i++) {
        h += '<div class="file-card skeleton-card">' +
            '<div class="skeleton skeleton-preview"></div>' +
            '<div class="file-main">' +
                '<div class="skeleton skeleton-line" style="width:55%"></div>' +
                '<div class="skeleton skeleton-line short"></div>' +
            '</div>' +
        '</div>';
    }
    return h;
}

function updateBatchUI() {
    var checked = document.querySelectorAll('.file-check:checked');
    var all = document.querySelectorAll('.file-check');
    var count = checked.length;
    var bdel = document.getElementById('batchDelBtn'); if (bdel) bdel.style.display = count ? 'inline-block' : 'none';
    var bdl = document.getElementById('batchDlBtn'); if (bdl) bdl.style.display = count ? 'inline-block' : 'none';
    var sc = document.getElementById('selectCount'); if (sc) sc.textContent = count ? '已选 ' + count + ' 项' : '';
    var selAll = document.getElementById('selectAll');
    if (selAll) selAll.checked = (all.length > 0 && checked.length === all.length);
}

function toggleSelectAll(cb) {
    document.querySelectorAll('.file-check').forEach(function(chk) { chk.checked = cb.checked; });
    updateBatchUI();
}

async function batchDownload() {
    var checked = document.querySelectorAll('.file-check:checked');
    if (!checked.length) return;
    var paths = Array.from(checked).map(function(c) { return c.dataset.path; });
    toast(t('batch_dl_done') || 'Packing...');
    try {
        var res = await fetch('/api/files/batch-download', {
            method: 'POST',
            headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
            body: JSON.stringify({ paths: paths }),
        });
        if (!res.ok) {
            var err = await res.json().catch(function() { return {}; });
            toast(err.detail || err.message || t('toast_failed'), true);
            return;
        }
        var blob = await res.blob();
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'files_' + Date.now() + '.zip';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        toast(t('batch_dl_done') || 'Download ready');
    } catch (e) {
        toast(t('toast_failed'), true);
    }
}

async function batchDelete() {
    var checked = document.querySelectorAll('.file-check:checked');
    if (!checked.length) return;
    if (!(await confirmModal({ message: '确认删除选中的 ' + checked.length + ' 个文件？', danger: true }))) return;
    var paths = Array.from(checked).map(function(c) { return c.dataset.path; });
    var res = await fetch('/api/files/batch-delete', {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
        body: JSON.stringify({ paths: paths }),
    });
    var data = await res.json().catch(function() { return {}; });
    if (res.ok && data.ok) {
        var skipped = (data.failed && data.failed.length) || 0;
        toast(t('toast_deleted') + (skipped ? ' (' + skipped + ' 跳过)' : ''));
        loadFiles();
        buildCatBar('catBar');
    } else {
        toast(data.detail || data.message || t('toast_del_failed'), true);
    }
}

async function delFile(path) {
    if (!(await confirmModal({ message: escHtml(t('confirm_del_file') + path + '"?'), danger: true }))) return;
    var res = await fetch('/api/files/' + encodeURIComponent(path), { method: 'DELETE', headers: getAuthHeaders() });
    if (res.ok) { toast(t('toast_deleted')); buildCatBar('catBar'); buildCatBar('uploadCatBar'); loadFiles(); }
    else toast(t('toast_del_failed'), true);
}

async function organizeRoot() {
    if (!(await confirmModal({ message: escHtml(t('confirm_organize')) }))) return;
    var res = await fetch('/api/organize', { method: 'POST', headers: getAuthHeaders() });
    var data = await res.json();
    if (data.ok) {
        toast(t('toast_organized') + data.moved + t('files_suffix'));
        buildCatBar('catBar');
        buildCatBar('uploadCatBar');
        if (viewMode === 'files') loadFiles();
    } else { toast(data.message || t('toast_organize_fail'), true); }
}

// ===== P1-3: inline file preview =====
var PREVIEW_IMG = ['.jpg','.jpeg','.png','.gif','.webp','.bmp','.svg','.ico'];
var PREVIEW_VIDEO = ['.mp4','.webm','.ogg','.mov','.m4v','.avi','.mkv','.wmv','.flv'];
var PREVIEW_AUDIO = ['.mp3','.wav','.flac','.aac','.ogg','.m4a','.opus','.wma'];
var PREVIEW_DOC = ['.pdf','.txt','.html','.htm','.md','.markdown','.json','.xml','.csv','.log','.js','.css','.py','.java','.c','.cpp','.go','.rs','.sh','.yml','.yaml'];

function isPreviewable(path) {
    var ext = (path.split('.').pop() || '').toLowerCase();
    return PREVIEW_IMG.indexOf('.' + ext) >= 0
        || PREVIEW_VIDEO.indexOf('.' + ext) >= 0
        || PREVIEW_AUDIO.indexOf('.' + ext) >= 0
        || PREVIEW_DOC.indexOf('.' + ext) >= 0;
}

function buildInlinePreviewHtml(path, filename) {
    var ext = (path.split('.').pop() || '').toLowerCase();
    var url = previewUrl(path);
    var dl = downloadUrl(path);
    if (PREVIEW_IMG.indexOf('.' + ext) >= 0) {
        return '<img class="preview-media" src="' + url + '" onerror="imgFallback(this)">';
    }
    if (PREVIEW_VIDEO.indexOf('.' + ext) >= 0) {
        return '<video class="preview-media" controls autoplay src="' + url + '"></video>';
    }
    if (PREVIEW_AUDIO.indexOf('.' + ext) >= 0) {
        return '<audio class="preview-media" controls autoplay src="' + url + '"></audio>';
    }
    if (PREVIEW_DOC.indexOf('.' + ext) >= 0) {
        return '<iframe class="preview-frame" src="' + url + '"></iframe>';
    }
    return '<div class="preview-fallback">' +
        '<div class="preview-fallback-icon">📄</div>' +
        '<div class="preview-fallback-text">' + (t('preview_unsupported') || 'Cannot preview this file type.') + '</div>' +
        '<a class="btn" href="' + dl + '" download>' + (t('btn_dl') || 'Download') + '</a>' +
        '</div>';
}

function imgFallback(img) {
    var box = document.createElement('div');
    box.className = 'preview-fallback';
    box.innerHTML = '<div class="preview-fallback-text">' + (t('preview_unsupported') || 'Cannot preview this.') + '</div>';
    if (img && img.parentNode) img.parentNode.replaceChild(box, img);
}

function previewUrl(path) {
    return '/api/preview/' + encodeURIComponent(path) + getTokenParam();
}

function openPreview(path) {
    var pb = document.getElementById('previewBody');
    if (pb) pb.innerHTML = buildInlinePreviewHtml(path, path);
    showModal('previewModal');
}

function closePreview() {
    hideModal('previewModal');
    var b = document.getElementById('previewBody');
    if (b) b.innerHTML = '';
}

// ===== View sub-navigation (within this module) =====
// NOTE: goFiles is owned by shell.js (hash navigation). For in-view "back to
// file list" we use showFilesView(), which only toggles the sub-views.
function showFilesView() {
    viewMode = 'files';
    var vf = document.getElementById('viewFiles'); if (vf) vf.style.display = 'block';
    var vu = document.getElementById('viewUpload'); if (vu) vu.style.display = 'none';
    var vd = document.getElementById('viewDetail'); if (vd) vd.style.display = 'none';
    buildCatBar('catBar');
    loadFiles();
}
function goUpload() {
    viewMode = 'upload';
    var vf = document.getElementById('viewFiles'); if (vf) vf.style.display = 'none';
    var vd = document.getElementById('viewDetail'); if (vd) vd.style.display = 'none';
    var vu = document.getElementById('viewUpload'); if (vu) vu.style.display = 'block';
    updateUploadHint();
    buildCatBar('uploadCatBar');
}

function refreshUI() {
    buildCatBar('catBar');
    buildCatBar('uploadCatBar');
    if (viewMode === 'files') loadFiles();
}

// ===== Self-service: change password / deactivate account =====

// Hide the "注销账号" entry for the protected default account.
function applyAccountUi() {
    var el = document.getElementById('deactivateMenuItem');
    var isProtected = authRole === 'anonymous' || authIsDefault || (authUser && authUser === authBootstrapAdmin);
    if (el) el.style.display = isProtected ? 'none' : '';
}

// Re-sync the default-account flag from the server so the menu is correct even
// after a page reload or on clients with stale local state.
async function syncAccountFlags() {
    try {
        var res = await fetch('/api/auth/me', { headers: getAuthHeaders() });
        if (res.ok) applyAccountFlags(await res.json());
    } catch (e) { /* keep locally cached flag on network error */ }
    applyAccountUi();
}

function toggleUserMenu(e) {
    e.stopPropagation();
    if (authRole === 'anonymous') return;
    var m = document.getElementById('userMenu');
    if (m) m.classList.toggle('show');
}

function openChangePwModal() {
    var m = document.getElementById('userMenu'); if (m) m.classList.remove('show');
    var o = document.getElementById('changePwOld'); if (o) o.value = '';
    var n = document.getElementById('changePwNew'); if (n) n.value = '';
    var c = document.getElementById('changePwConfirm'); if (c) c.value = '';
    var e = document.getElementById('changePwErr'); if (e) e.textContent = '';
    showModal('changePwModal');
}

function closeChangePwModal() {
    hideModal('changePwModal');
}

async function submitChangePw() {
    var oldP = document.getElementById('changePwOld').value;
    var newP = document.getElementById('changePwNew').value;
    var cfm = document.getElementById('changePwConfirm').value;
    var err = document.getElementById('changePwErr');
    if (!oldP || !newP) { err.textContent = (t('fill_fields') || 'Fill all fields'); return; }
    if (newP !== cfm) { err.textContent = t('pw_mismatch'); return; }
    var res = await fetch('/api/auth/me/password', {
        method: 'PUT',
        headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
        body: JSON.stringify({ old_password: oldP, new_password: newP }),
    });
    var data = await res.json().catch(function () { return {}; });
    if (res.ok && data.ok) {
        closeChangePwModal();
        forceLogout(t('pw_changed_relogin'));
    } else {
        err.textContent = data.detail || data.message || (t('toast_failed') || 'Failed');
    }
}

async function deactivateAccount() {
    var m = document.getElementById('userMenu'); if (m) m.classList.remove('show');
    if (!(await confirmModal({ message: escHtml(t('deactivate_confirm')), danger: true }))) return;
    var res = await fetch('/api/auth/me/deactivate', { method: 'POST', headers: getAuthHeaders() });
    var data = await res.json().catch(function () { return {}; });
    if (res.ok && data.ok) {
        forceLogout(t('acct_deactivated'));
    } else {
        toast(data.detail || data.message || (t('toast_failed') || 'Failed'), true);
    }
}

// Close the user dropdown when clicking outside it.
document.addEventListener('click', function (e) {
    var wrap = document.querySelector('.user-menu-wrap');
    var menu = document.getElementById('userMenu');
    if (menu && menu.classList.contains('show') && wrap && !wrap.contains(e.target)) {
        menu.classList.remove('show');
    }
});

// ===== ADB 一键安装 APK (P-ADB) =====
function isApk(path) {
    var ext = (path.split('.').pop() || '').toLowerCase();
    return ext === 'apk';
}
function canAdbInstall() {
    return !!authRole && authRole !== 'anonymous';
}

function openAdbModal(html) {
    var m = document.getElementById('adbModal');
    var title = document.getElementById('adbModalTitle');
    if (title) title.textContent = t('adb_title') || 'ADB 安装';
    var b = document.getElementById('adbModalBody');
    if (b) b.innerHTML = html;
    if (m) showModal('adbModal');
}
function setAdbModalBody(html) {
    var b = document.getElementById('adbModalBody');
    if (b) b.innerHTML = html;
}
function closeAdbModal() {
    hideModal('adbModal');
    var b = document.getElementById('adbModalBody');
    if (b) b.innerHTML = '';
}

// ---- ADB 安装引导向导（未检测到 adb 时展示） ----
var adbCurrentPath = null;

window.addEventListener('error', function (ev) {
    try { toast('JS 错误：' + (ev.message || (ev.error && ev.error.message) || '未知'), true); } catch (_) {}
});
window.addEventListener('unhandledrejection', function (ev) {
    try { var r = ev.reason; toast('异步错误：' + (r && r.message ? r.message : String(r)), true); } catch (_) {}
});

function adbOsDetect() {
    var ua = navigator.userAgent || '';
    if (/Win/i.test(ua)) return 'win';
    if (/Mac/i.test(ua)) return 'mac';
    if (/Linux|X11/i.test(ua)) return 'linux';
    return 'win';
}

function adbStep(n, title, body) {
    return '<div class="adb-step">' +
        '<div class="adb-step-no">' + n + '</div>' +
        '<div class="adb-step-body">' +
            '<div class="adb-step-title">' + escHtml(title) + '</div>' +
            '<div class="adb-step-text">' + body + '</div>' +
        '</div>' +
    '</div>';
}

function adbStepsHtml(os) {
    var dl = '<a href="https://developer.android.com/tools/releases/platform-tools" target="_blank" rel="noopener">developer.android.com/tools/releases/platform-tools</a>';
    var win = ''
        + adbStep(1, t('adb_s1_dl'), '从 ' + dl + ' 下载 <code>platform-tools-latest-windows.zip</code>。')
        + adbStep(2, t('adb_s2_extract'), '解压到本地目录，例如 <code>C:\\platform-tools</code>。')
        + adbStep(3, t('adb_s3_path'), '把 <code>C:\\platform-tools</code> 加入系统环境变量 <b>Path</b>；或在<b>服务端</b>的 <code>.env</code> 写入 <code>ADB_PATH=C:\\platform-tools\\adb.exe</code>。')
        + adbStep(4, t('adb_s4_verify'), '打开 PowerShell 运行 <code>adb version</code>，显示版本号即安装成功。')
        + adbStep(5, t('adb_s5_phone'), '手机：设置 → 关于手机 → 连点「版本号」7 次开启<b>开发者选项</b> → 返回 → 系统与更新 → 开发者选项 → 开启「<b>USB 调试</b>」。')
        + adbStep(6, t('adb_s6_rescan'), '用<b>数据线</b>把手机连到<b>运行本服务的机器</b>，弹窗点「<b>允许</b>」；回到本页点「<b>重新检测</b>」。');
    var mac = ''
        + adbStep(1, t('adb_s1_dl'), '推荐：终端执行 <code>brew install android-platform-tools</code>。或下载 <code>platform-tools-latest-darwin.zip</code> 解压到 <code>~/platform-tools</code>。')
        + adbStep(2, t('adb_s2_extract'), '解压到本地目录 <code>~/platform-tools</code>。')
        + adbStep(3, t('adb_s3_path'), '在 <code>~/.zshrc</code> 追加 <code>export PATH=$PATH:~/platform-tools</code> 后执行 <code>source ~/.zshrc</code>；或在 <code>.env</code> 设 <code>ADB_PATH=~/platform-tools/adb</code>。')
        + adbStep(4, t('adb_s4_verify'), '终端运行 <code>adb version</code> 验证。')
        + adbStep(5, t('adb_s5_phone'), '手机开启<b>开发者选项</b>与「<b>USB 调试</b>」（同 Windows 步骤 5）。')
        + adbStep(6, t('adb_s6_rescan'), '用数据线连到<b>运行本服务的机器</b>，弹窗点「允许」；回本页点「重新检测」。');
    var linux = ''
        + adbStep(1, t('adb_s1_dl'), 'Debian/Ubuntu 终端执行 <code>sudo apt update &amp;&amp; sudo apt install -y android-tools-adb</code>；或其它发行版从 ' + dl + ' 下载 zip。')
        + adbStep(2, t('adb_s2_extract'), '解压到本地目录，例如 <code>~/platform-tools</code>。')
        + adbStep(3, t('adb_s3_path'), '将解压目录加入 PATH，或在 <code>.env</code> 设 <code>ADB_PATH=/path/to/platform-tools/adb</code>。')
        + adbStep(4, t('adb_s4_verify'), '终端运行 <code>adb version</code> 验证。')
        + adbStep(5, t('adb_s5_phone'), '手机开启<b>开发者选项</b>与「<b>USB 调试</b>」。')
        + adbStep(6, t('adb_s6_rescan'), '用数据线连到<b>运行本服务的机器</b>，弹窗点「允许」；回本页点「重新检测」。');
    if (os === 'mac') return mac;
    if (os === 'linux') return linux;
    return win;
}

function adbOsTab(os, activeOs, label) {
    return '<button class="adb-os' + (os === activeOs ? ' active' : '') + '" data-os="' + os + '" onclick="adbSetOs(\'' + os + '\')">' + label + '</button>';
}

function adbNeedHttpsHtml() {
    return '<div class="adb-guide">' +
        '<div class="adb-guide-intro">' + escHtml(t('adb_need_https') ||
            'WebUSB 需要安全上下文（HTTPS）。请通过 https 打开本页面（例如 https://服务器地址:8000/files.html），浏览器会禁用 http 下的设备连接。') + '</div>' +
        '<div class="adb-actions"><button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button></div>' +
    '</div>';
}
function adbNeedBrowserHtml() {
    return '<div class="adb-guide">' +
        '<div class="adb-guide-intro">' + escHtml(t('adb_need_browser') ||
            '当前浏览器不支持 WebUSB。请使用 Chrome / Edge / Brave 等基于 Chromium 的浏览器打开本页面。') + '</div>' +
        '<div class="adb-actions"><button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button></div>' +
    '</div>';
}
function adbRetry() { adbWifiRescan(); }

function adbGuideHtml(path) {
    adbCurrentPath = path || null;
    return '<div class="adb-guide">' +
        '<div class="adb-guide-intro">' + escHtml(t('adb_guide_webusb_intro') ||
            '若手机已通过 <b>WiFi（网络 ADB）</b> 连到电脑，点「ADB安装」后会先让你填手机 WiFi 地址让服务器去连，再走服务端安装（服务器需能访问该 IP）。若用 <b>USB 数据线</b> 直连本机，则走浏览器 WebUSB 通道。') + '</div>' +
        adbStep(1, t('adb_w1') || '用 Chrome / Edge 打开本页', '必须使用基于 Chromium 的浏览器，并通过 <b>https</b>（非 http）访问本页。') +
        adbStep(2, t('adb_w2') || '手机开启 USB 调试', '设置 → 关于手机 → 连点「版本号」7 次开启<b>开发者选项</b> → 开发者选项 → 开启「<b>USB 调试</b>」。') +
        adbStep(3, t('adb_w3') || '连接并授权', '用<b>数据线</b>把手机连到<b>这台电脑（B）</b>；浏览器会弹出 USB 设备选择，选中手机并点「连接」；手机上点「<b>允许</b>」USB 调试。') +
        adbStep(4, t('adb_w4') || '重新点击安装', '回到文件列表，再次点击 APK 的「ADB安装」即可推送到手机。') +
        '<div class="adb-actions">' +
            '<button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button>' +
            '<button class="btn btn-save" onclick="adbRetry()">' + (t('adb_retry') || '重新安装') + '</button>' +
        '</div>' +
    '</div>';
}

function adbSetOs(os) {
    document.querySelectorAll('.adb-os').forEach(function (b) {
        b.classList.toggle('active', b.getAttribute('data-os') === os);
    });
    var el = document.getElementById('adbSteps');
    if (el) el.innerHTML = adbStepsHtml(os);
}

async function adbRescan() {
    setAdbModalBody('<div class="adb-loading"><div class="spinner"></div><div>' + (t('adb_scanning') || '正在扫描设备…') + '</div></div>');
    try {
        var r = await fetch('/api/adb/devices', { headers: getAuthHeaders() });
        var d = await r.json();
        if (!r.ok) {
            setAdbModalBody('<div class="adb-msg adb-err">' + escHtml(d.detail || (t('toast_failed') || '失败')) + '</div><div class="adb-actions"><button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button></div>');
            return;
        }
        if (d.adb_missing) { setAdbModalBody(adbGuideHtml(adbCurrentPath)); return; }
        var devs = d.devices || [];
        var ready = devs.filter(function (x) { return x.ready; });
        if (ready.length === 0) {
            var off = devs.filter(function (x) { return !x.ready; });
            var sub = off.length
                ? ('<br><span class="adb-sub">' + (off[0].state === 'unauthorized' ? (t('adb_unauthorized') || '设备未授权') : escHtml(off[0].state)) + '</span>')
                : '';
            setAdbModalBody(
                '<div class="adb-msg">' + escHtml(t('adb_no_device') || '未检测到设备') + sub + '</div>' +
                '<div class="adb-actions"><button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button></div>'
            );
            return;
        }
        if (ready.length === 1) { await adbDoInstall(adbCurrentPath, ready[0].serial); return; }
        setAdbModalBody(adbDevicePickerHtml(adbCurrentPath, devs));
    } catch (e) {
        setAdbModalBody('<div class="adb-msg adb-err">' + (t('net_error') || '网络错误') + '</div><div class="adb-actions"><button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button></div>');
    }
}

function adbDevicePickerHtml(path, devices) {
    var html = '<div class="adb-choose">' + (t('adb_choose') || '选择目标设备') + '</div>' +
        '<div class="adb-dev-list">';
    (devices || []).forEach(function (x) {
        if (!x.ready) return;
        var safePath = path.replace(/'/g, "\\'");
        var safeSerial = x.serial.replace(/'/g, "\\'");
        html += '<button class="adb-dev" onclick="adbDoInstall(\'' + safePath + '\',\'' + safeSerial + '\')">' +
            '<span class="adb-dev-name">' + (escHtml(x.model) || escHtml(x.serial)) + '</span>' +
            '<span class="adb-dev-sn">' + escHtml(x.serial) + '</span>' +
            '</button>';
    });
    html += '</div>';
    return html;
}

function adbDiagNothingVisible() {
    setAdbModalBody(
        '<div class="adb-msg adb-err">❌ WebUSB <b>完全看不到任何 USB 设备</b>。<br><br>' +
        '请按顺序排查：<br>' +
        '① 换一根<b>能传数据</b>的 USB 线（很多线只有充电功能）；<br>' +
        '② 手机 USB 连接模式选「传输文件 (MTP)」或「USB 调试」，而不要选「仅充电」；<br>' +
        '③ B 电脑上<b>结束其他 adb 进程</b>（任务管理器结束 adb.exe / 关闭 Android Studio 的 ADB），它们会独占 ADB 接口导致 WebUSB 看不见；<br>' +
        '④ Windows 上安装 Android 复合 ADB 驱动（Google USB Driver 或手机厂商驱动）；<br>' +
        '⑤ 换一个 USB 口，或重启手机后重新连接。</div>' +
        '<div class="adb-actions"><button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button></div>'
    );
}

async function adbDiagnosePick() {
    try {
        const dev = await navigator.usb.requestDevice({ filters: [] });
        if (dev) {
            const name = dev.productName || dev.manufacturerName || dev.serialNumber || '未知设备';
            setAdbModalBody(
                '<div class="adb-msg adb-ok">✅ 设备可见：<b>' + escHtml(name) + '</b><br><br>' +
                '但它在默认 ADB 过滤器下没被选中，说明它<b>没有暴露 ADB 接口</b>。<br>请确认：<br>' +
                '① 手机「开发者选项 → USB 调试」已开启；<br>' +
                '② 手机弹出「是否允许 USB 调试」时点了「允许」并勾选「一律允许」；<br>' +
                '③ 拔插一次 USB 线重新触发授权。<br><br>' +
                '若仍不行，多半是 B 电脑上<b>其他 adb（Android Studio / platform-tools 的 adb.exe）已占用接口</b>，请先结束它们再试。</div>' +
                '<div class="adb-actions"><button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button></div>'
            );
        } else {
            adbDiagNothingVisible();
        }
    } catch (e) {
        if (/notfound|no device|user cancelled/i.test((e && e.message) || '')) {
            adbDiagNothingVisible();
        } else {
            setAdbModalBody('<div class="adb-msg adb-err">' + escHtml((e && e.message) || String(e)) + '</div><div class="adb-actions"><button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button></div>');
        }
    }
}

async function adbDiagnose() {
    if (!window.isSecureContext) { openAdbModal(adbNeedHttpsHtml()); return; }
    if (!navigator.usb) { openAdbModal(adbNeedBrowserHtml()); return; }
    openAdbModal('<div class="adb-loading"><div class="spinner"></div><div>正在检测 WebUSB 与已连接设备…</div></div>');
    const lines = [];
    lines.push('• ' + (window.isSecureContext ? '✅ HTTPS 安全上下文正常（WebUSB 可用）' : '❌ 非安全上下文，WebUSB 被禁用'));
    lines.push('• ' + (navigator.usb ? '✅ 浏览器支持 WebUSB（Chrome / Edge）' : '❌ 浏览器不支持 WebUSB'));
    let paired = [];
    try { paired = await navigator.usb.getDevices(); } catch (_) {}
    if (paired.length) {
        lines.push('• ✅ 已配对过 ' + paired.length + ' 台设备：' + paired.map(d => d.productName || d.serialNumber || '未知').join('、'));
    } else {
        lines.push('• ⚠️ 尚无已配对设备（首次需弹窗授权）');
    }
    setAdbModalBody(
        '<div class="adb-msg"><div>' + lines.join('<br>') + '</div>' +
        '<div style="margin-top:10px">下一步将弹出「选择 USB 设备」窗口：<br>' +
        '— 若能看到你的手机 → 物理连接 OK，问题是<b>手机未开 USB 调试 / 未授权</b>；<br>' +
        '— 若列表为空 → WebUSB 完全看不到手机，问题在<b>线缆 / 驱动 / 被其他 adb 占用</b>。</div>' +
        '<div class="adb-actions">' +
            '<button class="btn btn-save" onclick="adbDiagnosePick()">弹出设备选择框（诊断）</button>' +
            '<button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button>' +
        '</div></div>'
    );
}

// ===== WiFi (网络 ADB) 配对面板 =====
function adbWifiRender(devices, msg) {
    var ip = window.__adbWifiIp || '';
    var listHtml = '';
    (devices || []).forEach(function (x) {
        if (!x.ready) {
            listHtml += '<div class="adb-dev adb-dev-off">' + escHtml(x.serial) + ' <span class="adb-sub">' + escHtml(x.state) + '</span></div>';
            return;
        }
        var p = (adbCurrentPath || '').replace(/'/g, "\\'");
        var s = x.serial.replace(/'/g, "\\'");
        listHtml += '<button class="adb-dev adb-dev-ok" onclick="adbDoInstall(\'' + p + '\',\'' + s + '\')">✅ '
            + escHtml(x.model || x.serial) + ' <span class="adb-sub">' + escHtml(x.serial) + '</span><br>点击安装</button>';
    });
    if (!listHtml) listHtml = '<div class="adb-sub">尚无已授权设备。连接成功后这里会出现设备。</div>';
    var body = '<div class="adb-wifi">'
        + '<div class="adb-wifi-title">📶 WiFi (网络 ADB) 配对</div>'
        + '<div class="adb-wifi-hint">手机开启「开发者选项 → 无线调试 / 网络 ADB」会显示 <b>IP:端口</b>（如 192.168.1.20:5555）。填到下面点「连接」，让<b>服务器</b>去连它（服务器需与该 IP 网络可达）。</div>'
        + '<div class="adb-wifi-row">'
        + '<input id="adbWifiIp" class="adb-input" placeholder="如 192.168.1.20:5555" value="' + escHtml(ip) + '">'
        + '<button class="btn btn-save" onclick="adbWifiConnect()">连接</button>'
        + '<button class="btn" onclick="adbWifiRescan()">刷新设备</button>'
        + '</div>'
        + (msg ? '<div class="adb-wifi-msg">' + msg + '</div>' : '')
        + '<div class="adb-wifi-list">' + listHtml + '</div>'
        + '<div class="adb-actions"><button class="btn" onclick="closeAdbModal()">关闭</button>'
        + (adbCurrentPath ? '<button class="btn" onclick="adbInstall(\'' + adbCurrentPath.replace(/'/g, "\\'") + '\')">改用 USB (WebUSB)</button>' : '')
        + '</div>'
        + '</div>';
    setAdbModalBody(body);
}

async function adbWifiConnect() {
    var inp = document.getElementById('adbWifiIp');
    if (!inp) return;
    var val = (inp.value || '').trim();
    if (!val) { adbWifiRender(null, '请填写手机 WiFi ADB 地址'); return; }
    if (!val.includes(':')) val = val + ':5555';
    window.__adbWifiIp = val;
    var host = val.split(':')[0];
    var port = parseInt(val.split(':')[1] || '5555', 10);
    adbWifiRender(null, '正在连接 ' + escHtml(val) + ' …');
    try {
        var r = await fetch('/api/adb/connect', {
            method: 'POST',
            headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
            body: JSON.stringify({ host: host, port: port }),
        });
        var d = await r.json();
        if (!r.ok) { adbWifiRender(d.devices || null, '❌ ' + escHtml(d.detail || '连接失败')); return; }
        var m = '✅ ' + escHtml((d.output || '已连接').toString().replace(/<[^>]+>/g, ''));
        if (d.adb_missing) m += '（但<b>服务器未装 adb</b>，请先在服务器安装 Android SDK Platform-Tools 或在 .env 设 ADB_PATH）';
        adbWifiRender(d.devices || [], m);
    } catch (e) {
        adbWifiRender(null, '❌ 网络错误');
    }
}

async function adbWifiRescan() {
    try {
        var r = await fetch('/api/adb/devices', { headers: getAuthHeaders() });
        var d = await r.json();
        if (!r.ok) { adbWifiRender(null, '❌ ' + escHtml(d.detail || '获取设备失败')); return; }
        if (d.adb_missing) { adbWifiRender([], '⚠️ <b>服务器未检测到 adb</b>：请先在服务器安装 Android SDK Platform-Tools 并加入 PATH，或在 .env 设 ADB_PATH。'); return; }
        adbWifiRender(d.devices || [], '');
    } catch (e) {
        adbWifiRender(null, '❌ 网络错误');
    }
}

function adbStart(path) {
    adbCurrentPath = path || null;
    openAdbModal('<div class="adb-loading"><div class="spinner"></div><div>正在连接服务器 ADB…</div></div>');
    adbWifiRescan();
}

async function adbInstall(path) {
    if (!canAdbInstall()) { toast(t('login_required') || '请先登录', true); return; }
    if (!window.isSecureContext) { openAdbModal(adbNeedHttpsHtml()); return; }
    if (!navigator.usb) { openAdbModal(adbNeedBrowserHtml()); return; }

    adbCurrentPath = path;
    openAdbModal('<div class="adb-loading"><div class="spinner"></div><div>' + (t('adb_connecting') || '正在连接设备（请在浏览器弹窗中选择手机并允许）…') + '</div></div>');
    try {
        var bundleUrl = '/static/js/webadb2.bundle.js?v=' + Date.now();
        var check = await fetch(bundleUrl, { method: 'HEAD', cache: 'no-store' });
        if (!check.ok) {
            throw new Error(
                (t('adb_lib_fail') || 'ADB 库文件未找到 (404)') + '\n' +
                (t('adb_lib_fail_hint') || '请先在服务器运行 "python download_webadb2.py"，然后完全重启服务器再试。')
            );
        }
        const mod = await import(bundleUrl);
        const Adb = mod.Adb;
        const AdbDaemonTransport = mod.AdbDaemonTransport;
        const DeviceManager = mod.AdbDaemonWebUsbDeviceManager;
        const AdbWebCredentialStore = mod.AdbWebCredentialStore;
        if (!Adb || !AdbDaemonTransport || !DeviceManager || !AdbWebCredentialStore) {
            throw new Error(t('adb_lib_fail') || 'ADB 库未加载：请先在服务器运行 python download_webadb2.py');
        }
        setAdbModalBody('<div class="adb-loading"><div class="spinner"></div><div>' + (t('adb_connecting') || '正在连接设备…') + '</div></div>');
        const manager = DeviceManager.BROWSER;
        if (!manager) throw new Error(t('adb_need_browser') || '当前浏览器不支持 WebUSB（请用 Chrome / Edge）。');
        const device = await manager.requestDevice();
        if (!device) { await adbDiagnose(); return; }
        const connection = await device.connect();
        const transport = await AdbDaemonTransport.authenticate({
            serial: device.serial,
            connection,
            credentialStore: new AdbWebCredentialStore(),
        });
        const adb = new Adb(transport);
        setAdbModalBody('<div class="adb-loading"><div class="spinner"></div><div>' + (t('adb_downloading') || '正在从服务器下载 APK…') + '</div></div>');
        const res = await fetch(downloadUrl(path));
        if (!res.ok) throw new Error((t('adb_dl_fail') || 'APK 下载失败') + '：' + res.status);
        const buf = await res.arrayBuffer();
        setAdbModalBody('<div class="adb-loading"><div class="spinner"></div><div>' + (t('adb_installing') || '正在安装到手机…') + '</div></div>');
        const fileName = Math.random().toString().substring(2);
        const filePath = '/data/local/tmp/' + fileName + '.apk';
        const sync = await adb.sync();
        try {
            const apkStream = new ReadableStream({
                start(controller) { controller.enqueue(new Uint8Array(buf)); controller.close(); }
            });
            await sync.write({ filename: filePath, file: apkStream });
        } finally {
            await sync.dispose();
        }
        let output = '';
        try {
            output = await adb.subprocess.noneProtocol.spawnWaitText(['pm', 'install', '-r', filePath]) || '';
        } finally {
            await adb.rm(filePath);
        }
        if (/Failure|error:/i.test(output)) {
            throw new Error((t('adb_install_fail') || '安装失败') + '：' + output.trim());
        }
        setAdbModalBody(
            '<div class="adb-result adb-ok"><div class="adb-icon">✓</div>' +
            '<div class="adb-result-title">' + (t('adb_success') || '安装成功') + '</div>' +
            '<div class="adb-actions"><button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button></div></div>'
        );
    } catch (e) {
        var msg = (e && e.message) ? e.message : String(e);
        if (/already in use|in used by another/i.test(msg)) {
            const guide = (t('adb_usb_busy') || '❌ WebUSB 无法占用该设备：它已被本机另一个程序（通常是本地 adb.exe 或系统 USB 驱动）占用。\n' +
                '你的手机是 WiFi 连接，请【不要选 WebUSB】，改用上方「📶 WiFi 配对」面板：\n' +
                '在面板填手机「无线调试」界面里的 IP:端口，点「连接」，由服务器经网络直接安装（不需要 USB 线）。');
            setAdbModalBody(
                '<div class="adb-msg adb-err">' + escHtml(guide).replace(/\n/g, '<br>') + '</div>' +
                '<div class="adb-actions">' +
                    '<button class="btn btn-save" onclick="adbWifiRescan()">📶 改用 WiFi 配对</button>' +
                    '<button class="btn" onclick="closeAdbModal()">关闭</button>' +
                '</div>'
            );
            return;
        }
        if (/user cancelled|notfound|not found|securityerror|no device/i.test(msg)) {
            msg = t('adb_usb_denied') || '未选择设备或已取消，请在浏览器弹窗中允许访问手机 USB 后重试。';
        }
        setAdbModalBody(
            '<div class="adb-msg adb-err">' + escHtml(msg).replace(/\n/g, '<br>') + '</div>' +
            '<div class="adb-actions">' +
                '<button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button>' +
                '<button class="btn btn-save" onclick="setAdbModalBody(adbGuideHtml(adbCurrentPath))">' + (t('adb_guide_btn') || '查看配置指引') + '</button>' +
                '<button class="btn" onclick="adbDiagnose()">🔍 设备自检</button>' +
            '</div>'
        );
    }
}

async function adbDoInstall(path, serial) {
    setAdbModalBody('<div class="adb-loading"><div class="spinner"></div><div>' + (t('adb_installing') || '正在安装…') + '</div></div>');
    try {
        var res = await fetch('/api/adb/install', {
            method: 'POST',
            headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeaders()),
            body: JSON.stringify({ path: path, serial: serial || null }),
        });
        var data = await res.json();
        if (!res.ok) {
            if (data && data.needs_serial) {
                setAdbModalBody(adbDevicePickerHtml(path, data.devices || []));
                return;
            }
            setAdbModalBody(
                '<div class="adb-msg adb-err">' + escHtml(data.detail || data.message || (t('toast_failed') || '失败')) + '</div>' +
                '<div class="adb-actions"><button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button></div>'
            );
            return;
        }
        var logHtml = data.output
            ? ('<div class="adb-output-title">' + (t('adb_output') || '安装日志') + '</div><pre class="adb-log">' + escHtml(data.output) + '</pre>')
            : '';
        if (data.ok) {
            setAdbModalBody(
                '<div class="adb-result adb-ok"><div class="adb-icon">✓</div>' +
                '<div class="adb-result-title">' + (t('adb_success') || '安装成功') + '</div>' + logHtml +
                '<div class="adb-actions"><button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button></div></div>'
            );
        } else {
            setAdbModalBody(
                '<div class="adb-result adb-fail"><div class="adb-icon">✕</div>' +
                '<div class="adb-result-title">' + (t('adb_fail') || '安装失败') + '</div>' + logHtml +
                '<div class="adb-actions"><button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button></div></div>'
            );
        }
    } catch (e) {
        setAdbModalBody(
            '<div class="adb-msg adb-err">' + (t('net_error') || '网络错误') + '</div>' +
            '<div class="adb-actions"><button class="btn" onclick="closeAdbModal()">' + (t('adb_close') || '关闭') + '</button></div>'
        );
    }
}

// ---- mount / unmount (SPA) ----
window.Views = window.Views || {};
window.Views.files = {
    mount: function (root) {
        dropZone = document.getElementById('dropZone');
        fileInput = document.getElementById('fileInput');
        fileList = document.getElementById('fileList');
        uploadHint = document.getElementById('uploadHint');
        if (dropZone) {
            dropZone.addEventListener('click', function () { if (fileInput) fileInput.click(); });
            if (fileInput) fileInput.addEventListener('change', function () { uploadFiles(fileInput.files); });
            ['dragenter', 'dragover'].forEach(function (e) {
                dropZone.addEventListener(e, function (ev) { ev.preventDefault(); dropZone.classList.add('dragover'); });
            });
            ['dragleave', 'drop'].forEach(function (e) {
                dropZone.addEventListener(e, function (ev) { ev.preventDefault(); dropZone.classList.remove('dragover'); });
            });
            dropZone.addEventListener('drop', function (ev) { uploadFiles(ev.dataTransfer.files); });
        }
        syncAccountFlags();
        showFilesView();
    },
    unmount: function () {
        var overlay = document.getElementById('uploadOverlay');
        if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }
};
