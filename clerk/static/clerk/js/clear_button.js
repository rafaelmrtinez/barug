(function () {
  const clearBtn   = document.getElementById('ClearBtn');
  const form       = document.querySelector('#create-pane form');   // the Fill-up form
  const pageRoot   = document.getElementById('ownerPage');
  const clearURL   = pageRoot?.dataset.clearOwnerUrl || null;

  function getCookie(name){
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return '';
  }

  function clearFormFields(formEl){
    if (!formEl) return;
    const els = formEl.querySelectorAll('input, select, textarea');

    els.forEach(el => {
      const tag = el.tagName.toLowerCase();
      const type = (el.type || '').toLowerCase();

      if (tag === 'select') {
        el.selectedIndex = 0;                 // first option
        return;
      }

      if (type === 'checkbox' || type === 'radio') {
        el.checked = false;
        return;
      }

      if (type === 'file') {
        el.value = '';                        // drop chosen files
        return;
      }

      // text, email, number, date, time, hidden, textarea, etc.
      el.value = '';
    });

    // clear Bootstrap validation states if any
    formEl.classList.remove('was-validated');
    formEl.querySelectorAll('.is-invalid, .is-valid').forEach(x => {
      x.classList.remove('is-invalid', 'is-valid');
    });
  }

  async function clearSessionDraft(){
    if (!clearURL) return;
    try{
      await fetch(clearURL, {
        method: 'POST',
        headers: {
          'X-CSRFToken': getCookie('csrftoken'),
          'X-Requested-With': 'XMLHttpRequest'
        }
      });
    } catch(e){
      // non-fatal; UI is already cleared
      console.warn('Clear owner draft failed:', e);
    }
  }

  clearBtn?.addEventListener('click', async () => {
    clearFormFields(form);
    await clearSessionDraft();
    // optional: focus first field
    const firstInput = form?.querySelector('input, select, textarea');
    firstInput?.focus();
  });
})();