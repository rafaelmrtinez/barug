(() => {
    const weightInput = document.getElementById("id_birth_weight");
    const underWeightCheckbox = document.getElementById("id_low_birth_weight");

    if (!weightInput || !underWeightCheckbox) {
        return;
    }

    weightInput.addEventListener("input", (e) => {
        let weight = parseFloat(e.target.value);
        if (isNaN(weight)) {
            underWeightCheckbox.checked = false;
            return;
        }
        underWeightCheckbox.checked = weight < 2.5;
    });
})();