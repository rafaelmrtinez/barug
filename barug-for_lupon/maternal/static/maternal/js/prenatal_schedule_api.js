/* Intercept prenatal schedule form submission, validate/sanitize, send JSON to API
   Uses async/await + try/catch; uses confirm() for user feedback and returns nothing. */

(function () {
    'use strict';

    function getCookie(name) {
        const cookies = document.cookie ? document.cookie.split('; ') : [];
        for (let i = 0; i < cookies.length; i++) {
            const parts = cookies[i].split('=');
            const key = parts.shift();
            const value = parts.join('=');
            if (key === name) return decodeURIComponent(value);
        }
        return null;
    }

    function sanitizeString(s, maxLen = 1000) {
        if (!s && s !== '') return '';
        let t = String(s).trim();
        if (t.length > maxLen) t = t.slice(0, maxLen);
        return t;
    }

    function showToast(message, isSuccess = false) {
        // Delegate to reusable MHRToast helper if available
        try {
            if (globalThis.MHRToast && typeof globalThis.MHRToast.show === 'function') {
                globalThis.MHRToast.show(message, isSuccess);
                return;
            }
        } catch (_err) {
            // ignore and fallback
        }

        // Fallback: simple alert-like behavior
        try {
            // eslint-disable-next-line no-alert
            alert((isSuccess ? 'Success: ' : 'Error: ') + String(message));
        } catch (_err) {
            try { console.warn('Toast fallback:', message); } catch (_e) { /* ignore */ }
        }
    }

    async function handleSubmit(e) {
        e.preventDefault();
        const form = e.target || e.currentTarget;
        // disable submit to prevent double submits; we'll re-enable via helper
        const submitBtn = form ? form.querySelector("button[type='submit']") : null;
        if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
            globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, true);
        } else if (submitBtn) {
            // fallback
            submitBtn.disabled = true;
            submitBtn.classList.add('disabled');
        }

        const mhrIdEl = document.getElementById('sched_maternal_record_id');
        const dateEl = document.getElementById('sched_date');
        const timeEl = document.getElementById('sched_time');
        const purposeEl = document.getElementById('sched_purpose');
        const notesEl = document.getElementById('sched_notes');

        const mhrId = sanitizeString(mhrIdEl?.value || '');
        const schedule_date = sanitizeString(dateEl?.value || '');
        const schedule_time = sanitizeString(timeEl?.value || '');
        const purpose = sanitizeString(purposeEl?.value || '', 500);
        const notes = sanitizeString(notesEl?.value || '', 1000);

        // Basic front-end validation
        if (!mhrId || Number.isNaN(Number(mhrId))) {
            showToast('Invalid maternal record id.', false);
            if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
                globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
            } else if (submitBtn) {
                submitBtn.disabled = false; submitBtn.classList.remove('disabled');
            }
            return;
        }
        if (!schedule_date) {
            showToast('Please choose a schedule date.', false);
            if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
                globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
            } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
            return;
        }
        if (!schedule_time) {
            showToast('Please choose a schedule time.', false);
            if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
                globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
            } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
            return;
        }
        if (!purpose) {
            showToast('Please provide a purpose for the visit.', false);
            if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
                globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
            } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
            return;
        }

        // Same-day time validation: if schedule_date === today, ensure schedule_time >= now
        try {
            const now = new Date();
            const selDate = new Date(schedule_date + 'T' + schedule_time);
            if (selDate.toDateString() === now.toDateString() && selDate < now) {
                showToast('Cannot schedule a visit for a time in the past today.', false);
                if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
                    globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
                } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
                return;
            }
        } catch (_err) {
            // ignore parse errors and let server validate
        }

        const payload = {
            mhr_id: Number(mhrId),
            schedule_date,
            schedule_time,
            purpose,
            notes,
        };

        const csrftoken = getCookie('csrftoken');

        try {
            const resp = await fetch('/maternal/api/v1/mhr/schedule/prenatal/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrftoken || ''
                },
                body: JSON.stringify(payload),
                credentials: 'same-origin'
            });

            let data = null;
            try {
                data = await resp.json();
            } catch (_err) {
                // Non-JSON response
            }

            if (!resp.ok) {
                const msg = (data && data.message) ? data.message : `Server returned ${resp.status}`;
                showToast(`Failed to save prenatal schedule: ${msg}`, false);
                if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
                    globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
                } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
                return;
            }

            const successMsg = (data && data.message) ? data.message : 'Prenatal schedule saved.';

            // ensure we clear loading UI before closing modal
            if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
                try { globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false); } catch (_e) { /* ignore */ }
            } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }

            // close modal if bootstrap available
            try {
                const modalEl = document.getElementById('prenatalScheduleModal');
                if (globalThis.bootstrap && modalEl) {
                    const inst = globalThis.bootstrap.Modal.getInstance(modalEl) || new globalThis.bootstrap.Modal(modalEl);
                    inst.hide();
                }
            } catch (_err) {
                // ignore
            }

            showToast(successMsg, true);
            return;
        } catch (err) {
            console.error('Network or unexpected error', err);
            showToast('Unexpected network error while saving prenatal schedule.', false);
            if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
                globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
            } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
            return;
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        const form = document.getElementById('prenatalScheduleForm');
        if (form) form.addEventListener('submit', handleSubmit);
        // set min date to today to prevent selecting past dates (greys out previous dates)
        try {
            const dateEl = document.getElementById('sched_date');
            if (dateEl) {
                const today = new Date();
                const yyyy = today.getFullYear();
                const mm = String(today.getMonth() + 1).padStart(2, '0');
                const dd = String(today.getDate()).padStart(2, '0');
                dateEl.setAttribute('min', `${yyyy}-${mm}-${dd}`);
            }
        } catch (_err) {
            // ignore
        }
    });

})();
