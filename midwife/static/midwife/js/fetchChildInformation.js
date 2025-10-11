(() => {
    const childIdField = document.getElementById("child_id");

    const fetchData = async () => {
        try {
            const child_id = childIdField.value;

            if (!child_id) {
                return;
            }

            const url = `/midwife/child-basic-info/${child_id}/`;
            const response = await fetch(url);

            let res;
            try {
                res = await response.json();
            } catch {
                res = null;
            }

            if (!response.ok) {
                alert(res?.error || "No record of child information found.");
                return;
            }

            const message = res.message;

            document.querySelector('input[name="family_no"]').value = message.fam_number || "";

            const motherName = document.getElementById("mother_name");
            if (motherName) motherName.value = message.mother || "";

            const motherAge = document.getElementById("mother_age");
            if (motherAge) motherAge.value = message.mothers_age || "";

            const fatherName = document.getElementById("father_name");
            if (fatherName) fatherName.value = message.father || "";

            const fatherAge = document.getElementById("father_age");
            if (fatherAge) fatherAge.value = message.fathers_age || "";

            const birthOrder = document.querySelector('input[name="birth_order"]');
            if (birthOrder) birthOrder.value = message.birth_order || "";

            const place = (message.place_of_delivery || "").toLowerCase();
            const mapping = {
                "hospital (gov’t)": "hospital_govt",
                "hospital (private)": "hospital_private",
                "home": "home",
                "private clinic": "private_clinic",
                "lying-in": "lying_in",
                "hc": "hc",
            };

            const deliveryValue = mapping[place];
            if (deliveryValue) {
                const radio = document.querySelector(`input[name="place_delivery"][value="${deliveryValue}"]`);
                if (radio) radio.checked = true;
            }

        } catch {
            console.error("Error fetching child information:");
        }
    };

    const observer = new MutationObserver(() => {
        fetchData();
    });

    observer.observe(childIdField, {
        attributes: true,
        attributeFilter: ["value"]
    });
})();
