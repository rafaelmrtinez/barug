// static/js/complete_visit.js
// Handles marking a household as quarterly visited

async function completeHouseholdVisit(id, staffId, type = 'household') {
  const entity = type === 'family' ? 'Family' : 'Household';
  const confirmMsg = `You are about to update this ${entity}. Are you sure you want to proceed?`;
  if (!confirm(confirmMsg)) {
    return;
  }
  try {
    const response = await fetch('/bhw/api/quarterly-visit-completion/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value || ''
      },
      body: JSON.stringify({
        type: type,
        id: id,
        staff_id: staffId
      })
    });
    const data = await response.json();
    if (response.ok && data.success) {
      if (type === 'family') {
        alert('Family visit marked as complete!');
      } else {
        alert('Household visit marked as complete!');
      }
      // Optionally reload or update UI
    } else {
      alert('Warning: ' + (data.error || 'Unknown error'));
    }
  } catch (err) {
    alert('Network or server error: ' + err);
  }
}
