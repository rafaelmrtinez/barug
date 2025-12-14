/**
 * update_family.js
 * Handles AJAX submission for updating family information in the Update Family Information modal.
 *
 * - submitFamilyDetails: Handles the first section (family info update)
 *
 * The handler is bound to the Save Family Details button to avoid API call clashes.
 */
// ================= Update Family Information Modal JS =================
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

  // DOMContentLoaded: Bind handlers for both sections
  document.addEventListener('DOMContentLoaded', function() {
    // Section 1: Update Family Info
    const saveFamilyDetailsBtn = document.querySelector('#updateFamilyModal .accordion #sharedFamilySection1 .btn.btn-primary[type="submit"]');
    if (saveFamilyDetailsBtn) {
      saveFamilyDetailsBtn.addEventListener('click', submitFamilyDetails);
    }

    // ================= Save Head Change Handler =================
    /**
     * Handles submission for changing the family head (second section of modal)
     * Calls /bhw/api/update-family-head/
     * @param {Event} e
     */
    async function submitFamilyHeadChange(event) {
      event.preventDefault();
      const form = event.target.closest('form');
      if (!form) return;

      // Gather form data for head change
      const familyId = form.querySelector('[name="family_num"]')?.value;
      const newHeadPersonId = form.querySelector('[name="new_family_head"]')?.value;
      const reason = form.querySelector('[name="head_change_reason"]')?.value || 'Change family head';

      // Validate required fields
      if (!familyId || !newHeadPersonId) {
        alert('Please select a family and a new head.');
        return;
      }

      const payload = {
        family_id: familyId,
        new_head_person_id: newHeadPersonId,
        reason: reason
      };

      try {
        const response = await fetch('/bhw/api/update-family-head/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
          },
          body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (result.success) {
          alert('Family head updated successfully!');
          window.location.reload();
        } else {
          alert('Error: ' + (result.error || 'Unknown error'));
        }
      } catch (err) {
        alert('Request failed: ' + err);
      }
    }
    // ================= End Save Head Change Handler =================

    // Section 2: Save Head Change button
    const saveHeadChangeBtn = document.querySelector('#updateFamilyModal .accordion #sharedFamilySection2 .btn.btn-primary[type="submit"]');
    if (saveHeadChangeBtn) {
      saveHeadChangeBtn.addEventListener('click', submitFamilyHeadChange);
    }
  });
// ================= End Update Family Information Modal JS =================
})();
