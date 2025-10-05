(() => {

    document.getElementById("childForm").addEventListener("submit", (e) => {
        
        e.preventDefault();

        //  child id for quertying the child health record
        // const childId = document.getElementById("child_id").value; 
        // const visitDate = document.getElementById("cpab_date_assessed").value;
        // const feedingType = document.getElementById("feeding_type").value;
        // const screeningReferal = document.getElementById("nbs_referral_date").value;

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

        const monitoringData = document.getElementById("visits_json").value;
        const immunizationsJson = document.getElementById("immunizations_json").value;

        const isChildProtectedAtBirth = document.getElementById("cpab").value;
        const assessedDate = document.getElementById("cpab_date_assessed").value;
        const anemicSeen = document.getElementById("anemic_seen_2_59").value;
        const anemicGivenIron = document.getElementById("anemic_given_2_59").value;
        const seen26Months = document.getElementById("seen_2_6").value;
        const seen26MonthsGivenIron = document.getElementById("iron_2_6").value;
        const vitaminA1 = document.getElementById("vita_1").value;
        const vitaminA2 = document.getElementById("vita_2").value;
        const vitaminA3 = document.getElementById("vita_3").value;
        const ironStartedDate = document.getElementById("iron_started").value;
        const ironCompletedDate = document.getElementById("completed_date").value;
        
        console.log("Monitoring Data:", monitoringData);
        console.log("Immunizations Data:", immunizationsJson);


        const sendData = async () => {
        try {
            const url = "/bhw/child-visit/";
            const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

            const res = await fetch(url, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrftoken,
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
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