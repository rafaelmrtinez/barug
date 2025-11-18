// Extracted from health_record_form.html inline script
// Handles the Back-to-top button behaviour for the maternal page
document.addEventListener('DOMContentLoaded', function(){
    const btn = document.getElementById('maternal-back-to-top');
    if(!btn) return;
    function onScroll(){
        if(window.scrollY > 200) btn.classList.add('visible'); else btn.classList.remove('visible');
    }
    window.addEventListener('scroll', onScroll, {passive:true});
    btn.addEventListener('click', function(){ window.scrollTo({top:0, behavior:'smooth'}); });
    onScroll();
});

// --- Disable save buttons based on existing data rules for various forms ---
(function() {
    'use strict';

    function isValuePresent(el) {
        if (!el) return false;
        if (el.type === 'hidden') return false;
        if (el.type === 'checkbox' || el.type === 'radio') return el.checked;
        if (el.tagName === 'SELECT') return (el.value || '').toString().trim() !== '';
        if (el.type === 'file') return false; // file inputs don't indicate saved state here
        return (el.value || '').toString().trim() !== '';
    }

    function anyFieldFilled(form) {
        if (!form) return false;
        for (const el of Array.from(form.elements)) {
            if (!el.name) continue;
            if (el.name === 'csrfmiddlewaretoken' || el.name === 'form_type') continue;
            if (isValuePresent(el)) return true;
        }
        return false;
    }

    function allFieldsFilled(form, predicates) {
        if (!form) return false;
        const els = Array.from(form.elements).filter(e => e.name && e.name !== 'csrfmiddlewaretoken' && e.name !== 'form_type');
        if (predicates && typeof predicates === 'function') return predicates(els);
        // default: require every element to have a value (ignores file inputs)
        for (const el of els) {
            if (el.type === 'file') continue;
            if (!isValuePresent(el)) return false;
        }
        return els.length > 0;
    }

    function disableButtonForForm(form, condition) {
        if (!form) return;
        const btn = form.querySelector('button[type="submit"]');
        if (!btn) return;
        try {
            btn.disabled = !!condition;
        } catch (e) { /* ignore */ }
    }

    // Wait till DOM ready
    document.addEventListener('DOMContentLoaded', function(){
        try {
            // 1. Obstetric - disable once already filled (any field present)
            const obstForm = document.getElementById('form-obstetric');
            disableButtonForForm(obstForm, anyFieldFilled(obstForm));

            // 2. Medical History - disable once already filled
            const medForm = document.getElementById('form-medhist');
            disableButtonForForm(medForm, anyFieldFilled(medForm));

            // 3. Tetanus Toxoid - disable only when ALL fields are filled
            const ttForm = document.getElementById('form-tt');
            disableButtonForForm(ttForm, allFieldsFilled(ttForm));

            // 4. Present Pregnancy - disable once already filled
            const presentForm = document.getElementById('form-present');
            disableButtonForForm(presentForm, anyFieldFilled(presentForm));

            // 5. Laboratory Results - disable only when a specific field is already filled
            const labForms = Array.from(document.querySelectorAll('form')).filter(f => {
                const ft = f.querySelector('input[name="form_type"][value="laboratory_form"]');
                return !!ft;
            });
            labForms.forEach(f => {
                const primary = Array.from(f.elements).find(el => el.name && el.name !== 'csrfmiddlewaretoken' && el.type !== 'file' && el.type !== 'hidden');
                const shouldDisable = primary ? isValuePresent(primary) : false;
                disableButtonForForm(f, shouldDisable);
            });

            // 6. Checklist - disable only when all fields are filled or server indicated populated alert exists
            const checklistForm = document.getElementById('form-checklist');
            let checklistPopulated = false;
            const checklistAlert = document.querySelector('#checklist .alert.alert-secondary');
            if (checklistAlert) checklistPopulated = true;
            disableButtonForForm(checklistForm, checklistPopulated || allFieldsFilled(checklistForm));

            // 7. Plans - disable when fields are filled (any field)
            const plansForm = document.getElementById('form-plans');
            disableButtonForForm(plansForm, anyFieldFilled(plansForm));

            // 8. Micronutrients - disable only when ALL fields are filled
            const microsForm = document.getElementById('form-micros');
            disableButtonForForm(microsForm, allFieldsFilled(microsForm));
        } catch (err) {
            console.error('Error in health form auto-disable init', err);
        }
    });
})();
