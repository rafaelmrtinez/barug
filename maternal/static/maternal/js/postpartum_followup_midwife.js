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

      try{
        submitBtn.disabled = true;
        const endpoint = '/api/dummy/maternal/postpartum/midwife'; // dummy endpoint
        const resp = await submitForm(payload, endpoint);
        if (!resp.ok){
          let text = 'Failed to save. Please try again.';
          try { const j = await resp.json(); if (j && j.error) text = j.error; } catch(e){}
          MHRToast.show(text, false);
          return;
        }

        MHRToast.show('Postpartum follow-up saved', true);
        // optionally close modal if bootstrap present
        try{
          if (window.bootstrap){
            const modalEl = document.getElementById('postpartumFollowupMidwifeModal');
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
          }
        }catch(e){}

      }catch(err){
        console.error(err);
        MHRToast.show('An unexpected error occured', false);
      }finally{
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
