(() => {

    document.getElementById("visitForm").addEventListener("submit", function (e) {

        e.preventDefault();

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
        const mh_prev_illnessInput = document.getElementById('mh_prev_illness').checked;
        const mh_prev_hospInput = document.getElementById('mh_prev_hosp').checked;
        const mh_prev_compInput = document.getElementById('mh_prev_comp').checked;

        // Checklist
        // Preeclampsia / Danger Signs
        const preeclampsiaSigns = document.getElementById("checklist_json").value;

        const deliveryPlan = document.getElementById('chk_delivery_plan').value;
        
        const nbsYes = document.getElementById('chk_nbs_yes').checked;
        const nbsNo = document.getElementById('chk_nbs_no').checked;
        
        let nbsPlan = nbsYes ? "YES" : "NO";

        const ifaStart = document.getElementById('chk_ifa_start').value;
        const ifaDone = document.getElementById('chk_ifa_done').value;
        const dewormDate = document.getElementById('chk_deworm_date').value;

        const riskPrevCs = document.getElementById('risk_prev_cs').checked;
        const riskThreeMiscarriages = document.getElementById('risk_three_miscarriages').checked;
        const riskPph = document.getElementById('risk_pph').checked;
        const riskTb = document.getElementById('risk_tb').checked;
        const riskHd = document.getElementById('risk_hd').checked;
        const riskDm = document.getElementById('risk_dm').checked;
        const riskAsthma = document.getElementById('risk_asthma').checked;
        const riskGoiter = document.getElementById('risk_goiter').checked;

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

        // Danger Signs
        const dangerSigns = document.getElementById("danger_signs_json").value;

        const labs = document.getElementById("labs_json").value;
        const tt = document.getElementById("tt_json").value;
        const supplements = document.getElementById("supplements_json").value;

        console.log(`Obstetric History: ${gravidaInput}, ${paraInput}, ${cbaInput}, ${livingInput}, ${largeInput}, ${abortionsInput}, ${stillbirthsInput}`);
        console.log(`Previous Pregnancies: ${previousPregnancies}`);
        console.log(`Medical History: ${mh_diabetesInput}, ${mh_htnInput}, ${mh_asthmaInput}, ${mh_prev_illnessInput}, ${mh_prev_hospInput}, ${mh_prev_compInput}`);
        console.log(`Checklist: ${preeclampsiaSigns}`);
        console.log(`Risk Codes — Obstetric: ${deliveryPlan}, ${nbsPlan}, ${ifaStart}, ${ifaDone}, ${dewormDate}`);
        console.log(`Risk Codes — Medical Conditions: ${riskPrevCs}, ${riskThreeMiscarriages}, ${riskPph}, ${riskTb}, ${riskHd}, ${riskDm}, ${riskAsthma}, ${riskGoiter}`);
        console.log(`Visit Basics: ${visitDate}, ${gaWeeks}, ${bpSys}, ${bpDia}, ${weightKg}, ${fundicHeightCm}, ${fhrBpm}, ${assessedById}, ${notes}`);
        console.log(`Danger Signs: ${dangerSigns}`);
        console.log(`Labs: ${labs}`);
        console.log(`TT: ${tt}`);
        console.log(`Supplements: ${supplements}`);


    });

})();