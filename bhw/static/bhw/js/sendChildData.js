(() => {

    const sendData = () => {

        const person_id = document.getElementById('child_id')?.value;
        const mother_id = document.getElementById('mother_id')?.value;
        const father_id = document.getElementById('father_id')?.value;
        const birth_order = document.querySelector('input[name="birth_order"]')?.value;
        const place_delivery = document.querySelector('input[name="place_delivery"]:checked')?.value;
        const family_no = document.querySelector('input[name="family_no"]')?.value;
        const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]').value;

        document.getElementById('childForm')?.addEventListener('submit', async (e) => {

            e.preventDefault();

            // Minimal guard: require a child selection
            const childId = document.getElementById('child_id')?.value;
            if (!childId) {
                alert('Please select the child resident first.');
                document.getElementById('childSearch')?.focus();
            }

            try {
                const res = await fetch("add-child/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken,
                    },
                    body: JSON.stringify({
                        child_id: person_id,
                        mother_id: mother_id,
                        father_id: father_id,
                        birth_order: birth_order,
                        place_delivery: place_delivery,
                        family_no: family_no
                    })
                });

                if (!res.ok) {
                    alert("An error occurred while submitting the form.");
                    return;
                }

                const data = await res.json();
                if (data.response === true) {
                    console.log("Child health record successfully created.");
                    alert("Child health record successfully created.");
                    window.location.reload();
                }

            } catch (error) {
                console.log(error);
                alert("An error occurred while submitting the form.");
            }


        });
    }

    sendData();
})();