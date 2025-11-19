// Centralized form submit handler for maternal health record forms.
// Intercepts form submits and sends them as JSON to dedicated API endpoints
// added during the API migration. Uses CSRF token from cookie or hidden input.
(function(){
    'use strict';

    function getCookie(name) {
        const v = document.cookie.match('(^|;)\s*' + name + '\s*=\s*([^;]+)');
        return v ? v.pop() : '';
    }

    function showToast(msg, success = true) {
        try {
            if (globalThis.CustomToast && typeof globalThis.CustomToast.show === 'function') {
                return globalThis.CustomToast.show(String(msg || ''), { type: success ? 'success' : 'error' });
            }
        } catch (_) {}
        try { alert(String(msg)); } catch (_) { try { console.log(msg); } catch(_){} }
    }

    async function submitFormTo(url, form) {
        const submitBtn = form.querySelector('button[type="submit"]');
        const origText = submitBtn ? submitBtn.innerHTML : null;
        if (submitBtn) { submitBtn.disabled = true; submitBtn.innerHTML = '<span class="spinner-grow spinner-grow-sm" role="status" aria-hidden="true"></span> Saving...'; }

        // collect form data
        const payload = {};
        for (const el of form.elements) {
            if (!el.name) continue;
            if (el.name === 'csrfmiddlewaretoken') continue;

            if (el.type === 'checkbox') {
                // If multiple checkboxes share the same name (a checkbox group),
                // collect the values of checked boxes into an array. For lone
                // checkboxes (single boolean flags) keep the boolean checked value.
                const group = form.querySelectorAll(`input[name="${el.name}"][type="checkbox"]`);
                if (group && group.length > 1) {
                    if (!payload[el.name]) payload[el.name] = [];
                    if (el.checked) payload[el.name].push(el.value);
                } else {
                    payload[el.name] = el.checked;
                }
            } else if (el.type === 'radio') { if (el.checked) payload[el.name] = el.value; }
            else payload[el.name] = el.value;
        }

        // ensure mhr id present
        const mhrEl = document.getElementById('mhr-id');
        if (mhrEl && mhrEl.value) payload.mhr_id = mhrEl.value;

        const csrftoken = getCookie('csrftoken') || (form.querySelector('input[name="csrfmiddlewaretoken"]') ? form.querySelector('input[name="csrfmiddlewaretoken"]').value : null);

        try {
            const resp = await fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                headers: Object.assign({ 'Content-Type': 'application/json' }, csrftoken ? { 'X-CSRFToken': csrftoken } : {}),
                body: JSON.stringify(payload)
            });

            let data = null;
            try { data = resp.status === 204 ? { success: true } : await resp.json(); } catch (_) { data = null; }

            if (!resp.ok || (data && data.success === false)) {
                // Show only a single, user-friendly error toast.
                let singleMsg = 'Failed to save.';
                if (data) {
                    // Prefer the first validation error message when available
                    if (data.errors && typeof data.errors === 'object') {
                        try {
                            const firstField = Object.keys(data.errors)[0];
                            const v = data.errors[firstField];
                            if (Array.isArray(v) && v.length > 0) singleMsg = String(v[0]);
                            else if (v) singleMsg = String(v);
                        } catch (e) {
                            // fallback to message
                            if (data.message) singleMsg = String(data.message);
                        }
                    } else if (data.message) {
                        singleMsg = String(data.message);
                    }
                }
                showToast(singleMsg, false);
                return false;
            }

            showToast((data && data.message) ? data.message : 'Saved.');
            // server may ask for redirect
            if (data && data.redirect) { globalThis.location.href = data.redirect; return true; }
            // otherwise reload to show changes
            globalThis.location.reload();
            return true;
        } catch (err) {
            console.error('submitFormTo error', err);
            showToast('Unexpected error while saving.', false);
            return false;
        } finally {
            if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = origText; }
        }
    }

    function attach(id, url) {
        const form = document.getElementById(id);
        if (!form) return;
        form.addEventListener('submit', function(evt){
            evt.preventDefault();
            submitFormTo(url, form);
        });
    }

    function init() {
        // API endpoints (must match urls.py)
        const base = '/maternal';
        attach('form-obstetric', `${base}/api/v1/mhr/obstetric/`);
        attach('form-medhist', `${base}/api/v1/mhr/medical-history/`);
        attach('form-prev-preg-entry', `${base}/api/v1/mhr/previous-pregnancy/`);
        attach('form-tt', `${base}/api/v1/mhr/tetanus-toxoid/`);
        attach('form-present', `${base}/api/v1/mhr/present-pregnancy/`);
        attach('form-checklist', `${base}/api/v1/mhr/checklist/`);
        attach('form-plans', `${base}/api/v1/mhr/plans/`);
        attach('form-micros', `${base}/api/v1/mhr/micronutrients/`);
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
