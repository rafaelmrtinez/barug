(function(){
'use strict';

function getCookie(name) {
    const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return v ? v.pop() : '';
}

function showAlert(container, msg, type='danger'){
    if(!container) return;
    container.innerHTML = `<div class="alert alert-${type} small" role="alert">${String(msg)}</div>`;
}

function clearAlert(container){ if(container) container.innerHTML = ''; }

function computeBmiStatus(weightKg, heightCm){
    if (!weightKg || !heightCm) return { id: 2, label: 'Unknown' };
    const h = Number(heightCm) / 100.0;
    if (!h || h <= 0) return { id: 2, label: 'Unknown' };
    const bmi = Number(weightKg) / (h * h);
    if (isNaN(bmi)) return { id: 2, label: 'Unknown' };
    if (bmi < 18.5) return { id: 1, label: 'Low' };
    if (bmi >= 25) return { id: 3, label: 'High' };
    return { id: 2, label: 'Normal' };
}

function disableEl(el){ if(!el) return; try{ el.disabled = true; }catch(_e){} }
function enableEl(el){ if(!el) return; try{ el.disabled = false; }catch(_e){} }

function init(){
    const modal = document.getElementById('createMaternalModal');
    if(!modal) return;
    const form = document.getElementById('createMaternalForm');
    const weightInput = document.getElementById('cm_weight');
    const heightInput = document.getElementById('cm_height');
    const statusSpan = document.getElementById('cm_bmi_status');
    const statusHidden = document.getElementById('cm_bmi_status_id');
    const personHidden = document.getElementById('cm_person_id');
    const alertContainer = document.getElementById('createMaternalAlert');

    // populate person id from page-level hidden input if available
    try{
        const pagePerson = document.getElementById('person_id');
        if(pagePerson && pagePerson.value) personHidden.value = pagePerson.value;
    }catch(_e){}

    function updateStatus(){
        const w = parseFloat(weightInput.value);
        const h = parseFloat(heightInput.value);
        const s = computeBmiStatus(w, h);
        statusHidden.value = s.id;
        statusSpan.textContent = s.label;
        statusSpan.className = 'badge ' + (s.id === 1 ? 'bg-warning' : (s.id === 3 ? 'bg-danger' : 'bg-success'));
    }

    weightInput && weightInput.addEventListener('input', updateStatus);
    heightInput && heightInput.addEventListener('input', updateStatus);

    form && form.addEventListener('submit', async function(evt){
        evt.preventDefault();
        clearAlert(alertContainer);

        const weight = weightInput && weightInput.value ? Number(weightInput.value) : null;
        const height = heightInput && heightInput.value ? Number(heightInput.value) : null;
        const bmiStatusId = statusHidden && statusHidden.value ? Number(statusHidden.value) : 2;
        const personId = personHidden && personHidden.value ? personHidden.value : (document.getElementById('person_id') ? document.getElementById('person_id').value : null);

        if (!weight || weight <= 0) { showAlert(alertContainer, 'Please enter a valid weight.'); return; }
        if (!height || height <= 0) { showAlert(alertContainer, 'Please enter a valid height.'); return; }
        if (!personId) { showAlert(alertContainer, 'Missing person id on page.'); return; }

        const saveBtn = document.getElementById('cm_save');
        disableEl(saveBtn);
        const csrfInput = form.querySelector('input[name="csrfmiddlewaretoken"]');
        const csrfToken = csrfInput ? csrfInput.value : getCookie('csrftoken');

        const payload = {
            weight: weight,
            height: height,
            is_transfered: false,
            bmi_status_id: bmiStatusId,
            person_id: personId,
        };

        try{
            const resp = await fetch('/maternal/api/v1/create-mhr/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {}),
                },
                credentials: 'same-origin',
                body: JSON.stringify(payload),
            });

            let data = null;
            try{ data = await resp.json(); } catch(_e){ data = null; }

            if (!resp.ok || (data && data.success === false)){
                const msg = (data && data.message) ? data.message : 'Failed to create maternal record.';
                showAlert(alertContainer, msg, 'danger');
                return;
            }

            // success: close modal and reload or show success
            try{
                const bsModal = bootstrap.Modal.getInstance(modal) || new bootstrap.Modal(modal);
                bsModal.hide();
            }catch(_e){}

            try{
                if (data && data.redirect) { globalThis.location.href = data.redirect; return; }
                globalThis.location.reload();
            }catch(_e){ /* ignore */ }

        }catch(err){
            console.error('create maternal entry error', err);
            showAlert(alertContainer, 'An unexpected error occurred while creating the maternal record.', 'danger');
        }finally{
            enableEl(saveBtn);
        }
    });

    // when modal shown, reset fields and set person id
    modal.addEventListener('shown.bs.modal', function(){
        clearAlert(alertContainer);
        try{ form.reset(); } catch(_e){}
        try{
            const pagePerson = document.getElementById('person_id');
            if(pagePerson && pagePerson.value) personHidden.value = pagePerson.value;
        }catch(_e){}
        statusHidden.value = 2;
        statusSpan.textContent = 'Unknown';
        statusSpan.className = 'badge bg-secondary';
    });
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();

})();
