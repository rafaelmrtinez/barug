
/**
 * update_household.js
 * Handles AJAX submission for updating household information and changing household head.
 *
 * - submitHouseholdDetails: Handles the first section (household info update)
 * - submitHouseholdHeadChange: Handles the second section (household head change)
 *
 * Each handler is bound to its respective button to avoid API call clashes.
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
   * Handles submission of household details (first section of modal)
   * Calls /bhw/api/update-household-information/
   * @param {Event} e
   */
  async function submitHouseholdDetails(e) {
    e.preventDefault();
    const form = e.target.closest('form');
    if (!form) return;
    // Gather form data
    const payload = {
      household_id: form.querySelector('[name="household_num"]').value,
      reason: 'Update household info',
      house_type_id: form.querySelector('[name="house_type"]').value,
      house_ownership_id: form.querySelector('[name="house_ownership"]').value,
      city: '',
      barangay: '',
      street: '',
      purok_sitio_name: '',
      latitude: '',
      longitude: ''
    };

    // Parse address input if available
    const addressInput = form.querySelector('#household_address_input');
    if (addressInput && addressInput.value) {
      // Address format: "house_num, street, purok_sitio, barangay, city"
      const parts = addressInput.value.split(',').map(s => s.trim());
      if (parts.length >= 5) {
        payload.house_num = parts[0];
        payload.street = parts[1];
        payload.purok_sitio_name = parts[2];
        payload.barangay = parts[3];
        payload.city = parts.slice(4).join(', ');
      } else if (parts.length === 4) {
        payload.house_num = parts[0];
        payload.street = parts[1];
        payload.barangay = parts[2];
        payload.city = parts[3];
      } else {
        payload.street = addressInput.value;
      }
    }

    // Get latitude/longitude from hidden fields or map
    let lat = '';
    let lng = '';
    const latInput = form.querySelector('[name="latitude"]');
    const lngInput = form.querySelector('[name="longitude"]');
    if (latInput && latInput.value) lat = latInput.value;
    if (lngInput && lngInput.value) lng = lngInput.value;
    // Mapbox/Leaflet map data attributes
    const mapDiv = document.getElementById('map');
    if (mapDiv) {
      if (mapDiv.dataset && mapDiv.dataset.lat) lat = mapDiv.dataset.lat;
      if (mapDiv.dataset && mapDiv.dataset.lng) lng = mapDiv.dataset.lng;
    }
    // Fallback: window.lastSelectedLatLng
    if ((!lat || !lng) && window.lastSelectedLatLng) {
      if (window.lastSelectedLatLng.lat) lat = window.lastSelectedLatLng.lat;
      if (window.lastSelectedLatLng.lng) lng = window.lastSelectedLatLng.lng;
    }
    payload.latitude = lat;
    payload.longitude = lng;

    // performed_by (if present)
    const performedByInput = form.querySelector('[name="performed_by"]');
    if (performedByInput && performedByInput.value) payload.performed_by = performedByInput.value;

    // Validate required fields
    if (!payload.household_id || !payload.house_type_id || !payload.house_ownership_id || !payload.city || !payload.barangay || !payload.street) {
      alert('Please fill all required fields.');
      return;
    }
    try {
      const response = await fetch('/bhw/api/update-household-information/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (result.success) {
        alert('Household information updated successfully!');
        window.location.reload();
      } else {
        alert('Error: ' + (result.error || 'Unknown error'));
      }
    } catch (err) {
      alert('Request failed: ' + err);
    }
  }

  /**
   * Handles submission of household head change (second section of modal)
   * Calls /bhw/api/update-household-head/
   * @param {Event} e
   */
  async function submitHouseholdHeadChange(e) {
    e.preventDefault();
    const form = e.target.closest('form');
    if (!form) return;
    // Gather form data for head change
    const payload = {
      household_id: form.querySelector('[name="household_num"]').value,
      new_head_id: '',
      reason: 'Change household head'
    };
    // Get new head from select or input
    const newHeadInput = form.querySelector('[name="new_household_head"]');
    if (newHeadInput && newHeadInput.value) {
      payload.new_head_id = newHeadInput.value;
    } else {
      alert('Please select a new household head.');
      return;
    }
    // performed_by (if present)
    const performedByInput = form.querySelector('[name="performed_by"]');
    if (performedByInput && performedByInput.value) payload.performed_by = performedByInput.value;

    // Validate required fields
    if (!payload.household_id || !payload.new_head_id) {
      alert('Please fill all required fields.');
      return;
    }
    try {
      const response = await fetch('/bhw/api/update-household-head/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (result.success) {
        alert('Household head updated successfully!');
        window.location.reload();
      } else {
        alert('Error: ' + (result.error || 'Unknown error'));
      }
    } catch (err) {
      alert('Request failed: ' + err);
    }
  }

  // DOMContentLoaded: Bind each handler to its respective button
  document.addEventListener('DOMContentLoaded', function() {
    // Section 1: Update Household Info
    const saveInfoBtn = document.querySelector('#updateHouseholdModal .accordion #householdSection1 .btn.btn-primary[type="submit"]');
    if (saveInfoBtn) {
      saveInfoBtn.addEventListener('click', submitHouseholdDetails);
    }
    // Section 2: Change Household Head
    const saveHeadBtn = document.querySelector('#updateHouseholdModal .accordion #householdSection2 .btn.btn-primary[type="submit"]');
    if (saveHeadBtn) {
      saveHeadBtn.addEventListener('click', submitHouseholdHeadChange);
    }
  });
})();
