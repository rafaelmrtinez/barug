(() => {
    // static/maternal/js/mhr-form.js
    document.addEventListener("DOMContentLoaded", () => {
        document.querySelectorAll(".section-action").forEach(btn => {
            btn.addEventListener("click", () => {
                const target = document.querySelector(btn.dataset.section);
                if (!target) return;
                target.scrollIntoView({ behavior: "smooth", block: "start" });
            });
        });
    });

})();