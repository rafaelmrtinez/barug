// static/maternal/js/formClearHandler.js
(() => {
    document.addEventListener("DOMContentLoaded", () => {
        const form = document.getElementById("maternal-form");

        if (!form) {
            console.error("Maternal form not found on page.");
            return;
        }

        const clearBtn = form.querySelector('button[type="reset"], input[type="reset"]');
        if (!clearBtn) {
            console.error("Clear button not found inside maternal form.");
            console.log("Form HTML preview:", form.innerHTML.slice(0, 200));
            return;
        }

        clearBtn.addEventListener("click", (e) => {
            e.preventDefault();

            form.querySelectorAll("input, select, textarea").forEach((field) => {
                const type = field.type?.toLowerCase();

                if (
                    field.name === "csrfmiddlewaretoken" ||
                    ["button", "submit", "reset"].includes(type)
                ) {
                    return;
                }

                // Handle checkboxes and radios
                if (["checkbox", "radio"].includes(type)) {
                    field.checked = false;
                    return;
                }

                // Enable temporarily if disabled
                const wasDisabled = field.disabled;
                if (wasDisabled) field.disabled = false;

                field.value = "";

                if (wasDisabled) field.disabled = true;
            });
        });
    });
})();
