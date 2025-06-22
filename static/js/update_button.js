document.addEventListener("DOMContentLoaded", function () {
    const editBtn = document.getElementById("enable-edit-btn");
    const saveBtn = document.querySelector("button[name='submit']");
    const clearBtn = document.querySelector("button[name='reset']");
    const fields = document.querySelectorAll(".editable-field");

    editBtn.addEventListener("click", function () {
        fields.forEach(field => field.disabled = false);
        saveBtn.classList.remove("d-none");
        clearBtn.classList.remove("d-none");
        editBtn.classList.add("d-none");
    });
});