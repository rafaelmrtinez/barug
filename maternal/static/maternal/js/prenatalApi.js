// JS: prenatalApi.js
// Uses fetch with async/await and try/catch to POST prenatal form data to
// /maternal/api/form/prenatal/ as JSON. Expects a JSON response { success: bool, message: str }

(function () {
    'use strict';

    async function postPrenatalForm(event) {
        event.preventDefault();
        const form = event.currentTarget;
        const endpoint = '/maternal/api/v1/form/prenatal/';
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

        // Normalize common prefixed keys like `pf_entry-findings` => `findings`.
        // This ensures client-side role-based filtering sees canonical names
        // when Django formsets/templates render inputs with prefixes.
        (function normalizePrefixedKeys() {
            const normalized = {};
            for (const key of Object.keys(payload)) {
                // look for <prefix>-<name> pattern and normalize to <name>
                const idx = String(key).indexOf('-');
                if (idx > 0) {
                    const bare = key.slice(idx + 1);
                    if (bare && payload[bare] === undefined) {
                        normalized[bare] = payload[key];
                    }
                }
            }
            if (Object.keys(normalized).length) Object.assign(payload, normalized);
        })();

        // Determine role (may be set on the form as data-role by template)
        const role = (form.dataset.role || '').toString().trim().toLowerCase();

        // If a midwife is submitting, send only the ANC id (as `id`), the
        // maternal record id (`mhr_id`) and `findings` (and `notes` if available)
        // per policy. Also attempt to extract the most recent notes from the
        // follow-up log's view-entry buttons (these render notes into
        // `data-content`) if `notes` is not present in the form payload.
        if (role === 'midwife') {
            // attempt to populate notes from the follow-up log modal/button
            try {
                if (!payload.notes) {
                    const notesBtn = document.querySelector('#prenatal-followup-log .view-entry[data-title="Notes"]');
                    if (notesBtn && notesBtn.dataset && notesBtn.dataset.content) {
                        payload.notes = notesBtn.dataset.content;
                    }
                }
            } catch (_e) { /* ignore DOM scraping errors */ }

            const filtered = {};
            // maternal health record id
            if (mhrId) filtered.mhr_id = mhrId;
            // prefer anc_row_id, fall back to id if present
            const ancId = (payload.anc_row_id !== undefined && payload.anc_row_id !== '') ? payload.anc_row_id : (payload.id !== undefined ? payload.id : undefined);
            if (ancId !== undefined) filtered.id = ancId;
            // prefer canonical names (service expects 'findings' and 'notes')
            if (payload['pf_entry-findings'] !== undefined) filtered.findings = payload['pf_entry-findings'];
            if (payload.notes !== undefined) filtered.notes = payload.notes;

            // replace payload with the filtered one
            Object.keys(payload).forEach(k => delete payload[k]);
            Object.assign(payload, filtered);
        }

        // Prefer the actual button that triggered the submit (event.submitter)
        // Fallback to the first submit button in the form for older browsers.
        const submitBtn = (event && event.submitter) ? event.submitter : (form.querySelector('button[type="submit"]') || null);

        // Collect all related buttons (submit + reset) to disable during preflight.
        const buttons = Array.from(form.querySelectorAll('button[type="submit"], button[type="reset"], input[type="submit"], input[type="reset"]'));
        // Save original state so we can restore later
        const origStates = buttons.map(b => ({ el: b, disabled: b.disabled, tag: b.tagName.toLowerCase(), html: b.tagName.toLowerCase() === 'button' ? b.innerHTML : b.value }));

        // Set spinner/text on the clicked submit button and disable all
        if (submitBtn && submitBtn.tagName && submitBtn.tagName.toLowerCase() === 'button') {
            submitBtn.innerHTML = '<span class="spinner-grow spinner-grow-sm" role="status" aria-hidden="true"></span> Saving...';
        } else if (submitBtn && submitBtn.tagName && submitBtn.tagName.toLowerCase() !== 'button') {
            // input[type=submit]
            try { submitBtn.value = 'Saving...'; } catch (_e) { /* ignore */ }
        }
        buttons.forEach(b => { try { b.disabled = true; } catch (__) { /* ignore */ } });

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
            // Restore original button states/text
            try {
                for (const s of origStates) {
                    try { s.el.disabled = !!s.disabled; } catch (_) { /* ignore */ }
                    try {
                        if (s.tag === 'button') s.el.innerHTML = s.html;
                        else s.el.value = s.html;
                    } catch (_) { /* ignore */ }
                }
            } catch (__) { /* ignore */ }
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
