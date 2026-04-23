(function(){
  'use strict';

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
  }

  function sanitizeText(value){
    if (typeof value !== 'string') return '';
    // simple sanitization: trim and remove suspicious control chars
    return value.trim().replace(/[\u0000-\u001f\u007f]/g, '');
  }

  async function submitForm(data, endpoint){
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

  function showErrors(errors){
    if (!errors || errors.length === 0) return;
    // show first error as toast and console all
    try { MHRToast.show(errors.join('\n'), false); } catch(e){ console.warn('Toast error', e); }
    console.warn('Form validation errors:', errors);
  }

  function init(){
    const form = document.getElementById('postpartumFollowupMidwifeForm');
    if (!form) return;
    const submitBtn = document.getElementById('midwife_submit_btn');

    form.addEventListener('submit', async function(ev){
      ev.preventDefault();

      const findings = sanitizeText(document.getElementById('mid_findings').value);
      const notes = sanitizeText(document.getElementById('mid_notes').value);
      const maternal_record_id = sanitizeText(document.getElementById('midwife_maternal_record_id').value || '');

      const errors = [];
      if (!findings) errors.push('Findings is required.');

      if (errors.length){
        showErrors(errors);
        return;
      }

      const payload = { maternal_record_id, findings, notes };

      // spinner on submit
      const origBtnHtml = submitBtn.innerHTML;
      try{
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>' + origBtnHtml;
        const endpoint = '/maternal/api/form/postpartum/midwife/';
        const resp = await submitForm(payload, endpoint);
        if (!resp.ok){
          let text = 'Failed to save. Please try again.';
          try {
            const j = await resp.json();
            if (j) {
              if (j.message) text = j.message;
              else if (j.error) text = j.error;
              else if (j.errors) text = Array.isArray(j.errors) ? j.errors.join('\n') : JSON.stringify(j.errors);
            }
          } catch(_e) { /* ignore */ }
          globalThis.MHRToast.show(text, false);
          return;
        }

        let successMsg = 'Postpartum follow-up saved';
        try { const j = await resp.json(); if (j && j.message) successMsg = j.message; } catch (_e) { /* ignore */ }
        globalThis.MHRToast.show(successMsg, true);
        // clear form
        try {
          form.reset();
          const hid = document.getElementById('midwife_maternal_record_id');
          if (hid) hid.value = '';
        } catch (_e) { /* ignore */ }
        // optionally close modal if bootstrap present
        try{
          if (globalThis.bootstrap){
            const modalEl = document.getElementById('postpartumFollowupMidwifeModal');
            const modal = globalThis.bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
          }
        }catch(e){}

      }catch(err){
        console.error(err);
        try { globalThis.MHRToast.show(err && err.message ? err.message : 'An unexpected error occured', false); } catch (_e) { console.warn(_e); }
      }finally{
        try { submitBtn.innerHTML = origBtnHtml; } catch (_e) { /* ignore */ }
        submitBtn.disabled = false;
      }

    });
  }

  // auto-init when DOM ready
  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // expose for tests/debug
  window.PostpartumFollowupMidwife = { init };

})();
