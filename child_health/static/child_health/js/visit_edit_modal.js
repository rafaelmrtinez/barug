/* visit_edit_modal.js
   Adds a midwife-only edit flow for visit findings.
   - Buttons: .visit-edit-btn must have data-id and optional data-findings
   - Modal expected in template with ids: #visitEditModal, #visitEditModalLabel, #visitEditModalTextarea
*/
(function () {
    'use strict';

    function showEditModal(monitorId, findings) {
        const label = document.getElementById('visitEditModalLabel');
        const ta = document.getElementById('visitEditModalTextarea');
        const modalEl = document.getElementById('visitEditModal');
        if (label) label.textContent = `Edit Findings (Visit ${monitorId})`;
        if (ta) ta.value = findings || '';
        if (!modalEl) {
            alert('Edit findings:\n' + (findings || ''));
            return;
        }
        try {
            let inst = bootstrap.Modal.getInstance(modalEl);
            if (!inst) inst = new bootstrap.Modal(modalEl);
            modalEl.dataset.currentId = String(monitorId);
            inst.show();
        } catch (e) {
            console.warn('visitEditModal show failed', e);
            alert('Edit findings:\n' + (findings || ''));
        }
    }

    // Delegate click for edit buttons
    document.addEventListener('click', function (ev) {
        const btn = ev.target && ev.target.closest && ev.target.closest('.visit-edit-btn');
        if (!btn) return;
        ev.preventDefault();
        const id = btn.dataset && btn.dataset.id ? btn.dataset.id : '';
        const findings = btn.dataset && btn.dataset.findings ? btn.dataset.findings : '';
        showEditModal(id, findings);
    });

    // Save handler
    document.addEventListener('click', async function (ev) {
        const btn = ev.target && ev.target.closest && ev.target.closest('#visitEditModalSave');
        if (!btn) return;
        ev.preventDefault();

        const modalEl = document.getElementById('visitEditModal');
        const ta = document.getElementById('visitEditModalTextarea');
        if (!modalEl || !ta) return;
        const monitorId = modalEl.dataset.currentId;
        const childIdEl = document.getElementById('child_health_record_id');
        const childId = childIdEl ? childIdEl.value : null;
        if (!childId) {
            CustomToast && CustomToast.show && CustomToast.show('Missing child id', { type: 'error' });
            return;
        }

        const payload = {
            child_monitoring_id: monitorId,
            findings: ta.value || null
        };

        // Build API URL using exposed helper
        const url = (typeof ChildHealthApi !== 'undefined' && ChildHealthApi.apiUrl) ? ChildHealthApi.apiUrl(childId, 'visit/') : (`/child-health/api/v1/chr/entry/${childId}/visit/`);

        try {
            btn.disabled = true;
            btn.dataset.orig = btn.innerHTML;
            btn.innerHTML = 'Saving...';
            const result = await (typeof ChildHealthApi !== 'undefined' && ChildHealthApi.postJson ? ChildHealthApi.postJson(url, payload) : fetch(url, { method: 'POST', credentials: 'same-origin', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)}));
            // If result is a fetch Response wrapper from postJson, it returns {ok,...}
            const ok = result && (result.ok === true || (result.status && result.status >= 200 && result.status < 300));
            if (ok) {
                try { window.location.reload(); } catch (_e) { /* ignore */ }
            }
        } catch (e) {
            console.error('visitEditModal save failed', e);
            CustomToast && CustomToast.show && CustomToast.show('Failed to save findings', { type: 'error' });
        } finally {
            try {
                if (btn.dataset.orig) btn.innerHTML = btn.dataset.orig;
                btn.disabled = false;
                delete btn.dataset.orig;
            } catch (_e) {}
            try { let inst = bootstrap.Modal.getInstance(modalEl); if (inst) inst.hide(); } catch (_e) {}
        }
    });

})();
