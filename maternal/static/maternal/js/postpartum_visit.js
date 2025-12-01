/**
 * Postpartum Visit Management
 * Handles add and edit operations for postpartum visit records
 */

(function() {
    'use strict';

    // Get CSRF token from cookie
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

    const csrftoken = getCookie('csrftoken');

    // Populate edit modal when View/Edit button is clicked
    const viewPostpartumModal = document.getElementById('viewPostpartumModal');
    if (viewPostpartumModal) {
        viewPostpartumModal.addEventListener('show.bs.modal', function(event) {
            const button = event.relatedTarget;
            
            // Populate form fields with data attributes
            document.getElementById('edit_pp_row_id').value = button.getAttribute('data-pp-row-id') || '';
            document.getElementById('edit_date_visit').value = button.getAttribute('data-date-visit') || '';
            document.getElementById('edit_lochial').value = button.getAttribute('data-lochial') || '';
            document.getElementById('edit_bp_systolic').value = button.getAttribute('data-bp-systolic') || '';
            document.getElementById('edit_bp_diastolic').value = button.getAttribute('data-bp-diastolic') || '';
            document.getElementById('edit_feeding_type').value = button.getAttribute('data-feeding-type') || '';
            document.getElementById('edit_findings').value = button.getAttribute('data-findings') || '';
            document.getElementById('edit_notes').value = button.getAttribute('data-notes') || '';
        });
    }

    // Handle add postpartum visit form submission
    const addForm = document.getElementById('addPostpartumForm');
    if (addForm) {
        addForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const formData = new FormData(addForm);
            const payload = {};
            formData.forEach((value, key) => {
                payload[key] = value;
            });

            const submitBtn = addForm.querySelector('button[type="submit"]');
            const originalText = submitBtn.textContent;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Saving...';

            fetch('/maternal/api/v1/postpartum-visit/create/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrftoken
                },
                body: JSON.stringify(payload)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Show success message
                    if (window.showToast) {
                        window.showToast('Postpartum visit added successfully', 'success');
                    } else {
                        alert('Postpartum visit added successfully');
                    }
                    
                    // Close modal and reload page
                    const modal = bootstrap.Modal.getInstance(document.getElementById('addPostpartumModal'));
                    modal.hide();
                    location.reload();
                } else {
                    throw new Error(data.message || 'Failed to add postpartum visit');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                if (window.showToast) {
                    window.showToast(error.message || 'Failed to add postpartum visit', 'error');
                } else {
                    alert(error.message || 'Failed to add postpartum visit');
                }
            })
            .finally(() => {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            });
        });
    }

    // Handle edit postpartum visit form submission
    const editForm = document.getElementById('editPostpartumForm');
    if (editForm) {
        editForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const formData = new FormData(editForm);
            const payload = {};
            formData.forEach((value, key) => {
                payload[key] = value;
            });

            const submitBtn = editForm.querySelector('button[type="submit"]');
            const originalText = submitBtn.textContent;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Saving...';

            fetch('/maternal/api/v1/postpartum-visit/update/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrftoken
                },
                body: JSON.stringify(payload)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Show success message
                    if (window.showToast) {
                        window.showToast('Postpartum visit updated successfully', 'success');
                    } else {
                        alert('Postpartum visit updated successfully');
                    }
                    
                    // Close modal and reload page
                    const modal = bootstrap.Modal.getInstance(document.getElementById('viewPostpartumModal'));
                    modal.hide();
                    location.reload();
                } else {
                    throw new Error(data.message || 'Failed to update postpartum visit');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                if (window.showToast) {
                    window.showToast(error.message || 'Failed to update postpartum visit', 'error');
                } else {
                    alert(error.message || 'Failed to update postpartum visit');
                }
            })
            .finally(() => {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            });
        });
    }

    // Reset add form when modal is hidden
    const addPostpartumModal = document.getElementById('addPostpartumModal');
    if (addPostpartumModal) {
        addPostpartumModal.addEventListener('hidden.bs.modal', function() {
            addForm.reset();
        });
    }
})();
