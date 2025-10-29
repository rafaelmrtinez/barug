document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".section-action").forEach(btn => {
    btn.addEventListener("click", () => {
      const sel = btn.getAttribute("data-section");
      if (!sel) return;
      const el = document.querySelector(sel);
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      const firstInput = el.querySelector("input, select, textarea");
      if (firstInput) firstInput.focus({ preventScroll: true });
    });
  });
});
