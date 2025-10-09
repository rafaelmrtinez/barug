(() => {

    const childIdField = document.getElementById('child_id');

    if (!childIdField) {
        return;
    }

    const fetchData = async (childId) => {
        try {
            const response = await fetch(`/midwife/maternal-child/${childId}`);

            const data = await response.json();

            if (!response.ok) {
                console.error('Error fetching data:', data.error);
                return;
            }

            const feeding_type = validateFeedingType(data);

            document.getElementById("feeding_type").value = feeding_type;
            document.getElementById("nbs_referral_date").value = data.message.referred_newborn_screening_date || null;

            renderBreastFeedingDates(data);

            document.getElementById("cpab").value = data.message.is_protected_at_birth ? "yes" : "no" || "-";
            document.getElementById("cpab_date_assessed").value = data.message.date_assessed || null;

            const tt_status = validateTTVaccineStats(data);

            document.getElementById("tt_status_mother").value = tt_status || "-";
            document.getElementById("iron_started").value = data.message.date_started || null;
            document.getElementById("iron_completed_date").value = data.message.date_completed || null;

            renderVitamins(data);

            const visitTbody = document.getElementById("visitTbody");
            visitTbody.innerHTML = "";

            if (data.message.monitoring_logs && data.message.monitoring_logs.length > 0) {
                data.message.monitoring_logs.forEach(log => {
                    const row = document.createElement("tr");

                    row.innerHTML = `
                        <td>${log.check_date || "-"}</td>
                        <td>${log.age ?? "-"}</td>
                        <td>${log.weight ?? "-"}</td>
                        <td>${log.temperature ?? "-"}</td>
                        <td>${log.height ?? "-"}</td>
                        <td>${log.findings ?? "-"}</td>
                        <td>${log.notes ?? "-"}</td>
                        <td></td>
                    `;

                    visitTbody.appendChild(row);
                });

                immunizationRenderer(data);
            } else {
                const emptyRow = document.createElement("tr");
                emptyRow.innerHTML = `<td colspan="8" class="text-center">No monitoring logs available</td>`;
                visitTbody.appendChild(emptyRow);
            }

        } catch {
            console.error('Error fetching data');
        }

        function immunizationRenderer(data) {
            if (data.message.immunizations && data.message.immunizations.length > 0) {

                const immRows = document.querySelectorAll("#immTbody tr[data-vac]");
                immRows.forEach(row => {
                    const vacType = row.getAttribute("data-vac");
                    row.querySelectorAll(`input[id^='${vacType}_d']`).forEach(input => input.value = "");
                    const wtField = row.querySelector(`input[name='wt24h_${vacType}']`);
                    if (wtField) wtField.value = "";
                });

                data.message.immunizations.forEach(imm => {
                    const typeKey = imm.immunization_type.toLowerCase();
                    const row = document.querySelector(`#immTbody tr[data-vac='${typeKey}']`);
                    if (!row) return;

                    imm.dates_given.forEach((date, idx) => {
                        const dateField = row.querySelector(`#${typeKey}_d${idx}`);
                        if (dateField) dateField.value = date;
                    });
                });

            } else {
                console.warn("No immunization data available");
            }
        }

        function renderVitamins(data) {
            const vitamins_date_given = ["vita_1", "vita_2", "vita_3"];
            const vitamin_dose_given = ["vitamin_dose_1", "vitamin_dose_2", "vitamin_dose_3"];

            for (let i = 0; i < data.message.vitamins_given?.length; i++) {
                document.getElementById(vitamins_date_given[i]).value = data.message.vitamins_given[i].date_given || null;
                document.getElementById(vitamin_dose_given[i]).value = data.message.vitamins_given[i].dose_no || null;
            }
        }

        function validateTTVaccineStats(data) {
            let tt_status = null;
            const mother_tt_status = data.message.latest_tt_vaccine;

            if (mother_tt_status === "TT1") {
                tt_status = 1;
            } else if (mother_tt_status === "TT2") {
                tt_status = 2;
            } else if (mother_tt_status === "TT3") {
                tt_status = 3;
            } else if (mother_tt_status === "TT4") {
                tt_status = 4;
            } else if (mother_tt_status === "TT5") {
                tt_status = 5;
            } else if (mother_tt_status === "FIM") {
                tt_status = 6;
            } else {
                tt_status = null;
            }
            return tt_status;
        }

        function renderBreastFeedingDates(data) {
            for (let i = 0; i < data.message.breastfeeding_check_dates?.length; i++) {
                document.getElementById(`bf_check_${i + 1}`).value = data.message.breastfeeding_check_dates[i] || null;
            }
        }

        function validateFeedingType(data) {
            let feeding_type = null;

            if (data.message.feeding_type_name === "EXCLUSIVE BREASTFEEDING") {
                feeding_type = 1;
            } else if (data.message.feeding_type_name === "MIXED FEEDING") {
                feeding_type = 2;
            } else if (data.message.feeding_type_name === "FORMULA FEEDING") {
                feeding_type = 3;
            } else {
                feeding_type = null;
            }
            return feeding_type;
        }
    }
    const observer = new MutationObserver((mutationsList) => {
        for (const mutation of mutationsList) {
            if (mutation.attributeName === "value") {
                const newValue = childIdField.value;
                fetchData(newValue);
            }
        }
    });

    observer.observe(childIdField, {
        attributes: true,
        attributeFilter: ["value"]
    });

    // Optionally trigger an initial fetch if already set
    if (childIdField.value) {
        fetchData(childIdField.value);
    }
})();