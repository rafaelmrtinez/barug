// static/js/schedule-multi.js
(function () {
  function boot() {
    const list = document.getElementById('sched-list');
    const addBtn = document.getElementById('add-sched');
    if (!list || !addBtn) return;

    // Ensure row 0 has unique ids ("-0") and array-style names
    initRow(list.querySelector('.sched-row'), 0, true);

    addBtn.addEventListener('click', () => {
      const first = list.querySelector('.sched-row');
      const clone = first.cloneNode(true);
      const idx = list.querySelectorAll('.sched-row').length;

      // make ids unique, switch names to arrays, clear values
      initRow(clone, idx, false);

      // show remove button on clones
      const removeBtn = clone.querySelector('.remove-sched');
      if (removeBtn) removeBtn.classList.remove('d-none');

      list.appendChild(clone);
    });

    list.addEventListener('click', (e) => {
      const btn = e.target.closest('.remove-sched');
      if (!btn) return;
      const rows = list.querySelectorAll('.sched-row');
      const row = btn.closest('.sched-row');
      if (rows.length <= 1) return; // keep at least one
      row.remove();
      renumberRows();
    });

    // --- helpers ---
    function initRow(row, idx, convertOriginalNames) {
      row.dataset.index = idx;

      // Map of base ids used by your Django fields
      const fields = [
        { baseId: 'day' },
        { baseId: 'time_start' },
        { baseId: 'time_end' },
      ];

      fields.forEach(({ baseId }) => {
        // find the input/select within this row whose id starts with baseId
        let el = row.querySelector('#' + baseId) || row.querySelector(`[id^="${baseId}"]`);
        if (!el) return;

        const oldId = el.id;
        const newId = `${baseId}-${idx}`;
        el.id = newId;

        // optional: convert names to array style so multiple values can post later
        if (el.name) {
          if (convertOriginalNames || !/\[\]$/.test(el.name)) {
            const baseName = el.name.replace(/\[\]$/, '').replace(/\[\d+\]$/, '');
            el.name = baseName + '[]';
          }
        }

        // update the floating label's "for"
        const label = row.querySelector(`label[for="${oldId}"]`) || row.querySelector(`label[for^="${baseId}"]`);
        if (label) label.setAttribute('for', newId);

        // clear values for cloned rows
        if (idx !== 0) {
          if (el.tagName === 'SELECT') el.selectedIndex = 0;
          if (el.type === 'time') el.value = '';
        }
      });
    }

    function renumberRows() {
      const rows = list.querySelectorAll('.sched-row');
      rows.forEach((row, i) => {
        row.dataset.index = i;
        // update ids/labels to keep them unique & ordered
        ['day', 'time_start', 'time_end'].forEach(baseId => {
          const el = row.querySelector(`[id^="${baseId}"]`);
          if (!el) return;
          const oldId = el.id;
          const newId = `${baseId}-${i}`;
          el.id = newId;
          const lab = row.querySelector(`label[for="${oldId}"]`);
          if (lab) lab.setAttribute('for', newId);
        });

        // hide remove button if it's the only remaining row
        const removeBtn = row.querySelector('.remove-sched');
        if (removeBtn) removeBtn.classList.toggle('d-none', rows.length === 1 && i === 0);
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
