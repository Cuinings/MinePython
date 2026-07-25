// =====================================================================
//  File Server — shared modal infrastructure (P0)
//  - confirmModal / promptModal : 主题统一的异步弹窗（替代原生
//    confirm()/prompt()，消除线程阻塞与样式割裂）
//  - showModal / hideModal     : 统一处理 ESC 关闭、焦点陷阱、
//    body 滚动锁定、aria-modal 与焦点归还
//  Classic script: symbols stay on global scope.
// =====================================================================
(function () {
    'use strict';

    function focusable(el) {
        return el.querySelectorAll(
            'a[href],button:not([disabled]),input:not([disabled]),' +
            'select:not([disabled]),textarea:not([disabled]),' +
            '[tabindex]:not([tabindex="-1"])'
        );
    }

    function showModal(id) {
        var el = document.getElementById(id);
        if (!el) return;
        if (!el.__lastFocus && document.activeElement) el.__lastFocus = document.activeElement;
        el.classList.add('show');
        el.setAttribute('role', 'dialog');
        el.setAttribute('aria-modal', 'true');
        document.body.classList.add('modal-open');
        var f = focusable(el);
        if (f.length) {
            try { f[0].focus(); } catch (e) {}
        }
    }

    function hideModal(id) {
        var el = document.getElementById(id);
        if (!el) return;
        el.classList.remove('show');
        el.removeAttribute('role');
        el.removeAttribute('aria-modal');
        document.body.classList.remove('modal-open');
        if (el.__lastFocus && el.__lastFocus.focus) {
            try { el.__lastFocus.focus(); } catch (e) {}
            el.__lastFocus = null;
        }
    }

    // 全局 ESC 关闭 + 焦点陷阱（仅作用于带 data-close 的真实模态；
    // confirm/prompt 自带 data-self-managed，由各自的监听器处理）。
    document.addEventListener('keydown', function (e) {
        var open = document.querySelector('.modal-overlay.show');
        if (!open) return;
        if (open.getAttribute('data-self-managed')) return;

        if (e.key === 'Escape' || e.key === 'Esc') {
            e.preventDefault();
            var fn = open.getAttribute('data-close');
            if (fn && typeof window[fn] === 'function') window[fn]();
            else open.classList.remove('show');
            return;
        }
        if (e.key === 'Tab') {
            var f = focusable(open);
            if (!f.length) return;
            var first = f[0], last = f[f.length - 1];
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault(); last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault(); first.focus();
            } else if (!open.contains(document.activeElement)) {
                e.preventDefault(); first.focus();
            }
        }
    });

    // 点击遮罩关闭（仅对带 data-close 的真实模态生效）
    document.addEventListener('click', function (e) {
        var m = e.target;
        if (m && m.classList && m.classList.contains('modal-overlay') && m.getAttribute('data-close')) {
            var fn = m.getAttribute('data-close');
            if (typeof window[fn] === 'function') window[fn]();
        }
    });

    window.showModal = showModal;
    window.hideModal = hideModal;

    // -----------------------------------------------------------------
    //  confirmModal({ title, message, okText, cancelText, danger })
    //  返回 Promise<boolean>
    // -----------------------------------------------------------------
    function ensureModalHost() {
        var host = document.getElementById('modalHost');
        if (!host) {
            host = document.createElement('div');
            host.id = 'modalHost';
            document.body.appendChild(host);
        }
        return host;
    }

    function confirmModal(opts) {
        opts = opts || {};
        return new Promise(function (resolve) {
            var host = ensureModalHost();
            var overlay = document.createElement('div');
            overlay.className = 'modal-overlay show confirm-modal';
            overlay.setAttribute('role', 'dialog');
            overlay.setAttribute('aria-modal', 'true');
            overlay.setAttribute('data-self-managed', '1');

            var danger = opts.danger ? ' btn-danger' : '';
            var okText = opts.okText || (typeof t === 'function' ? t('btn_confirm') : '') || '确定';
            var cancelText = opts.cancelText || (typeof t === 'function' ? t('btn_cancel') : '') || '取消';
            var title = opts.title ? '<h2>' + escHtml(opts.title) + '</h2>' : '';
            var msg = opts.message ? '<div class="confirm-msg">' + opts.message + '</div>' : '';

            overlay.innerHTML =
                '<div class="modal-card">' + title + msg +
                '<div class="modal-actions">' +
                    '<button class="btn btn-cancel" data-role="cancel">' + escHtml(cancelText) + '</button>' +
                    '<button class="btn btn-save' + danger + '" data-role="ok">' + escHtml(okText) + '</button>' +
                '</div></div>';

            document.body.classList.add('modal-open');
            host.appendChild(overlay);
            var lastFocus = document.activeElement;
            var okBtn = overlay.querySelector('[data-role="ok"]');

            function cleanup(result) {
                if (!overlay.parentNode) return;
                overlay.remove();
                document.body.classList.remove('modal-open');
                if (lastFocus && lastFocus.focus) { try { lastFocus.focus(); } catch (e) {} }
                resolve(result);
            }

            overlay.addEventListener('click', function (e) {
                if (e.target === overlay) { cleanup(false); return; }
                var r = e.target.getAttribute && e.target.getAttribute('data-role');
                if (r === 'ok') cleanup(true);
                else if (r === 'cancel') cleanup(false);
            });

            if (okBtn) okBtn.focus();
        });
    }

    // -----------------------------------------------------------------
    //  promptModal({ title, label, value, okText, cancelText })
    //  返回 Promise<string|null>
    // -----------------------------------------------------------------
    function promptModal(opts) {
        opts = opts || {};
        return new Promise(function (resolve) {
            var host = ensureModalHost();
            var overlay = document.createElement('div');
            overlay.className = 'modal-overlay show prompt-modal';
            overlay.setAttribute('role', 'dialog');
            overlay.setAttribute('aria-modal', 'true');
            overlay.setAttribute('data-self-managed', '1');

            var okText = opts.okText || (typeof t === 'function' ? t('btn_save') : '') || '确定';
            var cancelText = opts.cancelText || (typeof t === 'function' ? t('btn_cancel') : '') || '取消';
            var title = opts.title ? '<h2>' + escHtml(opts.title) + '</h2>' : '';
            var lbl = opts.label ? '<label>' + escHtml(opts.label) + '</label>' : '';
            var val = opts.value || '';

            overlay.innerHTML =
                '<div class="modal-card">' + title + lbl +
                '<input type="text" class="prompt-input" value="' + escHtml(val) + '">' +
                '<div class="modal-actions">' +
                    '<button class="btn btn-cancel" data-role="cancel">' + escHtml(cancelText) + '</button>' +
                    '<button class="btn btn-save" data-role="ok">' + escHtml(okText) + '</button>' +
                '</div></div>';

            document.body.classList.add('modal-open');
            host.appendChild(overlay);
            var lastFocus = document.activeElement;
            var input = overlay.querySelector('.prompt-input');

            function cleanup(result) {
                if (!overlay.parentNode) return;
                overlay.remove();
                document.body.classList.remove('modal-open');
                if (lastFocus && lastFocus.focus) { try { lastFocus.focus(); } catch (e) {} }
                resolve(result);
            }

            overlay.addEventListener('click', function (e) {
                if (e.target === overlay) { cleanup(null); return; }
                var r = e.target.getAttribute && e.target.getAttribute('data-role');
                if (r === 'cancel') cleanup(null);
                else if (r === 'ok') cleanup(input.value.trim());
            });
            input.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') { e.preventDefault(); cleanup(input.value.trim()); }
                else if (e.key === 'Escape' || e.key === 'Esc') { e.preventDefault(); cleanup(null); }
            });
            input.focus();
            input.select();
        });
    }

    window.confirmModal = confirmModal;
    window.promptModal = promptModal;
})();
