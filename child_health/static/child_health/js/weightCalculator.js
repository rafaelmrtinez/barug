(() => {
    document.addEventListener("DOMContentLoaded", () => {
        const weightInput = document.getElementById("id_birth_weight");
        const underWeightCheckbox = document.getElementById("id_low_birth_weight");

        if (!weightInput || !underWeightCheckbox) {
            return;
        }

        const updateCheckboxState = (value) => {
            const weight = parseFloat(value);
            if (isNaN(weight)) {
                underWeightCheckbox.checked = false;
                return;
            }
            underWeightCheckbox.checked = weight < 2.5;
        };

        // --- Scenario 1: Page load (pre-filled value) ---
        if (weightInput.value.trim() !== "") {
            updateCheckboxState(weightInput.value);
        }

        // --- Scenario 2: User input changes ---
        weightInput.addEventListener("input", (e) => {
            updateCheckboxState(e.target.value);
        });
    });
})();
