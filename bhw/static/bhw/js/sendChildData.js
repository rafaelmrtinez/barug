(() => {

    document.getElementById('childForm')?.addEventListener('submit', async (e) => {

        e.preventDefault();

        const child_id = document.getElementById('child_id')?.value.trim();
        const mother_id = document.getElementById('mother_id')?.value.trim() || null;
        const father_id = document.getElementById('father_id')?.value.trim() || null;
        const birth_order = document.querySelector('input[name="birth_order"]')?.value.trim() || null;
        const place_delivery_el = document.querySelector('input[name="place_delivery"]:checked');
        const place_delivery = place_delivery_el ? place_delivery_el.value : null;
        const family_no = document.querySelector('input[name="family_no"]')?.value.trim() || null;
        const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;

        // Minimal guard: require a child selection
        const childId = document.getElementById('child_id')?.value;
        if (!childId) {
            alert('Please select the child resident first.');
            document.getElementById('childSearch')?.focus();
            return;
        }

        try {
            const res = await fetch("/bhw/add-child/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                },
                body: JSON.stringify({
                    child_id: child_id,
                    mother_id: mother_id,
                    father_id: father_id,
                    birth_order: birth_order,
                    place_delivery: place_delivery,
                    family_no: family_no
                })
            });

            if (!res.ok) {
                const data = await res.json();
                console.error("Error submitting form:", data);
                alert(data.response);
                return;
            }

            const data = await res.json();
            if (data.response === true) {
                alert("Child health record successfully created.");
                window.location.reload();
            }

        } catch (error) {
            console.error(error);
        }
    });
})();