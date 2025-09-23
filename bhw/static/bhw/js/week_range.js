document.addEventListener("DOMContentLoaded", function () {
  // ---------- date helpers ----------
  const isValidDate = (d) => d instanceof Date && !isNaN(d.getTime());

  // Parse "YYYY-MM-DD" safely (local time, avoids timezone shifts)
  const parseISO = (s) => {
    if (!s) return null;
    const parts = s.split("-");
    if (parts.length !== 3) return null;
    const [y, m, d] = parts.map(Number);
    const dt = new Date(y, (m || 1) - 1, d || 1);
    return isValidDate(dt) ? dt : null;
  };

  // Format "YYYY-MM-DD" from a Date (local)
  const toISOLocal = (d) => {
    if (!isValidDate(d)) return "";
    const y  = d.getFullYear();
    const m  = String(d.getMonth() + 1).padStart(2, "0");
    const da = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${da}`;
  };

  // Pure date add that preserves local date (no time-zone surprises)
  const addDays = (d, n) => {
    const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    x.setDate(x.getDate() + n);
    return x;
  };

  // Monday of the week for a given date (Mon=0)
  const mondayOf = (d) => addDays(d, -((d.getDay() + 6) % 7));

  // Label format: "Aug 18, 2025"
  const fmtFull = (d) =>
    d.toLocaleDateString(undefined, { month: "short", day: "2-digit", year: "numeric" });

  // "Aug 18, 2025 – Aug 22, 2025" (Mon–Fri)
  const labelFromMondayFull = (mon) => `${fmtFull(mon)} – ${fmtFull(addDays(mon, 4))}`;

  // ---------- CURRENT WEEK (page header) ----------
  (function renderCurrentWeek() {
    const el = document.getElementById("currentWeekLabel");
    if (!el) return;
    const thisMonday = mondayOf(new Date());
    el.textContent = labelFromMondayFull(thisMonday);
  })();

  // ---------- MODAL: Select week range (Prev/Next) ----------
  (function wireModalWeekPicker() {
    const weekStartInput = document.getElementById("weekStartField"); // hidden input for POST
    const weekLabel      = document.getElementById("weekLabel");      // text span showing range
    const prevBtn        = document.getElementById("prevWeek");
    const nextBtn        = document.getElementById("nextWeek");

    // If modal elements aren’t on this page, skip
    if (!weekLabel || !prevBtn || !nextBtn || !weekStartInput) return;

    // Seed current Monday:
    // 1) hidden input value (YYYY-MM-DD), else
    // 2) data-week-start on label, else
    // 3) this week's Monday (fallback)
    const seedStr = (weekStartInput.value || weekLabel.dataset.weekStart || "").trim();
    let currentMonday = parseISO(seedStr) || mondayOf(new Date());

    // Optional limits (uncomment if you want bounds)
    // const minMonday = mondayOf(new Date());          // no past weeks
    // const maxMonday = addDays(minMonday, 7 * 8);     // 8 weeks ahead

    function syncUI() {
      if (!isValidDate(currentMonday)) currentMonday = mondayOf(new Date());
      // Clamp to optional bounds (if using limits)
      // if (currentMonday < minMonday) currentMonday = minMonday;
      // if (currentMonday > maxMonday) currentMonday = maxMonday;

      weekLabel.textContent   = labelFromMondayFull(currentMonday);
      weekStartInput.value    = toISOLocal(currentMonday);

      // If you use limits, you can also disable buttons:
      // prevBtn.disabled = currentMonday <= minMonday;
      // nextBtn.disabled = currentMonday >= maxMonday;
    }

    prevBtn.addEventListener("click", function () {
      currentMonday = addDays(currentMonday, -7); // previous week
      syncUI();
    });

    nextBtn.addEventListener("click", function () {
      currentMonday = addDays(currentMonday, 7);  // next week
      syncUI();
    });

    // Initial paint
    syncUI();
  })();
});