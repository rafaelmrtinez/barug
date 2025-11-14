// JS to submit Risk Codes via AJAX to the RiskCodesAPI endpoint
(function(){
    function getCookie(name) {
        const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
        return v ? v.pop() : '';
    }

    // Unified toast helper: prefer global `CustomToast`, fallback to `alert`/`console`.
    function showToast(msg, success = true, opts = {}){
        try {
            if (globalThis.CustomToast && typeof globalThis.CustomToast.show === 'function') {
                // Map boolean success to a semantic type; allow opts.type override
                const type = opts.type || (success ? 'success' : 'error');
                const toastOpts = Object.assign({}, opts, { type });
                globalThis.CustomToast.show(String(msg == null ? '' : msg), toastOpts);
                return;
            }
        } catch (_e) {
            // If CustomToast throws, fall back to legacy behaviour below
        }

        // Legacy fallback when CustomToast isn't available or fails
        try { alert(String(msg)); } catch (_e) { try { console.log(String(msg)); } catch (_err) { /* ignore */ } }
    }

    document.addEventListener('DOMContentLoaded', function(){
        const form = document.getElementById('form-risk-code');
        if(!form) return;

        form.addEventListener('submit', async function(evt){
            evt.preventDefault();
            const mhrIdEl = document.getElementById('mhr-id');
            const mhrId = mhrIdEl ? mhrIdEl.value : (form.querySelector('[name="maternal_record_id"]') ? form.querySelector('[name="maternal_record_id"]').value : null);
            if(!mhrId){
                showToast('Missing maternal record id.', false);
                return;
            }

            // Prevent submission if server indicates existing risk codes
            const hasExisting = form.getAttribute('data-has-existing') === 'true';
            if (hasExisting){
                showToast('Risk codes already exist for this record and cannot be added.', false);
                return;
            }

            // gather selected risk-category data-risk-id attributes
            const checked = Array.from(form.querySelectorAll('.risk-category')).filter(i => i.checked);
            const categories = checked.map(i => {
                const v = i.getAttribute('data-risk-id');
                return v ? parseInt(v, 10) : null;
            }).filter(Boolean);

            // Require at least one selection before submitting
            if (!categories || categories.length === 0) {
                showToast('Please select at least one risk category.', false);
                return;
            }

            const payload = {
                maternal_record_id: parseInt(mhrId, 10),
                risk_categories: categories
            };

            const csrftoken = getCookie('csrftoken');
            const url = `/maternal/api/v1/mhr/risk-codes/`;
            const submitBtn = form.querySelector('button[type="submit"]');
            const origText = submitBtn ? submitBtn.innerHTML : null;
            if (submitBtn) submitBtn.disabled = true;
            if (submitBtn) submitBtn.innerHTML = '<span class="spinner-grow spinner-grow-sm" role="status" aria-hidden="true"></span> Saving...';

            try {
                const res = await fetch(url, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrftoken
                    },
                    body: JSON.stringify(payload)
                });

                const text = await res.text();
                let data = null;
                try { data = text ? JSON.parse(text) : null; } catch (_e) { data = text || null; }

                if (res.ok && data && data.success) {
                    showToast(data.message || 'Risk codes saved.');
                    return;
                }

                // Build error messages list from common response shapes
                const msgs = [];
                if (data) {
                    if (data.message) msgs.push(String(data.message));
                    if (data.error) msgs.push(String(data.error));

                    // errors may be an array of strings or objects, or an object mapping fields->messages
                    if (Array.isArray(data.errors)) {
                        data.errors.forEach(e => {
                            if (typeof e === 'string') msgs.push(e);
                            else if (typeof e === 'object' && e !== null) {
                                // flatten object entries
                                Object.keys(e).forEach(k => {
                                    const v = e[k];
                                    if (Array.isArray(v)) msgs.push(k + ': ' + v.join('; '));
                                    else msgs.push(k + ': ' + String(v));
                                });
                            }
                        });
                    } else if (typeof data.errors === 'object' && data.errors !== null) {
                        Object.keys(data.errors).forEach(k => {
                            const v = data.errors[k];
                            if (Array.isArray(v)) msgs.push(k + ': ' + v.join('; '));
                            else msgs.push(k + ': ' + String(v));
                        });
                    }
                }

                if (msgs.length === 0) {
                    // fallback to plain text response or generic message
                    if (typeof data === 'string' && data.length) msgs.push(data);
                    else msgs.push('Failed to save risk codes.');
                }

                // show each message via toast
                msgs.forEach(m => showToast(m, false));
            } catch (err) {
                try { console.error('Error saving risk codes', err); } catch (_e) { /* ignore logging failure */ }
                showToast('Unexpected server error.', false);
            } finally {
                if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = origText; }
            }
        });
    });
})();
