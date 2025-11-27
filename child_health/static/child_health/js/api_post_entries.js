/* Child Health: submit section forms to new API endpoints using fetch + async/await
   - Uses CustomToast.show(message, { type: 'success'|'error' }) for notifications
   - Avoids .catch() promise chains; uses try/catch
   - Derives app prefix from current pathname so endpoints work when app is included under a prefix
*/
(function(){
    'use strict';

    // Helper: read cookie for CSRF token
    function getCookie(name) {
        const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
        return v ? v.pop() : '';
    }

    const csrftoken = getCookie('csrftoken');

    // Use a fixed application prefix for API calls
    // All API URLs will be under `/child-health/v{API_VERSION}/...`
    const PREFIX = '/child-health';
    const API_VERSION = 1; // keep in sync with child_health/urls.py

    function apiUrl(childId, slug) {
        // slug examples: 'newborn-screening/', 'bf-feeding/', 'visit/', 'birth-supplementation/', 'iron-intake/', 'vitamin/'
        const s = String(slug || '').replace(/^\/*/, '');
        return `${PREFIX}/api/v${API_VERSION}/chr/entry/${childId}/${s}`;
    }

    // Extract textual message; ignore numeric-only nested messages like [[62]]
    function _extractMessageText(body) {
        if (body == null) return null;
        if (typeof body === 'string') return body;
        if (!body.message) return null;
        const msg = body.message;
        if (typeof msg === 'string') return msg;
        if (Array.isArray(msg)) {
            const flat = msg.flat(Infinity);
            const texts = flat.filter(el => typeof el === 'string');
            if (texts.length) return texts.join(' ');
            return null; // numeric-only -> ignore
        }
        return null;
    }

    async function postJson(url, payload) {
        try {
            const res = await fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrftoken,
                    'Accept': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            let data = {};
            try { data = await res.json(); } catch (_) { data = {}; }
            if (res.ok) {
                const text = _extractMessageText(data) || 'Saved.';
                CustomToast && CustomToast.show && CustomToast.show(text, { type: 'success' });
            } else {
                const msg = data.error || data.message || 'Failed to save.';
                CustomToast && CustomToast.show && CustomToast.show(msg, { type: 'error' });
            }
            return { ok: res.ok, status: res.status, body: data };
        } catch (err) {
            console.error('postJson error', err);
            CustomToast && CustomToast.show && CustomToast.show('Network error. Please try again.', { type: 'error' });
            return { ok: false, status: 0, body: null };
        }
    }

    // Builders: normalize dates to YYYY-MM-DD and pick only relevant fields
    function normalizeDate(val) {
        if (!val) return null;
        if (/^\d{4}-\d{2}-\d{2}$/.test(val)) return val;
        const d = new Date(val);
        if (isNaN(d.getTime())) return val;
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        return `${yyyy}-${mm}-${dd}`;
    }

    // Helper: find the most recent visit row in the visits table and return
    // its numeric id, findings and notes if present. Returns an object
    // { id: Number, findings: String|null, notes: String|null } or null.
    function getLatestVisitRowData() {
        try {
            const rows = document.querySelectorAll('#visits-table tbody tr');
            let max = null;
            let chosen = null;
            rows.forEach(row => {
                const firstCell = row.querySelector('td');
                if (!firstCell) return;
                const txt = (firstCell.textContent || '').trim();
                if (!txt) return;
                if (txt === '—') return;
                const n = parseInt(txt.replace(/[^0-9]/g, ''), 10);
                if (!isNaN(n)) {
                    if (max === null || n > max) {
                        max = n;
                        const tds = row.querySelectorAll('td');
                        const findings = tds[6] ? (tds[6].textContent || '').trim() : null;
                        const notes = tds[7] ? (tds[7].textContent || '').trim() : null;
                        chosen = { id: n, findings: findings || null, notes: notes || null };
                    }
                }
            });
            return chosen;
        } catch (e) {
            console.warn('getLatestVisitRowData failed', e);
            return null;
        }
    }

    function newbornBuilder(form) {
        return {
            type_of_feeding: (form.querySelector('[name="type_of_feeding"]') || {}).value || null,
            referred_for_newborn_screening: (form.querySelector('[name="referred_for_newborn_screening"]') || {}).value || null
        };
    }

    function bfBuilder(form) {
        const data = {};
        const inputs = form.querySelectorAll('[name^="exclusive_bf_check_"]');
        let lastNonEmpty = null;
        inputs.forEach((el) => {
            const v = (el.value || '').trim();
            data[el.name] = v || null;
            if (v) lastNonEmpty = v;
        });
        data['exclusive_bf_check_last'] = lastNonEmpty;
        return data;
    }

    function visitBuilder(form) {
        const get = (n) => (form.querySelector(`[name="${n}"]`) || {}).value || null;
        const payload = {
            date: normalizeDate(get('date')),
            age: get('age'),
            weight: get('weight'),
            temperature: get('temp') || get('temperature') || null,
            height: get('height'),
            findings: get('findings'),
            notes: get('notes')
        };


        // If the current user is a midwife, include the id of the most recent visit
        // and prefer the findings/notes from that latest row when present.
        try {
            const role = (typeof globalThis !== 'undefined' && globalThis.__USER_ROLE) ? String(globalThis.__USER_ROLE).toLowerCase() : null;
            if (role === 'midwife') {
                const latest = getLatestVisitRowData();
                if (latest && latest.id) {
                    payload.child_monitoring_id = latest.id;
                    // Prefer findings/notes from the visits table row if available
                    if (latest.findings) payload.findings = latest.findings;
                    if (latest.notes) payload.notes = latest.notes;
                }
            }
        } catch (e) {
            // non-fatal: if DOM access fails, proceed without id/overrides
            console.warn('visitBuilder: could not determine latest visit row data', e);
        }

        return payload;
    }

    function birthSuppBuilder(form) {
        const get = (n) => (form.querySelector(`[name="${n}"]`) || {}).value || null;
        return {
            data_assessed: normalizeDate(get('data_assessed')),
            birth_weight: get('birth_weight'),
            tt_status_mother: get('tt_status_mother'),
            anemia_2_59_seen: get('anemia_2_59_seen'),
            anemia_2_59_given_iron: get('anemia_2_59_given_iron'),
            birth_wt_seen: get('birth_wt_seen'),
            birth_wt_given_iron: get('birth_wt_given_iron'),
            low_birth_weight: get('low_birth_weight')
        };
    }

    function ironBuilder(form) {
        const get = (n) => (form.querySelector(`[name="${n}"]`) || {}).value || null;
        return {
            date_iron_started: normalizeDate(get('date_iron_started')),
            date_iron_completed: normalizeDate(get('date_iron_completed'))
        };
    }

    function vitaminBuilder(form) {
        const data = {};
        const inputs = form.querySelectorAll('[name^="vit_a"]');
        inputs.forEach((el) => {
            // If the input is a checkbox, use the checked state instead of the value
            if (el.type === 'checkbox') {
                data[el.name] = el.checked ? true : null;
            } else {
                data[el.name] = el.value || null;
            }
        });
        const stageEl = form.querySelector('[name="vit_a_stage"]');
        if (stageEl) data['vit_a_stage'] = stageEl.value || null;
        return data;
    }

    // Generic form submit handler with loading state
    function bindForm(selector, buildPayload, endpointSlug) {
        const form = document.querySelector(selector);
        if (!form) return;
        form.addEventListener('submit', async function (ev) {
            ev.preventDefault();
            const childIdEl = document.getElementById('child_health_record_id');
            const childId = childIdEl ? childIdEl.value : null;
            if (!childId) {
                CustomToast && CustomToast.show && CustomToast.show('Missing child id', { type: 'error' });
                return;
            }
            const payload = buildPayload(form);
            // Build API URL for this form
            const url = apiUrl(childId, endpointSlug);

            // If builder returned an object that expects child id, set it
            if (payload && Object.prototype.hasOwnProperty.call(payload, 'child_health_record_id')) {
                payload.child_health_record_id = childId;
            }

            // No special-case validations here; builders should return relevant fields only.

            // Disable submit buttons and mark section busy
            const submitButtons = Array.from(form.querySelectorAll('button[type="submit"], input[type="submit"]'));
            submitButtons.forEach(btn => {
                btn.disabled = true;
                btn.dataset._origText = btn.innerHTML;
                // use same spinner style as maternal (`mhr_form_submit.js`) for UI consistency
                btn.innerHTML = '<span class="spinner-grow spinner-grow-sm" role="status" aria-hidden="true"></span> Saving...';
            });
            form.setAttribute('aria-busy', 'true');

            try {
                const result = await postJson(url, payload);
                // If save succeeded, behave like `mhr_form_submit.js`: honor redirect or reload page
                if (result && result.ok) {
                    try {
                        if (result.body && result.body.redirect) {
                            globalThis.location.href = result.body.redirect;
                        } else {
                            globalThis.location.reload();
                        }
                    } catch (_e) {
                        try { globalThis.location.reload(); } catch (_) { /* swallow */ }
                    }
                }
            } finally {
                submitButtons.forEach(btn => {
                    btn.disabled = false;
                    if (btn.dataset._origText) btn.innerHTML = btn.dataset._origText;
                    delete btn.dataset._origText;
                });
                form.removeAttribute('aria-busy');
            }
        });
    }

    // Bind known forms on the page with specific builders
    bindForm('#nbs form, #nbs > form', newbornBuilder, 'newborn-screening/');
    bindForm('#breastFeedingForm', bfBuilder, 'bf-feeding/');
    bindForm('#visit-entry form', visitBuilder, 'visit/');
    bindForm('#birth-and-supplementation form', birthSuppBuilder, 'birth-supplementation/');
    bindForm('#iron-intake form', ironBuilder, 'iron-intake/');
    bindForm('#vitamin-intake form', vitaminBuilder, 'vitamin/');

    // Expose for debugging
    globalThis.ChildHealthApi = { postJson, apiUrl };

    // Button-disable feature removed per request. Previously implemented section/row completeness checks
    // and automatic disabling of header/row save buttons; removed to restore manual control.
})();
