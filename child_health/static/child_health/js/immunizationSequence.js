(() => {
    // static/child_health/js/immunizationSequence.js
    document.addEventListener('DOMContentLoaded', function () {
        const vaccineGroups = {
            bcg: ['bcg_24hr', 'bcg_1st', 'bcg_2nd', 'bcg_3rd'],
            hepbv: ['hepbv_24hr', 'hepbv_1st', 'hepbv_2nd', 'hepbv_3rd'],
            pcv: ['pcv_24hr', 'pcv_1st', 'pcv_2nd', 'pcv_3rd'],
            opv: ['opv_24hr', 'opv_1st', 'opv_2nd', 'opv_3rd'],
            amv: ['amv_24hr', 'amv_1st', 'amv_2nd', 'amv_3rd'],
            pentavalent: ['pentavalent_24hr', 'pentavalent_1st', 'pentavalent_2nd', 'pentavalent_3rd']
        };

        Object.entries(vaccineGroups).forEach(([vaccine, ids]) => {
            const elements = ids.map(id => document.getElementById(`id_${id}`)).filter(Boolean);

            // Initial state check
            updateSequence(elements);

            // Add listeners
            elements.forEach((el, idx) => {
                el.addEventListener('change', () => updateSequence(elements));
            });
        });

        function updateSequence(elements) {
            elements.forEach((el, idx) => {
                if (idx === 0) {
                    // The first checkbox is always enabled
                    el.disabled = false;
                } else {
                    // Disable this if any previous checkbox is unchecked
                    const allPreviousChecked = elements.slice(0, idx).every(prev => prev.checked);
                    el.disabled = !allPreviousChecked;

                    // Auto-uncheck invalid selections
                    if (!allPreviousChecked && el.checked) {
                        el.checked = false;
                    }
                }
            });
        }
    });

})();