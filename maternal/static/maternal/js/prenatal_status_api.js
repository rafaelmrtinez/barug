(function () {
  'use strict';

  // Small helper to read a cookie value (CSRF token)
  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
  }

  function showToast(msg, success = true) {
    try {
      if (globalThis.CustomToast && typeof globalThis.CustomToast.show === 'function') {
        return globalThis.CustomToast.show(String(msg || ''), { type: success ? 'success' : 'error' });
      }
    } catch (__) { /* ignore */ }
    // Avoid using blocking `alert()`/`confirm()` in production code.
    try { console.log(String(msg)); } catch (__2) { /* ignore logging errors */ }
  }

  // Basic front-end sanitization for integers
  function toPositiveInt(value) {
    const n = Number.parseInt(String(value).trim(), 10);
    return Number.isInteger(n) && n > 0 ? n : null;
  }

  document.addEventListener('DOMContentLoaded', function () {
    try {
      const form = document.getElementById('prenatal-form');
      if (!form) return;

      // The prenatal form includes multiple submit buttons; we need the "Mark Visit as Complete" one.
      const submitButtons = Array.from(form.querySelectorAll('button[type="submit"]'));
      let markBtn = submitButtons.find(b => (b.textContent || b.innerText || '').trim().toLowerCase().includes('mark visit as complete'));
      // fallback: look for button with exact label
      if (!markBtn) markBtn = submitButtons.find(b => (b.textContent || b.innerText || '').trim().toLowerCase() === 'mark visit as complete');
      if (!markBtn) return; // nothing to wire

      markBtn.addEventListener('click', async function (ev) {
        ev.preventDefault();
        ev.stopPropagation();

        // Confirm user's intent first
        const proceed = confirm('Are you sure you want to mark today\u2019s prenatal visit as complete?');
        if (!proceed) return;

        // Read and validate mhr id from form data attribute
        const mhrIdRaw = form.getAttribute('data-mhr-id');
        const mhrId = toPositiveInt(mhrIdRaw);
        if (!mhrId) {
          showToast('Cannot determine maternal record id. Please reload the page and try again.', false);
          return;
        }

        // CSRF
        const csrftoken = getCookie('csrftoken');
        if (!csrftoken) {
          // Generic message only
          showToast('Unable to perform action due to missing CSRF token. Please reload and try again.', false);
          return;
        }

        // Prepare UI state
        const originalText = markBtn.textContent;
        markBtn.disabled = true;
        markBtn.textContent = 'Completing...';

        try {
          const url = '/maternal/api/v1/mhr/visit/complete/';
          const payload = { mhr_id: mhrId };

          const resp = await fetch(url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrftoken
            },
            credentials: 'same-origin',
            body: JSON.stringify(payload)
          });

          let body = null;
          try { body = await resp.json(); } catch (_err) { /* non-json response */ }

          if (!resp.ok) {
            // Show server-provided message if safe, otherwise generic
            const userMsg = (body && body.message) ? String(body.message) : 'Unable to complete visit. Please try again later.';
            showToast(userMsg, false);
            // keep internal details in console for developers
            console.error('Prenatal visit complete API error', resp.status, body);
            return;
          }

          // success
          const successMsg = (body && body.message) ? String(body.message) : 'Visit marked complete.';
          showToast(successMsg, true);
        } catch (err) {
          // network/unexpected error: show generic message only
          showToast('An unexpected error occurred. Please try again later.', false);
          console.error('Error calling prenatal visit complete API', err);
        } finally {
          markBtn.disabled = false;
          markBtn.textContent = originalText;
        }
      });
    } catch (e) {
      console.error('prenatal_status_api initialization error', e);
    }
  });
})();
