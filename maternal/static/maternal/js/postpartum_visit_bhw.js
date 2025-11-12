(function () {
  'use strict';

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
  }

  function sanitizeText(value) {
    if (typeof value !== 'string') return '';
    return value.trim().replace(/[\x00-\x1f\x7f]/g, '');
  }

  function toInt(v) {
    const n = parseInt(String(v).trim(), 10);
    return Number.isFinite(n) ? n : null;
  }

  async function submitForm(data, endpoint) {
    const csrftoken = getCookie('csrftoken');
    const headers = { 'Content-Type': 'application/json' };
    if (csrftoken) headers['X-CSRFToken'] = csrftoken;

    const resp = await fetch(endpoint, {
      method: 'POST',
      headers,
      body: JSON.stringify(data),
      credentials: 'same-origin'
    });
    return resp;
  }

  function showErrors(errors) {
    if (!errors || errors.length === 0) return;
    try { globalThis.MHRToast.show(errors.join('\n'), false); } catch (e) { console.warn('Toast error', e); }
    console.warn('Form validation errors:', errors);
  }

  function init() {
    const form = document.getElementById('postpartumVisitBHWForm');
    if (!form) return;
    const submitBtn = document.getElementById('bhw_submit_btn');

    form.addEventListener('submit', async function (ev) {
      ev.preventDefault();

      const lochial = sanitizeText(document.getElementById('lochial_discharge').value);
      const syst = toInt(document.getElementById('bp_systolic').value);
      const diast = toInt(document.getElementById('bp_diastolic').value);
      const feeding = sanitizeText(document.getElementById('feeding_type').value);
      const maternal_record_id = sanitizeText(document.getElementById('bhw_maternal_record_id').value || '');

      const errors = [];
      if (!lochial) errors.push('Lochial discharge is required.');
      if (syst === null) errors.push('Systolic blood pressure is required and must be a number.');
      if (diast === null) errors.push('Diastolic blood pressure is required and must be a number.');
      if (syst !== null && (syst < 30 || syst > 300)) errors.push('Systolic value out of expected range (30-300).');
      if (diast !== null && (diast < 20 || diast > 200)) errors.push('Diastolic value out of expected range (20-200).');
      if (!feeding) errors.push('Feeding type is required.');

      if (errors.length) {
        showErrors(errors);
        return;
      }

      const payload = { maternal_record_id, lochial_discharge: lochial, bp_systolic: syst, bp_diastolic: diast, feeding_type_id: Number(feeding) };

      // show spinner on submit button
      const origBtnHtml = submitBtn.innerHTML;
      try {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>' + origBtnHtml;
        const endpoint = '/maternal/api/form/postpartum/bhw/';
        const resp = await submitForm(payload, endpoint);
        if (!resp.ok) {
          let text = 'Failed to save. Please try again.';
          try {
            const j = await resp.json();
            if (j) {
              if (j.message) text = j.message;
              else if (j.error) text = j.error;
              else if (j.errors) text = Array.isArray(j.errors) ? j.errors.join('\n') : JSON.stringify(j.errors);
            }
          } catch (_err) { /* ignore */ }
          globalThis.MHRToast.show(text, false);
          return;
        }

        let successMsg = 'Postpartum visit saved';
        try { const j = await resp.json(); if (j && j.message) successMsg = j.message; } catch (_e) { /* ignore */ }
        globalThis.MHRToast.show(successMsg, true);
        // clear form inputs
        try {
          form.reset();
          const hid = document.getElementById('bhw_maternal_record_id');
          if (hid) hid.value = '';
        } catch (_e) { /* ignore */ }
        // close modal if bootstrap available
        try {
          if (globalThis.bootstrap) {
            const modalEl = document.getElementById('postpartumVisitBHWModal');
            const modal = globalThis.bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
          }
        } catch (_err) { /* ignore */ }

      } catch (err) {
        console.error(err);
        try { globalThis.MHRToast.show(err && err.message ? err.message : 'An unexpected error occured', false); } catch (e) { console.warn(e); }
      } finally {
        // restore button
        try { submitBtn.innerHTML = origBtnHtml; } catch (_e) { /* ignore */ }
        submitBtn.disabled = false;
      }

    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  globalThis.PostpartumVisitBHW = { init };

})();
