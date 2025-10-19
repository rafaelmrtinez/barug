(() => {
    const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]').value;
    const recordId = document.getElementById("child_health_record_id").value;

    const getImmunizationStage = (prefix) => {
        const third = document.getElementById(`id_${prefix}_3rd`)?.checked;
        const second = document.getElementById(`id_${prefix}_2nd`)?.checked;
        const first = document.getElementById(`id_${prefix}_1st`)?.checked;

        if (third) return 4;
        if (second) return 3;
        if (first) return 2;
        return null;
    };

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
                confirm(`${immunizationName} Submission Failed: ${data.message}`);
                return;
            }

            if (!data.message) {
                alert(`Failed to submit ${immunizationName} data. Please try again.`);
                return;
            }

            alert(`${immunizationName} Data submitted successfully!`);
        } catch (error) {
            console.error(`Error submitting ${immunizationName}:`, error);
            alert(`Failed to submit ${immunizationName}. Please try again.`);
        }
    };

    const submitImmunization = ({ formId, prefix, typeId, immunizationName, stageOverride = null }) => {
        document.getElementById(formId).addEventListener("submit", async (event) => {
            event.preventDefault();

            const dose24hr = document.getElementById(`id_${prefix}_24hr`)?.checked;
            if (dose24hr && !stageOverride) return;

            const immunizationStage = stageOverride ?? getImmunizationStage(prefix);

            if (!immunizationStage) {
                confirm(`No immunization stage selected for ${immunizationName}.`);
                return;
            }

            console.log(`Submitting ${immunizationName} Data:`, {
                [`${prefix}_24hr`]: dose24hr,
                child_health_record_id: recordId,
                immunization_type_id: typeId,
                immunization_stage_given_id: immunizationStage
            });

            await postImmunizationData({
                [`${prefix}_24hr`]: dose24hr,
                child_health_record_id: recordId,
                immunization_type_id: typeId,
                immunization_stage_given_id: immunizationStage
            }, immunizationName);
        });
    };

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
