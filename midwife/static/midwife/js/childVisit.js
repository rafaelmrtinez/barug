(() => {

    document.getElementById("childForm").addEventListener("submit", (e) => {
        
        e.preventDefault();

        const isConfirmed = confirm("Click CANCEL to review. Click OK to submit.");
        
        if (!isConfirmed) {
            return;
        }

        //  child id for quertying the child health record
        

        // child immunozations 
        // const bcgD0 = document.getElementById("bcg_d0").value;
        // const bcgD1 = document.getElementById("bcg_d1").value;
        // const bcgD2 = document.getElementById("bcg_d2").value;
        // const bcgD3 = document.getElementById("bcg_d3").value;

        // <th>Hep. B</th>
        // <td><input name="wt24h_hepb" type="number" step="0.01" class="form-control" placeholder="kg"></td>
        // <td><input name="hepb_d0" id="hepb_d0" type="date" class="form-control"></td>
        // <td><input name="hepb_d1" id="hepb_d1" type="date" class="form-control"></td>
        // <td><input name="hepb_d2" id="hepb_d2" type="date" class="form-control"></td>
        // <td><input name="hepb_d3" id="hepb_d3" type="date" class="form-control"></td>
        // const hepbD0 = document.getElementById("hepb_d0").value;
        // const hepbD1 = document.getElementById("hepb_d1").value;
        // const hepbD2 = document.getElementById("hepb_d2").value;
        // const hepbD3 = document.getElementById("hepb_d3").value;

        // <th>PCV</th>
        // <td><input name="wt24h_pcv" type="number" step="0.01" class="form-control" placeholder="kg"></td>
        // <td><input name="pcv_d0" id="pcv_d0" type="date" class="form-control"></td>
        // <td><input name="pcv_d1" id="pcv_d1" type="date" class="form-control"></td>
        // <td><input name="pcv_d2" id="pcv_d2" type="date" class="form-control"></td>
        // <td><input name="pcv_d3" id="pcv_d3" type="date" class="form-control"></td>

        // const pcvD0 = document.getElementById("pcv_d0").value;
        // const pcvD1 = document.getElementById("pcv_d1").value;
        // const pcvD2 = document.getElementById("pcv_d2").value;
        // const pcvD3 = document.getElementById("pcv_d3").value;

        // <th>OPV</th>
        // <td><input name="wt24h_opv" type="number" step="0.01" class="form-control" placeholder="kg"></td>
        // <td><input name="opv_d0" id="opv_d0" type="date" class="form-control"></td>
        // <td><input name="opv_d1" id="opv_d1" type="date" class="form-control"></td>
        // <td><input name="opv_d2" id="opv_d2" type="date" class="form-control"></td>
        // <td><input name="opv_d3" id="opv_d3" type="date" class="form-control"></td>
        
        // const opvD0 = document.getElementById("opv_d0").value;
        // const opvD1 = document.getElementById("opv_d1").value;
        // const opvD2 = document.getElementById("opv_d2").value;
        // const opvD3 = document.getElementById("opv_d3").value;

        // <th>AMV (Measles)</th>
        // <td><input name="wt24h_amv" type="number" step="0.01" class="form-control" placeholder="kg"></td>
        // <td><input name="amv_d0" id="amv_d0" type="date" class="form-control"></td>
        // <td><input name="amv_d1" id="amv_d1" type="date" class="form-control"></td>
        // <td><input name="amv_d2" id="amv_d2" type="date" class="form-control"></td>
        // <td><input name="amv_d3" id="amv_d3" type="date" class="form-control"></td>

        // const amvD0 = document.getElementById("amv_d0").value;
        // const amvD1 = document.getElementById("amv_d1").value;
        // const amvD2 = document.getElementById("amv_d2").value;
        // const amvD3 = document.getElementById("amv_d3").value;

        // <th>Pentavalent</th>
        // <td><input name="wt24h_penta" type="number" step="0.01" class="form-control" placeholder="kg"></td>
        // <td><input name="penta_d0" id="penta_d0" type="date" class="form-control"></td>
        // <td><input name="penta_d1" id="penta_d1" type="date" class="form-control"></td>
        // <td><input name="penta_d2" id="penta_d2" type="date" class="form-control"></td>
        // <td><input name="penta_d3" id="penta_d3" type="date" class="form-control"></td>

        // const pentaD0 = document.getElementById("penta_d0").value;
        // const pentaD1 = document.getElementById("penta_d1").value;
        // const pentaD2 = document.getElementById("penta_d2").value;
        // const pentaD3 = document.getElementById("penta_d3").value;

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

        // console.log("Monitoring Data:", monitoringData);
        // console.log("Immunizations Data:", JSON.parse(immunizationsJson));
        // console.log("isChildProtectedAtBirth:", isChildProtectedAtBirth);
        // console.log("assessedDate:", assessedDate);
        // console.log("anemicSeen:", anemicSeen);
        // console.log("anemicGivenIron:", anemicGivenIron);
        // console.log("seen26Months:", seen26Months);
        // console.log("seen26MonthsGivenIron:", seen26MonthsGivenIron);
        // console.log("vitaminA1:", vitaminA1);
        // console.log("vitaminA2:", vitaminA2);
        // console.log("vitaminA3:", vitaminA3);
        // console.log("ironStartedDate:", ironStartedDate);
        // console.log("ironCompletedDate:", ironCompletedDate);
        // console.log("ironSupplementDateStarted:", ironSupplementDateStarted);
        // console.log("ironSupplementDateCompleted:", ironSupplementDateCompleted);
        // console.log("vitaminsDose:", vitaminsDose);
        // console.log("vitaminDateGiven:", vitaminDateGiven);


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
                        "anemic_seen": anemicSeen,
                        "anemic_given_iron": anemicGivenIron,
                        "birth_weight": birth_weight,
                        "is_low_birth_weight": birth_weight && parseFloat(birth_weight) < 2.5 ? true : false,
                        "iron_seen_2_6_mos": seen26Months,
                        "iron_given_2_6_mos": seen26MonthsGivenIron,
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
                console.error("Error:", errorData);
                alert("An error occurred: " + (errorData.message || "Unknown error"));
                return;
            }

            const data = await res.json();
            console.log("Success:", data);
            alert("Data submitted successfully!");
        } catch (error) {
            console.error("Error:", error);
        }
    }

    sendData();

    })
    
})();