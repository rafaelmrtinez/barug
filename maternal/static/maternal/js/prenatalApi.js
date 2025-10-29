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

        // collect form fields by name
        const payload = {};
        for (const el of form.elements) {
            if (!el.name) continue;
            // skip CSRF token in payload (we send it in header)
            if (el.name === 'csrfmiddlewaretoken') continue;
            if (el.type === 'checkbox') {
                payload[el.name] = el.checked;
            } else if (el.type === 'radio') {
                if (el.checked) payload[el.name] = el.value;
            } else {
                payload[el.name] = el.value;
            }
        }

        if (mhrId) payload.mhr_id = mhrId;

        // CSRF token
        const csrfInput = form.querySelector('input[name="csrfmiddlewaretoken"]');
        const csrfToken = csrfInput ? csrfInput.value : null;

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

                const data = await resp.json();
                if (!resp.ok || !data.success) {
                    // Prefer detailed errors when returned by the server
                    let msg = data && data.message ? data.message : 'Failed to save prenatal data.';
                    if (data && data.errors && typeof data.errors === 'object') {
                        // data.errors is expected to be a mapping field -> [errors]
                        const parts = [];
                                for (const [field, errs] of Object.entries(data.errors)) {
                                    try {
                                        const joined = Array.isArray(errs) ? errs.join('; ') : String(errs);
                                        parts.push(`${joined}`);
                                    } catch (_e) {
                                        parts.push(`${String(errs)}`);
                                    }
                                }
                        if (parts.length) msg = parts.join('\n');
                    }

                    // simple feedback; project may prefer a toast/message utility
                    alert(msg);
                    return;
                }

            // success: either redirect if server suggests, or reload
            if (data.redirect) {
                    globalThis.location.href = data.redirect;
                return;
            }
            // fallback: reload to show updated list
                globalThis.location.reload();
        } catch (err) {
            console.error('prenatalApi error', err);
            alert('An unexpected error occurred while saving prenatal data.');
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
