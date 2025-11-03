(() => {
document.addEventListener("DOMContentLoaded", function () {
    // Select all checkbox inputs whose name starts with "vit_a_"
    const vitCheckboxes = Array.from(document.querySelectorAll('input[type="checkbox"][name^="vit_a_"]'));

    if (vitCheckboxes.length === 0) {
        // No vitamin checkboxes found — helpful for debugging
        console.debug("No vitamin checkboxes found with selector input[type=checkbox][name^='vit_a_'].");
        return;
    }

    function isReadonlyOrDisabled(el) {
        return el.hasAttribute('readonly') || el.disabled || el.getAttribute('aria-disabled') === 'true';
    }

    vitCheckboxes.forEach(cb => {
        cb.addEventListener('change', () => {
            // If current became checked, uncheck all other non-readonly checkboxes
            if (cb.checked) {
                vitCheckboxes.forEach(other => {
                    if (other === cb) return;

                    // don't uncheck previously completed (readonly/disabled) boxes
                    if (isReadonlyOrDisabled(other)) return;

                    // uncheck other checkboxes
                    other.checked = false;
                });
            }
        });
    });
});
})();