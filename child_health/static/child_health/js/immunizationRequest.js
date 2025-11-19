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
            CustomToast && CustomToast.show && CustomToast.show(`${immunizationName}: 2nd dose entered but 1st dose missing.`, { type: 'error' });
            return false;
        }
        if (d3 && !d2) {
            CustomToast && CustomToast.show && CustomToast.show(`${immunizationName}: 3rd dose entered but 2nd dose missing.`, { type: 'error' });
            return false;
        }
        if (d1 && d2 && d2 < d1) {
            CustomToast && CustomToast.show && CustomToast.show(`${immunizationName}: 2nd dose date cannot be before 1st dose.`, { type: 'error' });
            return false;
        }
        if (d2 && d3 && d3 < d2) {
            CustomToast && CustomToast.show && CustomToast.show(`${immunizationName}: 3rd dose date cannot be before 2nd dose.`, { type: 'error' });
            return false;
        }
        return true;
    };

    // --- POST helper ---
    const IMMUNIZATION_URL = "/child-health/child-immunization/request/";

    const _extractSuccessText = (body) => {
        if (body == null) return null;
        // if server returned a plain string, use it
        if (typeof body === 'string') return body;
        // prefer message field when it's textual
        if (body && body.message) {
            if (typeof body.message === 'string') return body.message;
            if (Array.isArray(body.message)) {
                // try to find any non-numeric textual content
                const flat = body.message.flat(Infinity);
                const textParts = flat.filter(el => typeof el === 'string');
                if (textParts.length) return textParts.join(' ');
                // no textual parts found — don't return numeric ids
                return null;
            }
        }
        return null;
    };

    const _extractErrorMsg = (body) => {
        if (!body) return 'Submission failed (no error provided).';
        if (typeof body === 'string') return body;
        if (typeof body.message === 'string') return body.message;
        if (Array.isArray(body.message)) return JSON.stringify(body.message);
        if (typeof body.error === 'string') return body.error;
        return 'Submission failed (no error provided).';
    };

    const _isNestedNumericMessage = (body) => {
        if (!body) return false;
        const msg = body.message;
        if (!Array.isArray(msg)) return false;
        // flatten and check that at least one numeric exists and no textual parts
        const flat = msg.flat(Infinity);
        const hasNumber = flat.some(el => typeof el === 'number');
        const hasText = flat.some(el => typeof el === 'string');
        return hasNumber && !hasText;
    };

    const postImmunizationData = async (payload, immunizationName) => {
        try {
            // Perform request locally so this module shows its own toasts
            const response = await fetch(IMMUNIZATION_URL, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                    'Accept': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            let data = null;
            try { data = await response.json(); } catch (_) { data = null; }

            if (response.ok) {
                // If server returned a textual message, show it; if message is numeric-only (e.g. [[62]]), show generic success
                const text = _extractSuccessText(data);
                if (text) {
                    CustomToast && CustomToast.show && CustomToast.show(text, { type: 'success' });
                } else {
                    CustomToast && CustomToast.show && CustomToast.show(`${immunizationName} data submitted successfully!`, { type: 'success' });
                }
                return;
            }

            const err = _extractErrorMsg(data);
            CustomToast && CustomToast.show && CustomToast.show(`${immunizationName} submission failed: ${err}`, { type: 'error' });
        } catch (error) {
            console.error(`Error submitting ${immunizationName}:`, error);
            CustomToast && CustomToast.show && CustomToast.show(`Failed to submit ${immunizationName}. Please try again.`, { type: 'error' });
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
                CustomToast && CustomToast.show && CustomToast.show(`No immunization date provided for ${immunizationName}.`, { type: 'error' });
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
