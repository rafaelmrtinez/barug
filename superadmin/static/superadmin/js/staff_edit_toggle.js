// static/js/staff_edit_toggle.js
document.addEventListener('DOMContentLoaded', function () {
  const form = document.getElementById('staff-update-form');
  if (!form) return;

  const btnPrimary = document.getElementById('btn-primary');   // Update -> Save
  const btnSecondary = document.getElementById('btn-secondary'); // Clear Changes
  const controls = Array.from(form.querySelectorAll('select, input, textarea'));

  function setReadOnlyMode(isReadOnly) {
    controls.forEach(el => {
      if (el.tagName === 'SELECT') {
        el.disabled = isReadOnly;                 // disabled for selects
        el.setAttribute('aria-disabled', String(isReadOnly));
      } else {
        if (isReadOnly) el.setAttribute('readonly', 'readonly');
        else el.removeAttribute('readonly');      // readonly for inputs/textarea
      }
    });

    if (isReadOnly) {
      btnPrimary.type = 'button';
      btnPrimary.textContent = 'Update';
      // Hide the Clear button in read-only mode
      btnSecondary.classList.add('d-none');
    } else {
      btnPrimary.type = 'submit';
      btnPrimary.textContent = 'Save';
      // Show the Clear button in edit mode
      btnSecondary.classList.remove('d-none');
    }
  }

  // Initialize: read-only + hide Clear
  setReadOnlyMode(true);

  // Click "Update" => enable fields, show Clear, switch to "Save"
  btnPrimary.addEventListener('click', function () {
    if (btnPrimary.type === 'button') {
      setReadOnlyMode(false);
    }
  });

  // Click "Clear Changes" => reset form, go back to read-only, hide Clear
  btnSecondary.addEventListener('click', function () {
    // Let the native reset occur first
    setTimeout(() => setReadOnlyMode(true), 0);
  });
});
