(() => {

    document.getElementById("pentavalentImmunizationForm").addEventListener("submit", function (event) {
        event.preventDefault();

        const twentyFourHtInput = document.getElementById("id_pentavalent_24hr").checked;

        if (twentyFourHtInput) {
            return;
        }

        const firstDoseInput = document.getElementById("id_pentavalent_1st").checked;
        const secondDoseInput = document.getElementById("id_pentavalent_2nd").checked;
        const thirdDoseInput = document.getElementById("id_pentavalent_3rd").checked;
        const recordId = document.getElementById("child_health_record_id").value;
        const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]').value;

        const immunizationType = 6;
        let immunizationStage = null;
        
        const dataArray = [
            { field: "pentavalent_24hr", value: twentyFourHtInput },
            { field: "pentavalent_1st", value: firstDoseInput },
            { field: "pentavalent_2nd", value: secondDoseInput },
            { field: "pentavalent_3rd", value: thirdDoseInput }
        ]

        for (const item of dataArray.reverse()) {
            if(item.value) {
                if (item.field == "pentavalent_3rd") {
                    immunizationStage = 4;
                    break;
                } else if (item.field == "pentavalent_2nd") {
                    immunizationStage = 3;
                    break;
                } else if (item.field == "pentavalent_1st") {
                    immunizationStage = 2;
                    break;
                } else {
                    confirm("No immunization stage selected for Pentavalent.");
                    return;
                }
            }
        }

        const sendPayload = async () => {
            try {
                const response = await fetch("/child-health/child-immunization/request/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    },
                    body: JSON.stringify({
                        pentavalent_24hr: twentyFourHtInput,
                        child_health_record_id: recordId,
                        immunization_type_id: immunizationType,
                        immunization_stage_given_id: immunizationStage
                    })
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    confirm(`Pentavalent Immunization Submission: ${errorData.message}`);
                    window.location.href = window.location.href;
                    return;
                }
                const responseData = await response.json();
                if (!responseData.message) {
                    console.error("Unexpected response format:");
                    alert("Failed to submit Pentavalent Immunization Data. Please try again.");
                    return;
                }
                alert("Pentavalent Immunization Data submitted successfully!");
            } catch (error) {
                console.error("Error submitting Pentavalent Immunization Data:", error);
                alert("Failed to submit Pentavalent Immunization Data. Please try again.");
            }
        }
        sendPayload();
    });

    document.getElementById("amvImmunizationForm").addEventListener("submit", function (event) {
        event.preventDefault();
        
        const twentyFourHtInput = document.getElementById("id_amv_24hr").checked;
        if (twentyFourHtInput) {
            return;
        }

        const firstDoseInput = document.getElementById("id_amv_1st").checked;
        const secondDoseInput = document.getElementById("id_amv_2nd").checked;
        const thirdDoseInput = document.getElementById("id_amv_3rd").checked;
        const recordId = document.getElementById("child_health_record_id").value;
        const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]').value;

        const immunizationType = 5;
        let immunizationStage = null;

        const dataArray = [
            { field: "amv_24hr", value: twentyFourHtInput },
            { field: "amv_1st", value: firstDoseInput },
            { field: "amv_2nd", value: secondDoseInput },
            { field: "amv_3rd", value: thirdDoseInput }
        ]

        for (const item of dataArray.reverse()) {
            if(item.value) {
                if (item.field == "amv_3rd") {
                    immunizationStage = 4;
                    break;
                } else if (item.field == "amv_2nd") {
                    immunizationStage = 3;
                    break;
                } else if (item.field == "amv_1st") {
                    immunizationStage = 2;
                    break;
                } else {
                    confirm("No immunization stage selected for AMV.");
                    return;
                }
            }
        }

        const sendPayload = async () => {
            try {
                const response = await fetch("/child-health/child-immunization/request/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    },
                    body: JSON.stringify({
                        amv_24hr: twentyFourHtInput,
                        child_health_record_id: recordId,
                        immunization_type_id: immunizationType,
                        immunization_stage_given_id: immunizationStage
                    })
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    confirm(`AMV Immunization Submission: ${errorData.message}`);
                    window.location.href = window.location.href;
                    return;
                }
                const responseData = await response.json();
                if (!responseData.message) {
                    console.error("Unexpected response format:");
                    alert("Failed to submit AMV Immunization Data. Please try again.");
                    return;
                }
                alert("AMV Immunization Data submitted successfully!");
            } catch (error) {
                console.error("Error submitting AMV Immunization Data:", error);
                alert("Failed to submit AMV Immunization Data. Please try again.");
            }
        }
        sendPayload();
    });

    document.getElementById("opvImmunizationForm").addEventListener("submit", function (event) {
        event.preventDefault();

        const twentyFourHtInput = document.getElementById("id_opv_24hr").checked;

        if (twentyFourHtInput) {
            return;
        }

        const firstDoseInput = document.getElementById("id_opv_1st").checked;
        const secondDoseInput = document.getElementById("id_opv_2nd").checked;
        const thirdDoseInput = document.getElementById("id_opv_3rd").checked;
        const recordId = document.getElementById("child_health_record_id").value;
        const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]').value;

        const immunizationType = 4;
        let immunizationStage = null;

        const dataArray = [
            { field: "opv_24hr", value: twentyFourHtInput },
            { field: "opv_1st", value: firstDoseInput },
            { field: "opv_2nd", value: secondDoseInput },
            { field: "opv_3rd", value: thirdDoseInput }
        ]

        for (const item of dataArray.reverse()) {
            if(item.value) {
                if (item.field == "opv_3rd") {
                    immunizationStage = 4;
                    break;
                } else if (item.field == "opv_2nd") {
                    immunizationStage = 3;
                    break;
                } else if (item.field == "opv_1st") {
                    immunizationStage = 2;
                    break;
                } else {
                    confirm("No immunization stage selected for OPV.");
                    return;
                }
            }
        }

        const sendPayload = async () => {
            try {
                const response = await fetch("/child-health/child-immunization/request/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    },
                    body: JSON.stringify({
                        opv_24hr: twentyFourHtInput,
                        child_health_record_id: recordId,
                        immunization_type_id: immunizationType,
                        immunization_stage_given_id: immunizationStage
                    })
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    confirm(`OPV Immunization Submission: ${errorData.message}`);
                    window.location.href = window.location.href;
                    return;
                }
                const responseData = await response.json();
                if (!responseData.message) {
                    console.error("Unexpected response format:");
                    alert("Failed to submit OPV Immunization Data. Please try again.");
                    return;
                }
                alert("OPV Immunization Data submitted successfully!");
            } catch (error) {
                console.error("Error submitting OPV Immunization Data:", error);
                alert("Failed to submit OPV Immunization Data. Please try again.");
            }
        }
        sendPayload();
    });

    document.getElementById("pcvImmunizationForm").addEventListener("submit", function (event) {
        event.preventDefault();

        const twentyFourHtInput = document.getElementById("id_pcv_24hr").checked;

        if (twentyFourHtInput) {
            return;
        }

        const firstDoseInput = document.getElementById("id_pcv_1st").checked;
        const secondDoseInput = document.getElementById("id_pcv_2nd").checked;
        const thirdDoseInput = document.getElementById("id_pcv_3rd").checked;
        const recordId = document.getElementById("child_health_record_id").value;
        const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]').value;

        const immunizationType = 3;
        let immunizationStage = null;

        const dataArray = [
            { field: "pcv_24hr", value: twentyFourHtInput },
            { field: "pcv_1st", value: firstDoseInput },
            { field: "pcv_2nd", value: secondDoseInput },
            { field: "pcv_3rd", value: thirdDoseInput }
        ]

        for (const item of dataArray.reverse()) {
            if(item.value) {
                if (item.field == "pcv_3rd") {
                    immunizationStage = 4;
                    break;
                } else if (item.field == "pcv_2nd") {
                    immunizationStage = 3;
                    break;
                } else if (item.field == "pcv_1st") {
                    immunizationStage = 2;
                    break;
                } else {
                    confirm("No immunization stage selected for PCV.");
                    return;
                }
            }
        }

        const sendPayload = async () => {
            try {
                const response = await fetch("/child-health/child-immunization/request/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    },
                    body: JSON.stringify({
                        hepbv_24hr: twentyFourHtInput,
                        child_health_record_id: recordId,
                        immunization_type_id: immunizationType,
                        immunization_stage_given_id: immunizationStage
                    })
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    confirm(`PCV Immunization Submission: ${errorData.message}`);
                    window.location.href = window.location.href;
                    return;
                }
                const responseData = await response.json();
                if (!responseData.message) {
                    console.error("Unexpected response format:");
                    alert("Failed to submit PCV Immunization Data. Please try again.");
                    return;
                }
                alert("PCV Immunization Data submitted successfully!");
            } catch (error) {
                console.error("Error submitting PCV Immunization Data:", error);
                alert("Failed to submit PCV Immunization Data. Please try again.");
            }
        }
        sendPayload();

    });

    document.getElementById("hepbvImmunizationForm").addEventListener("submit", function (event) {
        event.preventDefault();
        const twentyFourHtInput = document.getElementById("id_hepbv_24hr").checked;
        const recordId = document.getElementById("child_health_record_id").value;
        const immunizationType = 2;
        const immunizationStage = 1;
        const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]').value;
        const sendPayload = async () => {
            try {
                const response = await fetch("/child-health/child-immunization/request/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    },
                    body: JSON.stringify({
                        child_health_record_id: recordId,
                        immunization_type_id: immunizationType,
                        immunization_stage_given_id: immunizationStage
                    })
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    confirm(`HEP BV Immunization Submission: ${errorData.message}`);
                    window.location.href = window.location.href;
                    return;
                }
                const responseData = await response.json();
                if (!responseData.message) {
                    console.error("Unexpected response format:");
                    alert("Failed to submit Hep. BV Immunization Data. Please try again.");
                    return;
                }
                alert("Hep. BV Immunization Data submitted successfully!");
            } catch (error) {
                console.error("Error submitting Hep. BV Immunization Data:", error);
                alert("Failed to submit Hep. BV Immunization Data. Please try again.");
            }
        }
        sendPayload();
    });

    document.getElementById("bcgImmunizationForm").addEventListener("submit", function (event) {
        event.preventDefault();
        const twentyFourHtInput = document.getElementById("id_bcg_24hr").checked;
        const recordId = document.getElementById("child_health_record_id").value;
        const immunizationType = 1;
        const immunizationStage = 1;
        const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]').value;
        const sendPayload = async () => {
            try {
                const response = await fetch("/child-health/child-immunization/request/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    },
                    body: JSON.stringify({
                        child_health_record_id: recordId,
                        immunization_type_id: immunizationType,
                        immunization_stage_given_id: immunizationStage
                    })
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    confirm(`BCG Immunization Submission: ${errorData.message}`);
                    window.location.href = window.location.href;
                    return;
                }
                const responseData = await response.json();
                if (!responseData.message) {
                    console.error("Unexpected response format:");
                    alert("Failed to submit BCG Immunization Data. Please try again.");
                    return;
                }
                alert("BCG Immunization Data submitted successfully!");
            } catch (error) {
                console.error("Error submitting BCG Immunization Data:", error);
                alert("Failed to submit BCG Immunization Data. Please try again.");
            }
        }
        sendPayload();
    });
})();