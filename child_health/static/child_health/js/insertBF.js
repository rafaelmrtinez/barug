(() => {

    document.getElementById("breastFeedingForm").addEventListener("submit", (event) => {

        event.preventDefault();

        const childId = document.getElementById("child_id").value;

        if (!childId) {
            alert("Unable to find child. Please refresh the page and try again.");
            return;
        }

        const typeOfFeeding = document.getElementById("id_type_of_feeding").value;
        const screeningDate = document.getElementById("id_referred_for_newborn_screening").value;

        if (!typeOfFeeding) {
            alert("Please select the type of feeding.");
            return;
        }

        if (!screeningDate) {
            alert("Please select the date for newborn screening.");
            return;
        }

        const validEntries = [];
        let counter = 1;

        for (let i = 1; i <= 10; i++) {
            const bfCheckDate = document.getElementById(`id_exclusive_bf_check_${i}`).value;
            if (bfCheckDate) {
                validEntries.push({ counter, bfCheckDate });
            }
            counter++;
        }

        const child_record_id = document.getElementById("id_child_record_id").value;

        // const bfCheckDate_1 = document.getElementById("id_exclusive_bf_check_1").value;
        // const bfCheckDate_2 = document.getElementById("id_exclusive_bf_check_2").value;
        // const bfCheckDate_3 = document.getElementById("id_exclusive_bf_check_3").value;
        // const bfCheckDate_4 = document.getElementById("id_exclusive_bf_check_4").value;
        // const bfCheckDate_5 = document.getElementById("id_exclusive_bf_check_5").value;
        // const bfCheckDate_6 = document.getElementById("id_exclusive_bf_check_6").value;
        // const bfCheckDate_7 = document.getElementById("id_exclusive_bf_check_7").value;
        // const bfCheckDate_8 = document.getElementById("id_exclusive_bf_check_8").value;
        // const bfCheckDate_9 = document.getElementById("id_exclusive_bf_check_9").value;
        // const bfCheckDate_10 = document.getElementById("id_exclusive_bf_check_10").value;
        const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]').value;

        console.log(validEntries);

        const sendData = async () => {
            try {
                const response = await fetch(`/midwife/bf-submission/${childId}/`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    },
                    body: JSON.stringify({
                        "type_of_feeding": typeOfFeeding,
                        "referred_newborn_screening_date": screeningDate,
                        "entries": validEntries,
                        "child_record_id": child_record_id
                    })
                });

                if (!response.ok) {
                    const err = await response.text();
                    console.error("Failed to submit data: ", err);
                    alert("Failed to submit data.");
                    return;
                }

                const result = await response.json();
                console.log("Success: ", result);
            } catch (error) {
                console.error("Error submitting data: ", error);
                alert("An error occurred while submitting data.");
            }
        }
        sendData();
    });

})();