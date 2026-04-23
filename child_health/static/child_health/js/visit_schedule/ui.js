/* UI-only behaviors for visit schedule modal
   - toggles the 'other' input when purpose === 'other'
   - sets hidden child_record_id value when modal opens
   - keeps validation UI state in sync
*/
(function () {
    'use strict';

    function onPurposeChange(ev) {
        const select = ev.target;
        const wrapper = document.getElementById('visit_purpose_other_wrapper');
        const otherInput = document.getElementById('visit_purpose_other');
        if (!select || !wrapper || !otherInput) return;

        if (select.value === 'other') {
            wrapper.classList.remove('d-none');
            otherInput.setAttribute('required', 'required');
            // focus for convenience
            otherInput.focus();
        } else {
            wrapper.classList.add('d-none');
            otherInput.removeAttribute('required');
            otherInput.value = '';
            otherInput.classList.remove('is-invalid');
        }
    }

    function onModalShow(ev) {
        try {
            const modal = ev.target;
            const trigger = ev.relatedTarget;
            const childId = trigger && trigger.getAttribute('data-child-id');
            const hidden = modal.querySelector('#visit_child_record_id');
            if (hidden) hidden.value = childId || '';

            // reset UI validation states
            const form = modal.querySelector('#visitScheduleForm');
            if (form) {
                form.classList.remove('was-validated');
                Array.from(form.elements || []).forEach(el => el.classList.remove('is-invalid'));
            }

            // reset purpose other state
            const select = modal.querySelector('#visit_purpose');
            if (select) {
                select.dispatchEvent(new Event('change'));
            }
        } catch (err) {
            console.warn('visit modal show handler error', err);
        }
    }

    function init() {
        const modalEl = document.getElementById('visitScheduleModal');
        if (modalEl) {
            modalEl.addEventListener('show.bs.modal', onModalShow);
        }

        const purpose = document.getElementById('visit_purpose');
        if (purpose) {
            purpose.addEventListener('change', onPurposeChange);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
