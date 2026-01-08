/**
 * Resident Detail - Confirm Residency Functionality
 */

document.addEventListener('DOMContentLoaded', function () {
    const confirmBtn = document.getElementById('confirmResidencyBtn');
    const saveBtn = document.getElementById('saveConfirmResidency');
    const modal = new bootstrap.Modal(document.getElementById('confirmResidencyModal'));

    if (confirmBtn) {
        confirmBtn.addEventListener('click', () => {
            // Open the modal instead of showing confirmation dialog
            modal.show();
        });
    }

    if (saveBtn) {
        saveBtn.addEventListener('click', handleSaveConfirmation);
    }
});

/**
 * Handle the save button click in the modal
 */
function handleSaveConfirmation() {
    const form = document.getElementById('confirmResidencyForm');

    // Validate form
    if (!form.checkValidity()) {
        form.reportValidity();
        return;
    }

    // Get form values
    const reason = document.getElementById('residencyReason').value.trim();
    const householdRelationship = document.getElementById('householdRelationship').value;
    const familyRelationship = document.getElementById('familyRelationship').value;
    const residentId = document.getElementById('residentId').value;

    // Show confirmation dialog (keep modal open)
    const confirmed = confirm('Are you sure you want to confirm this resident\'s residency status?');

    if (confirmed) {
        // Get CSRF token from the page
        const csrfToken = getCSRFToken();

        // Get resident code from the page
        const residentCode = document.querySelector('.resident-code').textContent.trim();

        // Send POST request with form data
        sendConfirmationRequest(residentCode, csrfToken, reason, householdRelationship, familyRelationship, residentId);
    }
    // If user cancels, modal stays open (do nothing)
}

/**
 * Send the POST request to confirm residency
 * @param {string} residentCode - The resident's person code
 * @param {string} csrfToken - The CSRF token
 * @param {string} reason - The reason for confirmation
 * @param {string} householdRelationship - Relationship to household head
 * @param {string} familyRelationship - Relationship to family head
 * @param {string} residentId - The resident's ID
 */
async function sendConfirmationRequest(residentCode, csrfToken, reason, householdRelationship, familyRelationship, residentId) {
    // Placeholder URL - replace with actual endpoint
    const url = '/bhw/api/confirm-residency/';

    // Disable save button and show loading state
    const saveBtn = document.getElementById('saveConfirmResidency');
    const originalSaveContent = saveBtn.innerHTML;
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Processing...';

    try {
        const result = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify({
                person_code: residentCode,
                reason: reason,
                household_relationship_id: householdRelationship,
                family_relationship_id: familyRelationship,
                person_id: residentId,
            }),
        });
        if (!result.ok) {
            const errorData = await result.json();
            alert(errorData.error || 'Failed to confirm residency.');
            return;
        }
        const jsonData = await result.json();
        if (jsonData.success) {
            alert('Residency confirmed successfully.');
            // Optionally, refresh the page or update UI
            window.location.reload();
        } else {
            alert(jsonData.error || 'Failed to confirm residency.');
        }
    } catch (error) {
        console.error('Error during fetch:', error);
        alert('An error occurred while confirming residency. Please try again.');
    } finally {
        // Re-enable save button and restore content
        saveBtn.disabled = false;
        saveBtn.innerHTML = originalSaveContent;
    }
}

/**
 * Get CSRF token from cookies or meta tag
 * @returns {string} The CSRF token
 */
function getCSRFToken() {
    // Try to get from cookie first
    const cookieValue = document.cookie
        .split('; ')
        .find(row => row.startsWith('csrftoken='))
        ?.split('=')[1];

    if (cookieValue) {
        return cookieValue;
    }

    // Fallback to meta tag
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    return metaTag ? metaTag.getAttribute('content') : '';
}
