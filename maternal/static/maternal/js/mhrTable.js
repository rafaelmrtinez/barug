(() => {
    // Limit add/remove row logic to the "Previous Pregnancies" section form
    document.addEventListener("DOMContentLoaded", function () {
        const prevForm = document.getElementById("form-prev-preg");
        if (!prevForm) return;

        const addBtn = prevForm.querySelector("#add-previous-pregnancy");
        const totalForms = prevForm.querySelector("#id_pp-TOTAL_FORMS");
        const tableBody = prevForm.querySelector("#pregnancy-table-body");
        const emptyForm = document.querySelector("#empty-form-template").innerHTML;

        addBtn?.addEventListener("click", function () {
            const formCount = parseInt(totalForms.value);
            const newFormHtml = emptyForm.replaceAll("__prefix__", formCount);
            tableBody.insertAdjacentHTML("beforeend", newFormHtml);
            totalForms.value = formCount + 1;
        });

        tableBody.addEventListener("click", function (e) {
            if (e.target.classList.contains("remove-row")) {
                e.target.closest("tr").remove();
                totalForms.value = tableBody.querySelectorAll("tr").length;
            }
        });
    });
})();