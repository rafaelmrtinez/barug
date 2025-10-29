/* Intercept postpartum schedule form submission, validate/sanitize, send JSON to API
   Uses async/await + try/catch; uses confirm() for user feedback and returns nothing. */

(function () {
  'use strict';

  function getCookie(name) {
    const cookies = document.cookie ? document.cookie.split('; ') : [];
    for (let i = 0; i < cookies.length; i++) {
      const parts = cookies[i].split('=');
      const key = parts.shift();
      const value = parts.join('=');
      if (key === name) return decodeURIComponent(value);
    }
    return null;
  }

  function sanitizeString(s, maxLen = 1000) {
    if (!s && s !== '') return '';
    let t = String(s).trim();
    if (t.length > maxLen) t = t.slice(0, maxLen);
    return t;
  }

  function showToast(message, isSuccess = false) {
    try {
      let container = document.getElementById('mhrToastContainer');
      if (!container) {
        container = document.createElement('div');
        container.id = 'mhrToastContainer';
        container.className = 'position-fixed top-0 end-0 p-3';
        container.style.zIndex = '10800';
        document.body.appendChild(container);
      }

      const toastEl = document.createElement('div');
      toastEl.className = 'toast align-items-center text-bg-' + (isSuccess ? 'success' : 'danger') + ' border-0';
      toastEl.role = 'alert';
      toastEl.ariaLive = 'assertive';
      toastEl.ariaAtomic = 'true';

      const toastBody = document.createElement('div');
      toastBody.className = 'd-flex';
      const body = document.createElement('div');
      body.className = 'toast-body';
      body.textContent = message;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-close btn-close-white me-2 m-auto';
      btn.setAttribute('data-bs-dismiss', 'toast');
      btn.ariaLabel = 'Close';

      toastBody.appendChild(body);
      toastBody.appendChild(btn);
      toastEl.appendChild(toastBody);
      container.appendChild(toastEl);

      const bsToast = new globalThis.bootstrap.Toast(toastEl, { delay: 4000 });
      bsToast.show();
      toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
    } catch (_err) {
      console.warn('Toast unavailable, message:', message);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const form = e.target || e.currentTarget;
    const submitBtn = form ? form.querySelector("button[type='submit']") : null;
    if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
      globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, true);
    } else if (submitBtn) {
      submitBtn.disabled = true; submitBtn.classList.add('disabled');
    }

    const mhrIdEl = document.getElementById('post_maternal_record_id');
    const dateEl = document.getElementById('post_sched_date');
    const timeEl = document.getElementById('post_sched_time');
    const visitEl = document.getElementById('post_visit');
    const purposeEl = document.getElementById('post_purpose');

    const mhrId = sanitizeString(mhrIdEl?.value || '');
    const schedule_date = sanitizeString(dateEl?.value || '');
    const schedule_time = sanitizeString(timeEl?.value || '');
    const visit = sanitizeString(visitEl?.value || '', 200);
    const purpose = sanitizeString(purposeEl?.value || '', 500);

    // Basic front-end validation
    if (!mhrId || Number.isNaN(Number(mhrId))) {
      showToast('Invalid maternal record id.', false);
      if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
        globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
      } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
      return;
    }
    if (!schedule_date) {
      showToast('Please choose a schedule date.', false);
      if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
        globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
      } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
      return;
    }
    if (!schedule_time) {
      showToast('Please choose a schedule time.', false);
      if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
        globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
      } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
      return;
    }
    if (!visit) {
      showToast('Please provide the visit name.', false);
      if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
        globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
      } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
      return;
    }
    if (!purpose) {
      showToast('Please provide the purpose for the visit.', false);
      if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
        globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
      } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
      return;
    }

    // Same-day time validation: if schedule_date === today, ensure schedule_time >= now
    try {
      const now = new Date();
      const selDate = new Date(schedule_date + 'T' + schedule_time);
      if (selDate.toDateString() === now.toDateString() && selDate < now) {
        showToast('Cannot schedule a visit for a time in the past today.', false);
        if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
          globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
        } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
        return;
      }
    } catch (_err) {
      // ignore parse errors and let server validate
    }

    const payload = {
      mhr_id: Number(mhrId),
      schedule_date,
      schedule_time,
      visit,
      purpose,
    };

    const csrftoken = getCookie('csrftoken');

    try {
      const resp = await fetch('/maternal/api/v1/mhr/schedule/postpartum/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrftoken || ''
        },
        body: JSON.stringify(payload),
        credentials: 'same-origin'
      });

      let data = null;
      try {
        data = await resp.json();
      } catch (_err) {
        // ignore non-json
      }

      if (!resp.ok) {
        const msg = (data && data.message) ? data.message : `Server returned ${resp.status}`;
        showToast(`Failed to save postpartum schedule: ${msg}`, false);
        if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
          globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
        } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
        return;
      }

      const successMsg = (data && data.message) ? data.message : 'Postpartum schedule saved.';

      // close modal if bootstrap available
      try {
        const modalEl = document.getElementById('postpartumScheduleModal');
        if (globalThis.bootstrap && modalEl) {
          const inst = globalThis.bootstrap.Modal.getInstance(modalEl) || new globalThis.bootstrap.Modal(modalEl);
          inst.hide();
        }
      } catch (_e) {
        // ignore
      }

      showToast(successMsg, true);
      if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
        globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
      } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
      return;
    } catch (err) {
      console.error('Network or unexpected error', err);
      showToast('Unexpected network error while saving postpartum schedule.', false);
      if (submitBtn && globalThis.MHRScheduleHelpers && globalThis.MHRScheduleHelpers.setSubmitLoading) {
        globalThis.MHRScheduleHelpers.setSubmitLoading(submitBtn, false);
      } else if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('disabled'); }
      return;
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('postpartumScheduleForm');
    if (form) form.addEventListener('submit', handleSubmit);
    // set min date to today to prevent selecting past dates (greys out previous dates)
    try {
      const dateEl = document.getElementById('post_sched_date');
      if (dateEl) {
        const today = new Date();
        const yyyy = today.getFullYear();
        const mm = String(today.getMonth() + 1).padStart(2, '0');
        const dd = String(today.getDate()).padStart(2, '0');
        dateEl.setAttribute('min', `${yyyy}-${mm}-${dd}`);
      }
    } catch (_err) {
      // ignore
    }
  });

})();
