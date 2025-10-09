(() => {

    document.addEventListener("DOMContentLoaded", function () {

        const record_id = document.getElementById("record_id").value;

        if (!record_id) {
            return;
        }

        const fetchData = async () => {
            try {
                const response = await fetch(`/midwife/maternal-record/${record_id}/`);
                const res = await response.json();
                if (!response.ok) {
                    console.error("Failed to fetch maternal record.");
                    return;
                }

                const obj = JSON.parse(res.message);
                console.log("Maternal Record Response:", obj);

                // target tbody
                const tbody = document.getElementById("visitsTbody");
                tbody.innerHTML = ""; // clear previous rows

                // helper function
                const createRow = (visit) => {
                    const dangerBadge = visit.danger_signs
                        ? `<span class="badge text-bg-danger">Flag</span>`
                        : `<span class="badge text-bg-success">None</span>`;

                    return `
    <tr>
      <td>${visit.visit_date || "—"}</td>
      <td>${visit.trimester_stage_name || visit.trimester || "—"}</td>
      <td>${visit.weight ? visit.weight + " kg" : "—"}</td>
      <td>${dangerBadge}</td>
      <td class="text-end">
        <button class="btn btn-outline-secondary btn-sm" disabled>
          <i class="bi bi-eye"></i>
        </button>
      </td>
    </tr>`;
                };

                // current record (always first)
                if (obj.current_materrnal_record) {
                    tbody.insertAdjacentHTML("beforeend", createRow(obj.current_materrnal_record));
                }

                // append history (if any)
                if (Array.isArray(obj.record_history) && obj.record_history.length) {
                    obj.record_history.forEach((v) => {
                        tbody.insertAdjacentHTML("beforeend", createRow(v));
                    });
                }

                // fallback for empty
                if (!tbody.children.length) {
                    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">No visits yet.</td></tr>`;
                }


                document.getElementById("record_pname").textContent = obj.current_materrnal_record.full_name || "N/A";
                document.getElementById("mhr_number").textContent = obj.current_materrnal_record.maternal_record_id || "N/A";
                document.getElementById("family_no").textContent = obj.family_id || "N/A";
                document.getElementById("lmp").textContent = obj.current_materrnal_record.lmp || "N/A";
                document.getElementById("edd").textContent = obj.current_materrnal_record.edc || "N/A";
                document.getElementById("ep_delivery_plan").textContent = obj.current_materrnal_record.place_of_delivery_plan || "N/A";
                document.getElementById("ep_nbs_plan").textContent = obj.current_materrnal_record.new_born_screening_plan || "N/A";
                document.getElementById("h-val").textContent = obj.current_materrnal_record.height ? `${obj.current_materrnal_record.height} cm` : "N/A";
                document.getElementById("w-val").textContent = obj.current_materrnal_record.weight ? `${obj.current_materrnal_record.weight} kg` : "N/A";
                document.getElementById("an_bmi_stat").textContent = obj.current_materrnal_record.bmi_status_name ? obj.current_materrnal_record.bmi_status_name : "N/A";
                document.getElementById("lv_date").textContent = obj.previous_maternal_records ? obj.previous_maternal_records.visit_date : "N/A";
                document.getElementById("lv_trimester").textContent = obj.previous_maternal_records ? obj.previous_maternal_records.trimester_stage_name : "N/A";
                document.getElementById("lv_weight").textContent = obj.previous_maternal_records && obj.previous_maternal_records.weight ? `${obj.previous_maternal_records.weight} KG` : "N/A";
                document.getElementById("last-updated").textContent = `Last updated: ${obj.current_materrnal_record.visit_date ? obj.current_materrnal_record.visit_date : "N/A"}`;

            } catch (error) {
                console.error("Error fetching maternal record:", error);
            }
        }
        fetchData();
    })

})();