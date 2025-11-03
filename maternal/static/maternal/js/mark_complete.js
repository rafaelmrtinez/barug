 (function () {
  'use strict';

  // Minimal cookie helper to read CSRF token
  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
  }

  document.addEventListener('DOMContentLoaded', function () {
    const btn = document.getElementById('btn-mark-complete');
    if (!btn) return;

    // try to find the select for status inside the action group or by common name
    const statusSelect = document.querySelector('.mhr-action-group select') || document.querySelector('select[name="confirm_complete"]');
    // try to find an element carrying the current maternal record id
    const mhrContainer = document.querySelector('[data-mhr-id]');

    // user-facing messages: errors are shown via confirm(), info goes to console
    function showMessage(message, isError = false) {
      if (isError) {
        try {
          // Use confirm so the user sees and has to acknowledge the message.
          // Return the boolean to callers if they care about user's choice.
          return Promise.resolve(confirm(message));
        } catch (_e) {
          console.error('Unable to show user message:', message);
          return Promise.resolve(false);
        }
      }
      console.log(message);
      return Promise.resolve(true);
    }

  btn.addEventListener('click', async function () {
      // Confirm user's intention
      const confirmed = confirm('Are you sure you want to mark this maternal health record as complete?');
      if (!confirmed) {
        // await showMessage('Action cancelled by user.', true);
        // console.log('User cancelled marking maternal health record as complete.');
        return;
      }

      // Basic front-end validation / sanitization
      const mhrIdRaw = mhrContainer ? mhrContainer.getAttribute('data-mhr-id') : null;
      const statusRaw = statusSelect ? statusSelect.value : null;

      // ensure values are present
      if (!mhrIdRaw) {
        await showMessage('Cannot determine maternal record id. Please reload the page and try again.', true);
        return;
      }

      if (!statusRaw) {
        await showMessage('Please select a valid status before continuing.', true);
        return;
      }

      // coerce to integers and validate
      const mhrId = Number.parseInt(mhrIdRaw, 10);
      const statusId = Number.parseInt(statusRaw, 10);
      if (!Number.isInteger(mhrId) || mhrId <= 0) {
        await showMessage('Invalid maternal record id. Aborting.', true);
        return;
      }
      if (!Number.isInteger(statusId) || statusId <= 0) {
        await showMessage('Invalid status selected. Aborting.', true);
        return;
      }

      // ensure the status value actually exists in the select options to avoid forged values
      const optionExists = statusSelect && Array.from(statusSelect.options).some(function (opt) { return String(opt.value) === String(statusRaw); });
      if (!optionExists) {
        await showMessage('Selected status is not valid. Aborting.', true);
        return;
      }

      // Prepare the request
      const url = '/maternal/api/v1/mhr/status/update/';
      const payload = { mhr_id: mhrId, status_id: statusId };

      // Disable button while working
      btn.disabled = true;
      const originalText = btn.textContent;
      btn.textContent = 'Saving...';

      try {
        const csrf = getCookie('csrftoken');
        const response = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrf || ''
          },
          credentials: 'same-origin',
          body: JSON.stringify(payload)
        });

        let body = null;
        try {
          body = await response.json();
        } catch (err) {
          // non-JSON response
          console.error('Non-JSON response from status update API', err);
        }

        if (!response.ok) {
          // show safe message to users; include API-provided message when available
          const userMsg = (body && body.message) ? body.message : 'Unable to update status. Please try again later.';
            // Format the message (if needed) and present once via confirm
            try {
            // If this is the ANC visits error, format it for readability
            let displayMsg = userMsg;
            try {
              const requiredMatch = userMsg.match(/First Trimester\s*>=\s*(\d+)[\s\S]*?Second Trimester\s*>=\s*(\d+)[\s\S]*?Third Trimester\s*>=\s*(\d+)/i);
              const currentMatch = userMsg.match(/Current:\s*First Trimester\s*=\s*(\d+),\s*Second Trimester\s*=\s*(\d+),\s*Third Trimester\s*=\s*(\d+)/i);

              if (/Cannot set\s*COMPLETE/i.test(userMsg) && requiredMatch && currentMatch) {
                displayMsg = 'Cannot set status to COMPLETE: required ANC visits not met.\n\n'
                  + 'Required minimums:\n'
                  + `  - First Trimester:   >= ${requiredMatch[1]}\n`
                  + `  - Second Trimester:  >= ${requiredMatch[2]}\n`
                  + `  - Third Trimester:   >= ${requiredMatch[3]}\n\n`
                  + 'Current counts:\n'
                  + `  - First Trimester:   ${currentMatch[1]}\n`
                  + `  - Second Trimester:  ${currentMatch[2]}\n`
                  + `  - Third Trimester:   ${currentMatch[3]}`;
              }
            } catch (_err) {
              // If parsing fails, fall back to the raw message
              displayMsg = userMsg;
            }

            await showMessage(displayMsg, true);
          } catch (_e) { /* ignore in non-browser envs */ }
          return;
        }

        // success
        const successMsg = (body && body.message) ? body.message : 'Status updated successfully.';
        await showMessage(successMsg, false);
        console.log('Maternal status update result:', body);
      } catch (err) {
        // avoid showing internal error details to users
        await showMessage('An unexpected error occurred. Please try again later.', true);
        console.error('Error while calling status update API:', err);
      } finally {
        // restore button state
        btn.disabled = false;
        btn.textContent = originalText;
      }
    });
  });
})();
