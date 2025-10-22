(() => {

    document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("maternal-form");
    const motherNameInput = document.getElementById("id_name");

    if (motherNameInput && form) {
        motherNameInput.addEventListener("input", () => {
            // If input is empty, clear all other fields
            if (motherNameInput.value.trim() === "") {
                Array.from(form.elements).forEach(el => {
                    // Skip CSRF token
                    if (el.name !== "csrfmiddlewaretoken") {
                        if (el.type === "checkbox" || el.type === "radio") {
                            el.checked = false;
                        } else {
                            el.value = "";
                        }
                    }
                });

                // Optional: clear converted height display if present
                const heightFeetDisplay = document.getElementById("height-feet");
                if (heightFeetDisplay) heightFeetDisplay.textContent = "Feet: --";
            }
        });
    }
});


})();