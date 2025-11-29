// Live age display/calc for Visit Entry age input
// - Accepts a numeric age value (years, may be float)
// - If < 1 year, display in months (rounded)
// - If >= 1 year and < 5 years, display as "N year(s) old"
// - If >= 5 years, show validation error and mark invalid
// - Prevent form submission when invalid

(function () {
    function findAgeInput() {
        // common Django id
        let input = document.querySelector('#id_age');
        if (!input) {
            // fallback: find by name attribute inside visit-entry
            input = document.querySelector('#visit-entry input[name="age"]') || document.querySelector('input[name="age"]');
        }
        return input;
    }

    function toIntSafe(v) {
        try { return parseInt(v, 10); } catch (e) { return null; }
    }

    function showMessage(displayEl, errorEl, text, isError) {
        if (isError) {
            errorEl.textContent = text || '';
            displayEl.textContent = '';
        } else {
            errorEl.textContent = '';
            displayEl.textContent = text || '';
        }
    }

    function formatAge(value) {
        // value: string or number representing years (may be float)
        if (value === null || value === undefined || String(value).trim() === '') return { valid: true, text: '' };
        // try parse as float
        const num = parseFloat(String(value).trim());
        if (Number.isNaN(num) || num < 0) {
            return { valid: false, text: 'Invalid age value' };
        }

        // Only allow 0 <= age < 5 (we'll re-check after rounding)
        if (num < 0) {
            return { valid: false, text: 'Invalid age value' };
        }

        // If less than 1 year, show months (rounded)
        if (num < 1) {
            let months = Math.floor(num * 12);
            if (months < 1) months = 1; // display at least 1 month for very small decimals
            if (months === 1) return { valid: true, text: '1 month' };
            return { valid: true, text: `${months} months` };
        }

        // For 1 year and above, show "X year(s), Y month(s)" when applicable.
        let years = Math.floor(num);
        let months = Math.round((num - years) * 12);

        // handle rounding overflow (e.g., 1.999 -> months -> 12)
        if (months === 12) {
            years = years + 1;
            months = 0;
        }

        // Final sanity: disallow ages >= 5 years
        if (years >= 5) {
            return { valid: false, text: 'Only ages 0 to 4 years are allowed.' };
        }

        const yearPart = years === 1 ? '1 year' : `${years} years`;
        if (months === 0) {
            return { valid: true, text: years === 1 ? '1 year old' : `${years} years old` };
        }

        const monthPart = months === 1 ? '1 month' : `${months} months`;
        // Format: "1 year, 6 months old"
        return { valid: true, text: `${yearPart}, ${monthPart} old` };
    }

    function install() {
        const ageInput = findAgeInput();
        if (!ageInput) return;

        const displayEl = document.getElementById('age-display');
        const errorEl = document.getElementById('age-error');
        const visitForm = ageInput.closest('#visit-entry') || ageInput.closest('form');

        function update() {
            const v = ageInput.value;
            const res = formatAge(v);
            if (!res.valid) {
                showMessage(displayEl, errorEl, res.text, true);
                ageInput.classList.add('is-invalid');
                // disable submit button within form if present
                if (visitForm) {
                    const submit = visitForm.querySelector('button[type="submit"]');
                    if (submit) submit.disabled = true;
                }
            } else {
                showMessage(displayEl, errorEl, res.text, false);
                ageInput.classList.remove('is-invalid');
                if (visitForm) {
                    const submit = visitForm.querySelector('button[type="submit"]');
                    if (submit) submit.disabled = false;
                }
            }
        }

        // initial update
        update();

        ageInput.addEventListener('input', update);

        // prevent form submit when invalid
        if (visitForm) {
            visitForm.addEventListener('submit', function (ev) {
                const res = formatAge(ageInput.value);
                if (!res.valid) {
                    ev.preventDefault();
                    showMessage(displayEl, errorEl, res.text, true);
                    ageInput.focus();
                }
            });
        }
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', install);
    } else {
        install();
    }
})();
