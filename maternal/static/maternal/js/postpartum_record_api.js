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
        if (s === null || s === undefined) return '';
        let t = String(s).trim();
        if (t.length > maxLen) t = t.slice(0, maxLen);
        // basic remove of angle brackets
        return t.replace(/[<>]/g, '');
    }

    function showResultModal(message, isSuccess = false) {
        // Prefer the reusable toast helper
        try {
            if (globalThis.MHRToast && typeof globalThis.MHRToast.show === 'function') {
                globalThis.MHRToast.show(message, Boolean(isSuccess));
                return;
            }
        } catch (_err) {
            // ignore and fallback
        }

        // Final fallback: simple alert so user always gets feedback
        try {
            // eslint-disable-next-line no-alert
            alert((isSuccess ? 'Success: ' : 'Error: ') + String(message));
        } catch (_err) {
            try { console.warn('Postpartum API response:', message); } catch (_e) { /* ignore */ }
        }
    }

    async function handleSubmit(e) {
        e.preventDefault();
        const form = e.target || e.currentTarget;

        const submitBtn = form ? form.querySelector("button[type='submit']") : null;
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.classList.add('disabled');
        }

        // gather inputs by name
        const getVal = (name) => form.querySelector(`[name="${name}"]`);

        const maternal_record_id = sanitizeString(getVal('maternal_record_id')?.value || '');
        const date_of_delivery = sanitizeString(getVal('date_of_delivery')?.value || '');
        const time_of_delivery = sanitizeString(getVal('time_of_delivery')?.value || '');
        const attended_by_id = sanitizeString(getVal('attended_by_id')?.value || '');
        const place_of_delivery_id = sanitizeString(getVal('place_of_delivery_id')?.value || '');
        const outcome = sanitizeString(getVal('outcome')?.value || '', 200);
        const iron_supplementation = !!getVal('iron_supplementation')?.checked;
        const vit_a_supplementation = !!getVal('vit_a_supplementation')?.checked;
        const mebendazole_given = !!getVal('mebendazole_given')?.checked;
        const lochial_discharges_baseline = sanitizeString(getVal('lochial_discharges_baseline')?.value || '', 500);
        const pads_per_day_baseline = sanitizeString(getVal('pads_per_day_baseline')?.value || '');

        // basic front-end validation
        if (!maternal_record_id || Number.isNaN(Number(maternal_record_id))) {
            showResultModal('Invalid maternal record id.', false);
            if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
            return;
        }
        if (!date_of_delivery) {
            showResultModal('Please provide date of delivery.', false);
            if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
            return;
        }
        if (!time_of_delivery) {
            showResultModal('Please provide time of delivery.', false);
            if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
            return;
        }

        const payload = {
            maternal_record_id: Number(maternal_record_id),
            date_of_delivery,
            time_of_delivery,
            attended_by_id: attended_by_id || undefined,
            place_of_delivery_id: place_of_delivery_id || undefined,
            outcome: outcome || undefined,
            iron_supplementation,
            vit_a_supplementation,
            mebendazole_given,
            lochial_discharges_baseline: lochial_discharges_baseline || undefined,
            pads_per_day_baseline: pads_per_day_baseline !== '' ? Number(pads_per_day_baseline) : undefined,
        };

        const csrftoken = getCookie('csrftoken');

        try {
            const resp = await fetch('/maternal/api/v1/mhr/postpartum-record/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrftoken || ''
                },
                credentials: 'same-origin',
                body: JSON.stringify(payload)
            });

            let data = null;
            try {
                data = await resp.json();
            } catch (_err) {
                // ignore non-json
            }

            if (!resp.ok) {
                const msg = (data && data.message) ? data.message : `Server returned ${resp.status}`;
                showResultModal(msg, false);
                if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
                return;
            }

            const successMsg = (data && data.message) ? data.message : 'Postpartum record saved.';

            // hide the posting modal if open
            try {
                const modalEl = document.getElementById('postpartumRecordModal');
                if (globalThis.bootstrap && modalEl) {
                    const inst = globalThis.bootstrap.Modal.getInstance(modalEl) || new globalThis.bootstrap.Modal(modalEl);
                    inst.hide();
                }
            } catch (_err) {
                // ignore
            }

            showResultModal(successMsg, true);

            // dispatch an event so other parts of the app can react
            try {
                const ev = new CustomEvent('postpartum:created', { detail: data && data.result ? data.result : null });
                document.dispatchEvent(ev);
            } catch (_err) {
                // ignore
            }

            if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
            return;
        } catch (err) {
            console.error('Network or unexpected error', err);
            showResultModal('Unexpected network error while saving postpartum record.', false);
            if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
            return;
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        const form = document.getElementById('postpartumRecordForm');
        if (form) form.addEventListener('submit', handleSubmit);
    });

})();
