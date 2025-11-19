// JS: prenatalApi.js
// Uses fetch with async/await and try/catch to POST prenatal form data to
// /maternal/api/form/prenatal/ as JSON. Expects a JSON response { success: bool, message: str }

(function () {
    'use strict';

    async function postPrenatalForm(event) {
        event.preventDefault();
        const form = event.currentTarget;
        const endpoint = form.dataset.apiEndpoint || '/maternal/api/form/prenatal/';
        const mhrId = form.dataset.mhrId || null;
        // helper: get CSRF from hidden input or cookie
        function getCookie(name) {
            const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
            return v ? v.pop() : '';
        }

        function showToast(msg, success = true) {
            try {
                if (globalThis.CustomToast && typeof globalThis.CustomToast.show === 'function') {
                    return globalThis.CustomToast.show(String(msg || ''), { type: success ? 'success' : 'error' });
                }
            } catch (__) { /* ignore toast adapter errors */ }
            try { alert(String(msg)); } catch (__) { try { console.log(msg); } catch(__2) { /* ignore logging errors */ } }
        }

        // collect form fields by name, handling checkbox groups as arrays
        const payload = {};
        for (const el of form.elements) {
            if (!el.name) continue;
            if (el.name === 'csrfmiddlewaretoken') continue;

            if (el.type === 'checkbox') {
                const group = form.querySelectorAll(`input[name="${el.name}"][type="checkbox"]`);
                if (group && group.length > 1) {
                    if (!payload[el.name]) payload[el.name] = [];
                    if (el.checked) payload[el.name].push(el.value);
                } else {
                    payload[el.name] = el.checked;
                }
            } else if (el.type === 'radio') {
                if (el.checked) payload[el.name] = el.value;
            } else {
                payload[el.name] = el.value;
            }
        }

        if (mhrId) payload.mhr_id = mhrId;

        const submitBtn = form.querySelector('button[type="submit"]');
        const origText = submitBtn ? submitBtn.innerHTML : null;
        if (submitBtn) { submitBtn.disabled = true; submitBtn.innerHTML = '<span class="spinner-grow spinner-grow-sm" role="status" aria-hidden="true"></span> Saving...'; }

        const csrfInput = form.querySelector('input[name="csrfmiddlewaretoken"]');
        const csrfToken = csrfInput ? csrfInput.value : getCookie('csrftoken');

        try {
            const resp = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {}),
                },
                body: JSON.stringify(payload),
                credentials: 'same-origin',
            });

            let data = null;
            try { data = await resp.json(); } catch (_) { data = null; }

            if (!resp.ok || (data && data.success === false)) {
                // Prefer the first validation error message when available
                let singleMsg = 'Failed to save prenatal data.';
                if (data) {
                    if (data.errors && typeof data.errors === 'object') {
                        try {
                            const firstField = Object.keys(data.errors)[0];
                            const v = data.errors[firstField];
                            if (Array.isArray(v) && v.length > 0) singleMsg = String(v[0]);
                            else if (v) singleMsg = String(v);
                        } catch (_e) {
                            if (data.message) singleMsg = String(data.message);
                        }
                    } else if (data.message) {
                        singleMsg = String(data.message);
                    }
                }
                showToast(singleMsg, false);
                return;
            }

            showToast((data && data.message) ? data.message : 'Saved.');
            if (data && data.redirect) { globalThis.location.href = data.redirect; return; }
            globalThis.location.reload();
        } catch (err) {
            console.error('prenatalApi error', err);
            showToast('An unexpected error occurred while saving prenatal data.', false);
        } finally {
            if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = origText; }
        }
    }

    function init() {
        const form = document.getElementById('prenatal-form');
        if (!form) return;
        form.addEventListener('submit', postPrenatalForm);
    }

    // init on DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
