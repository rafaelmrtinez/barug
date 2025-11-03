(() => {

    document.getElementById("childForm").addEventListener("submit", (e) => {
        
        e.preventDefault();

        const isConfirmed = confirm("Click CANCEL to review. Click OK to submit.");
        
        if (!isConfirmed) {
            return;
        }

        const childId = document.getElementById("child_id").value; 
        const visitDate = document.getElementById("cpab_date_assessed").value;
        const feedingType = document.getElementById("feeding_type").value;
        const screeningReferalDate = document.getElementById("nbs_referral_date").value;

        const monitoringData = document.getElementById("visits_json").value;
        const immunizationsJson = document.getElementById("immunizations_json").value;

        const isChildProtectedAtBirth = document.getElementById("cpab").value;
        const assessedDate = document.getElementById("cpab_date_assessed").value;
        const anemicSeen = document.getElementById("anemic_seen_2_59").value;
        const anemicGivenIron = document.getElementById("anemic_given_2_59").value;
        const seen26Months = document.getElementById("seen_2_6").value;
        const seen26MonthsGivenIron = document.getElementById("iron_2_6").value;

        const vitaminA1DateGiven = document.getElementById("vita_1").value;
        const vitaminA2DateGiven = document.getElementById("vita_2").value;
        const vitaminA3DateGiven = document.getElementById("vita_3").value;

        const vitaminA1Dose = document.getElementById("vitamin_dose_1").value;
        const vitaminA2Dose = document.getElementById("vitamin_dose_2").value;
        const vitaminA3Dose = document.getElementById("vitamin_dose_3").value;

        const ironSupplementDateStarted = document.getElementById("iron_started").value;
        const ironSupplementDateCompleted = document.getElementById("iron_completed_date").value;

        const birth_weight = document.getElementById("birth_weight").value;

        const bfCheck1 = document.getElementById("bf_check_1").value;
        const bfCheck2 = document.getElementById("bf_check_2").value;
        const bfCheck3 = document.getElementById("bf_check_3").value;
        const bfCheck4 = document.getElementById("bf_check_4").value;

        const sendData = async () => {
        try {
            const url = "/midwife/child-visit/";
            const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

            const res = await fetch(url, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrftoken,
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    p_child_id: childId,
                    p_child_record_id: null,
                    p_visit_date: visitDate,
                    p_feeding_type_id: feedingType,
                    p_referred_nbs_date: screeningReferalDate,
                    p_child_immunizations: immunizationsJson,
                    p_bf_checks: [{
                        "check_date": bfCheck1,
                        "date_order": 1
                    }, {
                        "check_date": bfCheck2,
                        "date_order": 2
                    }, {
                        "check_date": bfCheck3,
                        "date_order": 3
                    }, {
                        "check_date": bfCheck4,
                        "date_order": 4
                    }],
                    child_monitoring: monitoringData,
                    screening: {
                        "is_protected_at_birth": isChildProtectedAtBirth === "yes" ? true : false,
                        "date_assessed": assessedDate,
                        "anemic_seen": anemicSeen ? true : false,
                        "anemic_given_iron": anemicGivenIron ? true : false,
                        "birth_weight": birth_weight,
                        "is_low_birth_weight": birth_weight && parseFloat(birth_weight) < 2.5 ? true : false,
                        "iron_seen_2_6_mos": seen26Months ? true : false,
                        "iron_given_2_6_mos": seen26MonthsGivenIron ? true : false,
                    },
                    iron_supplements: {
                        "date_started": ironSupplementDateStarted,
                        "date_completed": ironSupplementDateCompleted
                    },
                    vitamins: [{
                        "dose_no": vitaminA1Dose,
                        "date_given": vitaminA1DateGiven,
                        "order": 1
                    }, {
                        "dose_no": vitaminA2Dose,
                        "date_given": vitaminA2DateGiven,
                        "order": 2
                    }, {
                        "dose_no": vitaminA3Dose,
                        "date_given": vitaminA3DateGiven,
                        "order": 3
                    }]
                })
            });

            if (!res.ok) {
                const errorData = await res.json();
                alert("An error occurred: " + (errorData.error || "Unknown error"));
                return;
            }

            alert("Data submitted successfully!");
            window.location.reload();
        } catch (error) {
            alert("An unexpected error occurred. Please try again later.");
        }
    }

    sendData();

    })
    
})();