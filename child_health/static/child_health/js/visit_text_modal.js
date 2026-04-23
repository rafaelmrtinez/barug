/* visit_text_modal.js
   Shows full Findings/Notes in a Bootstrap modal when a .visit-text-toggle button is clicked.
   - Buttons must include `data-type` ('findings'|'notes'), `data-id` and `data-findings`/`data-notes`.
   - Modal element expected in template with ids: #visitTextModal, #visitTextModalLabel, #visitTextModalBody
*/
(function () {
    'use strict';

    function showModal(title, content) {
        const label = document.getElementById('visitTextModalLabel');
        const body = document.getElementById('visitTextModalBody');
        if (label) label.textContent = title;
        if (body) {
            // use textContent to preserve original text and avoid executing HTML
            body.textContent = content || '(no content)';
        }

        const modalEl = document.getElementById('visitTextModal');
        if (!modalEl) {
            // fallback: alert
            alert(content || '(no content)');
            return;
        }

        // Use Bootstrap Modal if available
        try {
            if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
                let inst = bootstrap.Modal.getInstance(modalEl);
                if (!inst) inst = new bootstrap.Modal(modalEl);
                inst.show();
                return;
            }
        } catch (err) {
            // ignore and fallback to alert below
            console.warn('bootstrap modal show failed', err);
        }

        alert(content || '(no content)');
    }

    // Delegate click handler for .visit-text-toggle buttons
    document.addEventListener('click', function (ev) {
        const btn = ev.target && ev.target.closest && ev.target.closest('.visit-text-toggle');
        if (!btn) return;
        ev.preventDefault();

        const type = (btn.dataset && btn.dataset.type) ? String(btn.dataset.type) : 'notes';
        const id = (btn.dataset && btn.dataset.id) ? String(btn.dataset.id) : '';
        let content = '';
        if (type === 'findings') content = (btn.dataset && btn.dataset.findings) ? btn.dataset.findings : '';
        else content = (btn.dataset && btn.dataset.notes) ? btn.dataset.notes : '';

        const title = (type === 'findings' ? 'Findings' : 'Notes') + (id ? ` (Visit ${id})` : '');

        // store metadata on modal for other scripts (optional)
        const modalEl = document.getElementById('visitTextModal');
        if (modalEl) {
            try {
                modalEl.dataset.lastType = type;
                modalEl.dataset.lastId = id;
                modalEl.dataset.lastContent = content || '';
            } catch (_e) {
                // ignore
            }
        }

        showModal(title, content);
    });

})();
