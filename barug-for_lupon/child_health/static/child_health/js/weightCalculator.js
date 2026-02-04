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
        
        // --- Visit Entry: live height (cm -> ft/in) preview ---
        const visitHeightInput = document.querySelector('#visit-entry [name="height"]');
        if (visitHeightInput) {
            // create preview element (small muted text)
            const preview = document.createElement('small');
            preview.className = 'form-text text-muted height-preview';
            preview.style.display = 'block';
            preview.style.marginTop = '4px';

            // try to append after the input; if wrapped, append to its parent
            if (visitHeightInput.parentNode) {
                visitHeightInput.parentNode.appendChild(preview);
            } else {
                visitHeightInput.after(preview);
            }

            const cmToFeetInches = (cm) => {
                const num = parseFloat(cm);
                if (isNaN(num) || num <= 0) return '';
                const totalInches = num / 2.54;
                let feet = Math.floor(totalInches / 12);
                let inches = Math.round(totalInches - (feet * 12));
                if (inches === 12) { feet += 1; inches = 0; }
                return `${feet} ft ${inches} in`;
            };

            const updatePreview = (val) => {
                const txt = cmToFeetInches(val);
                preview.textContent = txt ? `≈ ${txt}` : '';
            };

            // initial value
            if ((visitHeightInput.value || '').trim() !== '') updatePreview(visitHeightInput.value);
            // live update on input
            visitHeightInput.addEventListener('input', (e) => updatePreview(e.target.value));
        }
    });
})();
