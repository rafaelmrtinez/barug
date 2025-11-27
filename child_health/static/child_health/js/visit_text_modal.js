/* Small helper to show findings/notes text in a modal when the ellipsis button is clicked
   - Looks for elements with class `visit-text-toggle` and reads `data-findings` or `data-notes`.
   - Uses Bootstrap's Modal if available, otherwise falls back to alert().
*/
(function(){
    'use strict';

    function showModal(title, content) {
        const label = document.getElementById('visitTextModalLabel');
        const body = document.getElementById('visitTextModalBody');
        if (label) label.textContent = title;
        if (body) {
            // keep plain text to avoid executing HTML
            body.textContent = content || '(no content)';
        }

        if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
            const modalEl = document.getElementById('visitTextModal');
            if (modalEl) {
                const modal = new bootstrap.Modal(modalEl);
                modal.show();
            } else {
                alert(content || '(no content)');
            }
        } else {
            alert(content || '(no content)');
        }
    }

    document.addEventListener('click', function (ev) {
        const btn = ev.target.closest && ev.target.closest('.visit-text-toggle');
        if (!btn) return;
        ev.preventDefault();
        const type = btn.dataset.type || 'notes';
        const id = btn.dataset.id || '';
        let content = '';
        if (type === 'findings') content = btn.dataset.findings || '';
        else content = btn.dataset.notes || '';
        const title = (type === 'findings' ? 'Findings' : 'Notes') + (id ? ` (Visit ${id})` : '');
        showModal(title, content);
    });

})();
