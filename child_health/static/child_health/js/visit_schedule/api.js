/* API and validation logic for visit schedule
   - performs full validation including 'other' purpose field
   - submits via fetch to a dummy URL
   - shows toast notifications using MHRToast
*/
(function () {
    'use strict';

    const DUMMY_URL = '/child-health/api/v1/chr/schedule/'; // replace with real URL when ready

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
        const other = form.querySelector('#visit_purpose_other') ? form.querySelector('#visit_purpose_other').value.trim() : '';
        const notes = form.querySelector('#visit_notes').value || '';

        if (!date) return { ok: false, msg: 'Please select a schedule date.' };
        if (!time) return { ok: false, msg: 'Please select a schedule time.' };
        if (!purpose) return { ok: false, msg: 'Please select a visit purpose.' };
        if (purpose === 'other' && !other) return { ok: false, msg: 'Please provide the other purpose.' };
        if (notes.length > 1000) return { ok: false, msg: 'Notes must be at most 1000 characters.' };

        // Prevent scheduling in the past
        const now = new Date();
        const scheduled = new Date(date + 'T' + time);
        if (scheduled < now) return { ok: false, msg: 'Schedule must be in the future.' };

        const payload = {
            schedule_date: date,
            schedule_time: time,
            visit_purpose: purpose,
            visit_purpose_other: other || null,
            visit_notes: notes
        };
        return { ok: true, payload };
    }

    function attachSubmission() {
        const modalEl = document.getElementById('visitScheduleModal');
        if (!modalEl) return;
        const form = modalEl.querySelector('#visitScheduleForm');
        if (!form) return;

        form.addEventListener('submit', function (ev) {
            ev.preventDefault();
            ev.stopPropagation();

            const validation = validate(form);
            if (!validation.ok) {
                form.classList.add('was-validated');
                showError(validation.msg);
                return;
            }

            const childId = form.querySelector('#visit_child_record_id').value;
            const body = Object.assign({ child_record_id: childId }, validation.payload);

            const submitBtn = form.querySelector('#visitScheduleSubmit');
            if (submitBtn) submitBtn.disabled = true;

            const headers = { 'Content-Type': 'application/json' };
            const csrftoken = getCookie('csrftoken');
            if (csrftoken) headers['X-CSRFToken'] = csrftoken;

            fetch(DUMMY_URL, {
                method: 'POST',
                headers: headers,
                credentials: 'same-origin',
                body: JSON.stringify(body)
            }).then(async (resp) => {
                if (resp.ok) {
                    showSuccess('Visit scheduled successfully (dummy).');
                    // clear inputs
                    form.reset();
                    try { const bm = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl); bm.hide(); } catch (e) { console.warn(e); }
                } else {
                    let msg = 'Failed to schedule visit.';
                    try { const data = await resp.json(); if (data && data.message) msg = data.message; } catch (_e) { /* ignore */ }
                    showError(msg);
                }
            }).catch((err) => {
                showError('Network error while scheduling visit.');
                console.error(err);
            }).finally(() => {
                if (submitBtn) submitBtn.disabled = false;
            });
        });
    }

    function init() {
        try { attachSubmission(); } catch (e) { console.error('visit schedule api init', e); }
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();

})();
