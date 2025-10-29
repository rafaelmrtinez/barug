(function () {
    // safe: check a global flag set via template or detect container class
    const container = document.querySelector('.container.mhr-locked');
    if (!container) return;

    // disable all inputs/selects/textareas inside container, but allow status dropdown to remain active
    const controls = container.querySelectorAll('input, select, textarea, button[type="submit"], button.section-action, button');
    controls.forEach(el => {
        // Buttons: hide all except the status action button (id="btn-mark-complete")
        if (el.tagName === 'BUTTON') {
            if (el.id === 'btn-mark-complete' || el.classList.contains('status-action')) {
                // keep visible so users can change record status (revert)
                return;
            }
            el.style.display = 'none';
            return;
        }

        // For selects, allow the status dropdown if it explicitly opts-in via data-allow-status-change
        if (el.tagName === 'SELECT' && (el.name === 'confirm_complete' || el.id === 'id_confirm_complete')) {
            const allow = el.getAttribute('data-allow-status-change');
            if (allow === '1') {
                // leave the status select enabled so the user can revert status
                return;
            }
        }

        // otherwise disable the control
        el.disabled = true;
        // for Bootstrap style, optionally add 'disabled' class
        el.classList && el.classList.add('disabled');
    });

    // optionally add a sticky message:
    const banner = document.createElement('div');
    banner.className = 'alert alert-warning';
    banner.innerText = 'This record is locked (COMPLETE / INCOMPLETE). Editing is disabled.';
    container.insertBefore(banner, container.firstChild);
})();