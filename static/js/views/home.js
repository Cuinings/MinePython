// Home view (module entries). Markup lives in <template id="tpl-home"> in
// index.html; this file only wires the audit-card visibility per role.
(function () {
    window.Views = window.Views || {};
    window.Views.home = {
        mount: function (root) {
            // showApp() (auth.js) tried to set this before the view existed;
            // set it now that the home grid is in the DOM.
            var card = document.getElementById('homeAuditCard');
            var role = window.authRole || '';
            if (card) card.style.display = (role && role !== 'anonymous') ? '' : 'none';
        },
        unmount: function () {}
    };
})();
