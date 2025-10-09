(() => {

    // Iuncomment lang kung mag debug kag binsan unsa.
    // document.addEventListener('DOMContentLoaded', function () {
    //     const id = document.getElementById("record_id").value;
    //     console.log(`Record ID: ${id}`);
    //     console.log(document.querySelector('input[name="csrfmiddlewaretoken"]').value);
    // });

    document.getElementById("visitForm").addEventListener("submit", function (e) {

        e.preventDefault();

        const id = document.getElementById("record_id").value;

        // Obstetric History
        const gravidaInput = document.getElementById('ob_gravida').value;
        const paraInput = document.getElementById('ob_para').value;
        const cbaInput = document.getElementById('ob_cba').value;
        const livingInput = document.getElementById('ob_living').value;
        const largeInput = document.getElementById('ob_large').value;
        const abortionsInput = document.getElementById('ob_abortions').value;
        const stillbirthsInput = document.getElementById('ob_stillbirths').value;

        // Previous Pregnancy Details
        const previousPregnancies = document.getElementById('prev_preg_json').value;

        // Medical History
        const mh_diabetesInput = document.getElementById('mh_diabetes').checked;
        const mh_htnInput = document.getElementById('mh_htn').checked;
        const mh_asthmaInput = document.getElementById('mh_asthma').checked;
        const mh_prev_illnessInput = document.getElementById('mh_prev_illness').value;
        const mh_prev_hospInput = document.getElementById('mh_prev_hosp').value;
        const mh_prev_compInput = document.getElementById('mh_prev_comp').value;

        // Checklist
        // Preeclampsia / Danger Signs
        const preeclampsiaSigns = document.getElementById("checklist_json").value;

        const deliveryPlan = document.getElementById('chk_delivery_plan').value;

        const nbsYes = document.getElementById('chk_nbs_yes').checked;
        const nbsNo = document.getElementById('chk_nbs_no').checked;

        const nbsPlan = nbsYes ? true : false;

        const ifaStart = document.getElementById('chk_ifa_start').value;
        const ifaDone = document.getElementById('chk_ifa_done').value;
        const dewormDate = document.getElementById('chk_deworm_date').value;

        const obstetricRisk = document.getElementById('risk_obstetric').value;
        const medicalRisk = document.getElementById('risk_medical').value;

        riskArray = [obstetricRisk, medicalRisk];

        // Visit Basics
        const visitDate = document.getElementById('visit_date').value;
        const gaWeeks = document.getElementById('ga_weeks').value;

        const bpSys = document.getElementById('bp_sys').value;
        const bpDia = document.getElementById('bp_dia').value;
        const weightKg = document.getElementById('weight_kg').value;
        const fundicHeightCm = document.getElementById('fundic_height_cm').value;
        const fhrBpm = document.getElementById('fhr_bpm').value;
        const assessedById = document.getElementById('assessed_by_id').value;
        const notes = document.getElementById('notes').value;
        const lmp = document.getElementById('lmp').value;
        const edc = document.getElementById('edc').value;

        const bmi = (weightKg && fundicHeightCm) ? (weightKg / ((fundicHeightCm/100)**2)).toFixed(2) : null;
        let bmiStatusId = null

        // TODO: Should be computed in backend
        if (bmi < 18.5) {
            bmiStatusId = 1; 
        } else if (bmi >= 18.5 && bmi < 24.9) {
            bmiStatusId = 2; 
        } else if (bmi >= 25 && bmi < 29.9) {
            bmiStatusId = 3; 
        }

        // Danger Signs
        const dangerSigns = document.getElementById("danger_signs_json").value;

        const labs = document.getElementById("labs_json").value;
        const tt = document.getElementById("tt_json").value;
        const supplements = document.getElementById("supplements_json").value;

        const trimesterStageId = document.getElementById('trimester_stage_id').value;
        
        const targetTrimesterElement = document.getElementById('triBadgeInline');
        const trimesterStageText = targetTrimesterElement.textContent.trim();

        const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]').value;

        const parsedPreeclampsiaSigns = JSON.parse(preeclampsiaSigns);

        // console.log(`Obstetric History: ${gravidaInput}, ${paraInput}, ${cbaInput}, ${livingInput}, ${largeInput}, ${abortionsInput}, ${stillbirthsInput}`);
        // console.log(`Previous Pregnancies: ${previousPregnancies}`);
        // console.log(`Medical History: ${mh_diabetesInput}, ${mh_htnInput}, ${mh_asthmaInput}, ${mh_prev_illnessInput}, ${mh_prev_hospInput}, ${mh_prev_compInput}`);
        // console.log(`Checklist: ${preeclampsiaSigns}`);
        // console.log(`Checklist II: ${deliveryPlan}, ${nbsPlan}, ${ifaStart}, ${ifaDone}, ${dewormDate}`);
        // console.log(`Risk Codes — Medical Conditions: ${riskPrevCs}, ${riskThreeMiscarriages}, ${riskPph}, ${riskTb}, ${riskHd}, ${riskDm}, ${riskAsthma}, ${riskGoiter}`);
        // console.log(`Visit Basics: ${visitDate}, ${gaWeeks}, ${bpSys}, ${bpDia}, ${weightKg}, ${fundicHeightCm}, ${fhrBpm}, ${assessedById}, ${notes}`);
        // console.log(`Danger Signs: ${dangerSigns}`);
        console.log(`Labs: ${labs}`);
        // console.log(`TT: ${tt}`);
        // console.log(`Supplements: ${supplements}`);
        
        const sendData = async () => {
            try {
                const url = `/midwife/anc-care/`;
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({
                        p_maternal_record_id: id,
                        p_visit_date: visitDate,
                        p_trimester_stage_id: trimesterStageId,
                        p_prev_illness: mh_prev_illnessInput,
                        p_prev_hospitalization: mh_prev_hospInput,
                        p_prev_preg_complication: mh_prev_compInput,
                        p_num_children_born_alive: cbaInput,
                        p_num_children_living: livingInput,
                        p_num_abortion: abortionsInput,
                        p_num_stillbirth: stillbirthsInput,
                        p_num_large_babies: largeInput,
                        p_has_diabetes: mh_diabetesInput,
                        p_prev_pregs: previousPregnancies,
                        p_weight: weightKg,
                        p_height: fundicHeightCm,
                        p_bmi_status_id: bmiStatusId,
                        p_newborn_plan: nbsPlan,
                        p_delivery_plan: deliveryPlan,
                        p_gravida: gravidaInput,
                        p_para: paraInput,
                        p_is_fullterm: gaWeeks >= 37 ? true : false,
                        p_is_preterm: gaWeeks < 37 ? true : false,
                        p_lmp: lmp,
                        p_edc: edc,
                        p_lab_results: labs,
                        p_checklist_item_ids: parsedPreeclampsiaSigns["danger_flags"],
                        p_risk_category_ids: riskArray,
                        p_tt_vaccines: tt,
                        p_iron_start_date: ifaStart,
                        p_iron_end_date: ifaDone,
                        p_deworming_date: dewormDate,
                    })
                });
                const res = await response.json();
                if (!response.ok) {
                    alert(`Error: ${res.error}`);
                    return;
                }
                console.log(res);
                alert("ANC visit submitted successfully.");
                window.location.reload();

            } catch {
                alert("Failed to submit ANC visit. Please try again.");
            }

        }

        sendData();

    });

})();