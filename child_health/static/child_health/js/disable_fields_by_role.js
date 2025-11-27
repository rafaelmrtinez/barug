document.addEventListener('DOMContentLoaded', function () {
    const role = window.__USER_ROLE || '';

    // Helper to set disabled/readOnly on matching fields
    function setDisabled(selectorList, disabled) {
        selectorList.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
                // Prefer disabled for form controls, readOnly for textareas where appropriate
                if ('disabled' in el) el.disabled = disabled;
                if (el.tagName === 'TEXTAREA') el.readOnly = disabled;
                if (disabled) el.classList.add('disabled'); else el.classList.remove('disabled');
            });
        });
    }

    // Field selectors (scoped to #visit-entry where possible)
    const visitScope = '#visit-entry';
    const ageSelectors = [
        `${visitScope} [name$="age"]`,
        `${visitScope} [id*="age"]`,
        `${visitScope} input[id*="age"]`
    ];
    const weightSelectors = [
        `${visitScope} [name$="weight"]`,
        `${visitScope} [id*="weight"]`,
        `${visitScope} input[id*="weight"]`
    ];
    const tempSelectors = [
        `${visitScope} [name$="temp"]`,
        `${visitScope} [id*="temp"]`,
        `${visitScope} input[id*="temp"]`
    ];
    const heightSelectors = [
        `${visitScope} [name$="height"]`,
        `${visitScope} [id*="height"]`,
        `${visitScope} input[id*="height"]`
    ];
    const notesSelectors = [
        `${visitScope} [name$="notes"]`,
        `${visitScope} [id*="notes"]`,
        `${visitScope} textarea[id*="notes"]`,
        `${visitScope} textarea[name$="notes"]`
    ];
    const findingsSelectors = [
        `${visitScope} [name$="findings"]`,
        `${visitScope} [id*="findings"]`,
        `${visitScope} textarea[id*="findings"]`,
        `${visitScope} textarea[name$="findings"]`
    ];

    if (role === 'midwife') {
        setDisabled(ageSelectors, true);
        setDisabled(weightSelectors, true);
        setDisabled(tempSelectors, true);
        setDisabled(heightSelectors, true);
        setDisabled(notesSelectors, true);
    } else {
        // ensure enabled if not midwife
        setDisabled(ageSelectors, false);
        setDisabled(weightSelectors, false);
        setDisabled(tempSelectors, false);
        setDisabled(heightSelectors, false);
        setDisabled(notesSelectors, false);
    }

    if (role === 'barangay health worker') {
        setDisabled(findingsSelectors, true);
    } else {
        setDisabled(findingsSelectors, false);
    }

    // Also disable submit buttons for visit entry if all fields are disabled for the role
    // (prevents accidental submissions)
    try {
        const visitForm = document.querySelector('#visit-entry form');
        if (visitForm) {
            const allDisabled = role === 'midwife';
            visitForm.querySelectorAll('button[type="submit"]').forEach(btn => {
                btn.disabled = allDisabled;
            });
        }
    } catch (e) {
        // ignore
        console.error('disable_fields_by_role error', e);
    }
});
