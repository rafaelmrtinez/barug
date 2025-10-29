(() => {
    const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]').value;
    const recordId = document.getElementById("child_health_record_id").value;

    // --- Utility: parse date safely ---
    const parseDate = (val) => val ? new Date(val) : null;

    // --- Determine the latest valid immunization stage ---
    const getImmunizationStage = (prefix) => {
        const d24 = parseDate(document.getElementById(`id_${prefix}_24hr`)?.value);
        const d1 = parseDate(document.getElementById(`id_${prefix}_1st`)?.value);
        const d2 = parseDate(document.getElementById(`id_${prefix}_2nd`)?.value);
        const d3 = parseDate(document.getElementById(`id_${prefix}_3rd`)?.value);

        // Return the latest non-null stage
        if (d3) return 4;
        if (d2) return 3;
        if (d1) return 2;
        if (d24) return 1;
        return null;
    };

    // --- Validate chronological order ---
    const validateDates = (prefix, immunizationName) => {
        const d1 = parseDate(document.getElementById(`id_${prefix}_1st`)?.value);
        const d2 = parseDate(document.getElementById(`id_${prefix}_2nd`)?.value);
        const d3 = parseDate(document.getElementById(`id_${prefix}_3rd`)?.value);

        if (d2 && !d1) {
            alert(`${immunizationName}: 2nd dose entered but 1st dose missing.`);
            return false;
        }
        if (d3 && !d2) {
            alert(`${immunizationName}: 3rd dose entered but 2nd dose missing.`);
            return false;
        }
        if (d1 && d2 && d2 < d1) {
            alert(`${immunizationName}: 2nd dose date cannot be before 1st dose.`);
            return false;
        }
        if (d2 && d3 && d3 < d2) {
            alert(`${immunizationName}: 3rd dose date cannot be before 2nd dose.`);
            return false;
        }
        return true;
    };

    // --- POST helper ---
    const postImmunizationData = async (payload, immunizationName) => {
        try {
            const response = await fetch("/child-health/child-immunization/request/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (!response.ok) {
                alert(`${immunizationName} submission failed: ${data.message || "Unknown error."}`);
                return;
            }

            alert(`${immunizationName} data submitted successfully!`);
        } catch (error) {
            console.error(`Error submitting ${immunizationName}:`, error);
            alert(`Failed to submit ${immunizationName}. Please try again.`);
        }
    };

    // --- Submission Handler ---
    const submitImmunization = ({ formId, prefix, typeId, immunizationName, stageOverride = null }) => {
        document.getElementById(formId).addEventListener("submit", async (event) => {
            event.preventDefault();

            // Get all date values
            const d24 = document.getElementById(`id_${prefix}_24hr`)?.value;
            const d1 = document.getElementById(`id_${prefix}_1st`)?.value;
            const d2 = document.getElementById(`id_${prefix}_2nd`)?.value;
            const d3 = document.getElementById(`id_${prefix}_3rd`)?.value;

            // Validate before submission
            if (!validateDates(prefix, immunizationName)) return;

            const immunizationStage = stageOverride ?? getImmunizationStage(prefix);

            if (!immunizationStage) {
                alert(`No immunization date provided for ${immunizationName}.`);
                return;
            }

            // Select latest date among filled
            const latestDate = [d3, d2, d1, d24].find(Boolean);

            await postImmunizationData({
                child_health_record_id: recordId,
                immunization_type_id: typeId,
                immunization_stage_given_id: immunizationStage,
                date_given: latestDate
            }, immunizationName);
        });
    };

    // --- Immunization forms ---
    const immunizations = [
        { formId: "bcgImmunizationForm", prefix: "bcg", typeId: 1, name: "BCG", stageOverride: 1 },
        { formId: "hepbvImmunizationForm", prefix: "hepbv", typeId: 2, name: "Hepatitis BV", stageOverride: 1 },
        { formId: "pcvImmunizationForm", prefix: "pcv", typeId: 3, name: "PCV" },
        { formId: "opvImmunizationForm", prefix: "opv", typeId: 4, name: "OPV" },
        { formId: "amvImmunizationForm", prefix: "amv", typeId: 5, name: "AMV" },
        { formId: "pentavalentImmunizationForm", prefix: "pentavalent", typeId: 6, name: "Pentavalent" }
    ];

    immunizations.forEach(im => submitImmunization({
        formId: im.formId,
        prefix: im.prefix,
        typeId: im.typeId,
        immunizationName: im.name,
        stageOverride: im.stageOverride
    }));
})();
