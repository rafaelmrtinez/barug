/* Shared helpers for schedule form submit buttons */
(function () {
  'use strict';

  function setSubmitLoading(btn, isLoading) {
    if (!btn) return;
    if (isLoading) {
      // disable the button to prevent duplicate submits
      btn.disabled = true;
      btn.classList.add('disabled');
      // mark busy for accessibility but do NOT add/change visible text or spinner
      try { btn.setAttribute('aria-busy', 'true'); } catch (_e) { /* ignore */ }
    } else {
      btn.disabled = false;
      btn.classList.remove('disabled');
      try { btn.removeAttribute('aria-busy'); } catch (_e) { /* ignore */ }
    }
  }

  // expose globally for the schedule scripts
  globalThis.MHRScheduleHelpers = globalThis.MHRScheduleHelpers || {};
  globalThis.MHRScheduleHelpers.setSubmitLoading = setSubmitLoading;

})();
