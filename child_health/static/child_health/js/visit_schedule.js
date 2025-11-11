/* Front-end for Visit Schedule modal
   - Validates fields
   - Sends POST to a dummy URL using fetch
   - Uses MHRToast.show for user notifications
*/
(function () {
    'use strict';

    const DUMMY_URL = '/dummy/visit_schedule'; // placeholder - replace with real endpoint

    function getCookie(name) {
        const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
        return v ? v.pop() : '';
    }

    function showError(msg) {
        try { globalThis.MHRToast.show(msg, false); } catch (_e) { alert(msg); }
    }

    function showSuccess(msg) {
        try { globalThis.MHRToast.show(msg, true); } catch (_e) { alert(msg); }
    }

    function validate(form) {
        const date = form.querySelector('#schedule_date').value;
        const time = form.querySelector('#schedule_time').value;
        const purpose = form.querySelector('#visit_purpose').value;
        const notes = form.querySelector('#visit_notes').value || '';

        if (!date) return { ok: false, msg: 'Please select a schedule date.' };
        if (!time) return { ok: false, msg: 'Please select a schedule time.' };
        if (!purpose) return { ok: false, msg: 'Please select a visit purpose.' };
        if (notes.length > 1000) return { ok: false, msg: 'Notes must be at most 1000 characters.' };

        // Additional business rule: don't allow past dates
        const now = new Date();
        const scheduled = new Date(date + 'T' + time);
        if (scheduled < now) return { ok: false, msg: 'Schedule must be in the future.' };

        return { ok: true, payload: { schedule_date: date, schedule_time: time, visit_purpose: purpose, visit_notes: notes } };
    }

    function attachModalHandlers() {
        const modalEl = document.getElementById('visitScheduleModal');
        if (!modalEl) return;

        modalEl.addEventListener('show.bs.modal', function (ev) {
            try {
                const trigger = ev.relatedTarget;
                const childId = trigger && trigger.getAttribute('data-child-id');
                const hidden = modalEl.querySelector('#visit_child_record_id');
                if (hidden) hidden.value = childId || '';

                // reset form validation state
                const form = modalEl.querySelector('#visitScheduleForm');
                if (form) form.classList.remove('was-validated');
            } catch (_e) { console.warn('visitScheduleModal show handler error', _e); }
        });

        const form = modalEl.querySelector('#visitScheduleForm');
        if (!form) return;

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            e.stopPropagation();

            const v = validate(form);
            if (!v.ok) {
                form.classList.add('was-validated');
                showError(v.msg);
                return;
            }

            const childId = form.querySelector('#visit_child_record_id').value;
            const payload = Object.assign({ child_record_id: childId }, v.payload);

            // Show busy state
            const submitBtn = form.querySelector('#visitScheduleSubmit');
            if (submitBtn) submitBtn.disabled = true;

            const headers = { 'Content-Type': 'application/json' };
            const csrftoken = getCookie('csrftoken');
            if (csrftoken) headers['X-CSRFToken'] = csrftoken;

            // Send to dummy URL for now
            fetch(DUMMY_URL, {
                method: 'POST',
                headers: headers,
                body: JSON.stringify(payload),
                credentials: 'same-origin'
            }).then(async (resp) => {
                // For now any 2xx considered success
                if (resp.ok) {
                    showSuccess('Visit scheduled successfully (dummy).');
                    // close modal
                    try {
                        const bm = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
                        bm.hide();
                    } catch (_err) { console.warn('failed to hide modal', _err); }
                } else {
                    let text = 'Failed to schedule visit.';
                    try {
                        const data = await resp.json();
                        if (data && data.message) text = data.message;
                    } catch (_e) { /* ignore invalid JSON response */ }
                    showError(text);
                }
            }).catch((err) => {
                showError('Network error while scheduling visit.');
                console.error(err);
            }).finally(() => {
                if (submitBtn) submitBtn.disabled = false;
            });
        });
    }

    // Initialize on DOM ready
    function init() {
        try {
            attachModalHandlers();
        } catch (e) { console.error('visit_schedule init error', e); }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
