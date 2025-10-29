document.addEventListener('DOMContentLoaded', function () {
    // schedule (prenatal)
    document.body.addEventListener('click', function (ev) {
        const btn = ev.target.closest && ev.target.closest('.btn-schedule');
        if (!btn) return;
        const mhrId = btn.getAttribute('data-mhr-id');
        const hidden = document.getElementById('sched_maternal_record_id');
        const form = document.getElementById('prenatalScheduleForm');
        if (form) form.reset();
        if (hidden) hidden.value = mhrId || '';
    });

    // postpartum
    document.body.addEventListener('click', function (ev) {
        const btn = ev.target.closest && ev.target.closest('.btn-postpartum');
        if (!btn) return;
        const mhrId = btn.getAttribute('data-mhr-id');
        const hidden = document.getElementById('post_maternal_record_id');
        const form = document.getElementById('postpartumScheduleForm');
        if (form) form.reset();
        if (hidden) hidden.value = mhrId || '';
    });

    // postpartum record (modal with form)
    document.body.addEventListener('click', function (ev) {
        const btn = ev.target.closest && ev.target.closest('.btn-postpartum-record');
        if (!btn) return;
        const mhrId = btn.getAttribute('data-mhr-id');
        const hidden = document.getElementById('id_maternal_record_id');
        const form = document.getElementById('postpartumRecordForm');
        if (form) form.reset();
        if (hidden) hidden.value = mhrId || '';
    });

    // Optional: enhance form submissions with basic UX (disable submit while posting)
    function enhanceForm(formId) {
        const form = document.getElementById(formId);
        if (!form) return;
        form.addEventListener('submit', function (e) {
            const btn = form.querySelector('button[type="submit"]');
            if (btn) {
                // disable submit but DO NOT change the button text
                if (globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
                    try { globalThis.MHRScheduleHelpers.setSubmitLoading(btn, true); } catch (_e) { /* ignore */ }
                } else {
                    btn.disabled = true;
                    btn.classList.add('disabled');
                    try { btn.setAttribute('aria-busy', 'true'); } catch (_e) { /* ignore */ }
                }
            }
        });
    }

    enhanceForm('prenatalScheduleForm');
    enhanceForm('postpartumScheduleForm');
    enhanceForm('postpartumRecordForm');
});