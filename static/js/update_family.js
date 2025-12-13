/**
 * update_family.js
 * Handles AJAX submission for updating family information in the Update Family Information modal.
 *
 * - submitFamilyDetails: Handles the first section (family info update)
 *
 * The handler is bound to the Save Family Details button to avoid API call clashes.
 */
(function() {
  /**
   * Helper to get CSRF token from cookie
   * @param {string} name
   * @returns {string|null}
   */
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  /**
   * Handles submission of family details (first section of modal)
   * Calls /bhw/api/update-family-information/
   * @param {Event} e
   */
  async function submitFamilyDetails(e) {
    e.preventDefault();
    const form = e.target.closest('form');
    if (!form) return;
    // Gather form data
    const payload = {
      family_id: form.querySelector('[name="family_num"]').value,
      reason: 'Update family info',
      source_of_income: form.querySelector('[name="source_of_income"]').value,
      family_mnthly_icnome_id: form.querySelector('[name="monthly_income_range"]').value,
      nhts_status_id: form.querySelector('[name="nhts_status"]').value,
      indigent_status_id: form.querySelector('[name="indigent_status"]').value,
      household_type_id: form.querySelector('[name="household_type"]').value,
      household_id: form.querySelector('[name="household_num"]').value,
      family_head_id: form.querySelector('[name="family_head"]').value,
      rel_to_hhold_head_id: form.querySelector('[name="relationship_to_household_head"]').value
    };

    // Validate required fields (example: family_id, household_id, family_head_id)
    if (!payload.family_id || !payload.household_id || !payload.family_head_id) {
      alert('Please fill all required fields.');
      return;
    }
    try {
      const response = await fetch('/bhw/api/update-family-information/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (result.success) {
        alert('Family information updated successfully!');
        window.location.reload();
      } else {
        alert('Error: ' + (result.error || 'Unknown error'));
      }
    } catch (err) {
      alert('Request failed: ' + err);
    }
  }

  // DOMContentLoaded: Bind handler to Save Family Details button
  document.addEventListener('DOMContentLoaded', function() {
    // Section 1: Update Family Info
    const saveFamilyBtn = document.querySelector('#updateFamilyModal .accordion #sharedFamilySection1 .btn.btn-primary[type="submit"]');
    if (saveFamilyBtn) {
      saveFamilyBtn.addEventListener('click', submitFamilyDetails);
    }
  });
})();
