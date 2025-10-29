(function(){

    // Attach submit handlers to each laboratory test form (forms that include
    // a hidden input `form_type=laboratory_form`). Uses async/await + try/catch
    // (no .then()) as requested.

    function getCsrfToken() {
        return document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || '';
    }

    function getRecordIdFromPath() {
        // Expect path like /maternal/anc/form/<record_id>/ or similar
        const m = window.location.pathname.match(/anc\/form\/(\d+)/);
        return m ? m[1] : null;
    }

    const recordId = getRecordIdFromPath();
    if (!recordId) return; // nothing to do if we can't determine record id

    const csrfToken = getCsrfToken();

    // Find all forms that are intended for laboratory_form
    const labForms = Array.from(document.querySelectorAll('form')).filter(f => {
        const el = f.querySelector('input[name="form_type"][value="laboratory_form"]');
        return !!el;
    });

    labForms.forEach(form => {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const submitBtn = form.querySelector('button[type="submit"]');
            const originalText = submitBtn?.innerText;
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerText = 'Saving...';
            }

            try {
                const fd = new FormData(form);

                // Build endpoint URL using the record id
                const url = `/maternal/anc/form/${recordId}/lab/save/`;

                const res = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': csrfToken
                        // Note: when sending FormData do not set Content-Type; browser
                        // will set multipart/form-data with proper boundary.
                    },
                    body: fd
                });

                // Attempt to parse JSON response (API returns JSON)
                let data = null;
                try {
                    data = await res.json();
                } catch (parseErr) {
                    throw new Error('Invalid JSON response from server');
                }

                if (!res.ok || !data) {
                    const msg = (data && (data.message || data.errors)) || 'Failed to save laboratory data.';
                    // Format errors object if present
                    if (data && data.errors && typeof data.errors === 'object') {
                        const errmsg = Object.entries(data.errors).map(([k,v]) => {
                            if (Array.isArray(v)) return v.join(', ');
                            return String(v);
                        }).join('\n');
                        alert(errmsg || msg);
                    } else {
                        alert(msg);
                    }
                    return;
                }

                if (data.success) {
                    alert(data.message || 'Laboratory data saved successfully.');
                    // reload to reflect saved data
                    window.location.reload();
                } else {
                    const msg = data.message || JSON.stringify(data);
                    alert(msg);
                }

            } catch (err) {
                console.error('Error saving lab results', err);
                alert(err.message || 'An unexpected error occurred while saving laboratory data.');
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerText = originalText;
                }
            }
        });
    });

})();
