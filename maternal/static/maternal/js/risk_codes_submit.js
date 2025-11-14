// JS to submit Risk Codes via AJAX to the RiskCodesAPI endpoint
(function(){
    function getCookie(name) {
        const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
        return v ? v.pop() : '';
    }

    function showToast(msg, success=true){
        if (globalThis && globalThis.MHRToast && typeof globalThis.MHRToast.show === 'function'){
            globalThis.MHRToast.show(msg, !!success);
        } else {
            alert(msg);
        }
    }

    document.addEventListener('DOMContentLoaded', function(){
        const form = document.getElementById('form-risk-code');
        if(!form) return;

        form.addEventListener('submit', function(evt){
            evt.preventDefault();
            const mhrIdEl = document.getElementById('mhr-id');
            const mhrId = mhrIdEl ? mhrIdEl.value : (form.querySelector('[name="maternal_record_id"]') ? form.querySelector('[name="maternal_record_id"]').value : null);
            if(!mhrId){
                showToast('Missing maternal record id.', false);
                return;
            }

            // gather selected risk-category data-risk-id attributes
            const checked = Array.from(form.querySelectorAll('.risk-category')).filter(i => i.checked);
            const categories = checked.map(i => {
                const v = i.getAttribute('data-risk-id');
                return v ? parseInt(v, 10) : null;
            }).filter(Boolean);

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

            fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrftoken
                },
                body: JSON.stringify(payload)
            }).then(res => res.json()).then(data => {
                if(data && data.success){
                    showToast(data.message || 'Risk codes saved.')
                    // optional: clear checkboxes
                    form.querySelectorAll('.risk-category').forEach(i => i.checked = false);
                } else {
                    const msg = data && (data.message || (data.errors && JSON.stringify(data.errors))) || 'Failed to save risk codes.';
                    showToast(msg, false);
                }
            }).catch(err => {
                console.error('Error saving risk codes', err);
                showToast('Unexpected server error.', false);
            }).finally(()=>{
                if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = origText; }
            });
        });
    });
})();
