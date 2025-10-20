// static/child_health/js/fetchChildBasics.js
(() => {
  document.addEventListener('DOMContentLoaded', () => {
    const $ = (id) => document.getElementById(id);

    // Child (hidden + visible)
    const childHidden    = $('child_person_id');
    const childNameInput = $('id_name');

    // Basics
    const fldFamilyNo    = $('id_family_no');
    const fldUfcNo       = $('id_ufc_no');
    const fldSex         = $('id_sex');            // <select>
    const fldDob         = $('id_date_of_birth');  // <input type="date">

    // Parents (visible + hidden)
    const fldMotherName  = $('id_mother');
    const fldFatherName  = $('id_father');
    const hidMotherId    = $('mother_person_id');
    const hidFatherId    = $('father_person_id');

    // Parent details (age + occupation)
    const fldMotherAge   = $('id_mother_age');
    const fldMotherOcc   = $('id_mother_occupation');
    const fldFatherAge   = $('id_father_age');
    const fldFatherOcc   = $('id_father_occupation');

    // Helpers
    const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

    const setValue = (el, val, { silent = false } = {}) => {
      if (!el) return;
      const v = (val === null || val === undefined) ? '' : String(val);
      el.value = v;
      if (!silent) {
        el.dispatchEvent(new Event('input',  { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    };

    const setSelectByValueOrText = (selectEl, wanted) => {
      if (!selectEl) return;
      const target = (wanted ?? '').toString().trim();
      if (!target) { selectEl.value = ''; return; }

      // by value
      const byValue = Array.from(selectEl.options).find(o => (o.value || '').toString() === target);
      if (byValue) { selectEl.value = byValue.value; selectEl.dispatchEvent(new Event('change', { bubbles: true })); return; }

      // by text (case-insensitive)
      const tl = target.toLowerCase();
      const byText = Array.from(selectEl.options).find(o => (o.text || '').toLowerCase() === tl);
      if (byText) { selectEl.value = byText.value; selectEl.dispatchEvent(new Event('change', { bubbles: true })); return; }

      console.warn('[CHR] Sex option not found for:', target);
    };

    const toISODate = (d) => {
      if (!d) return '';
      if (typeof d === 'string') return d; // already yyyy-mm-dd
      try {
        const dt = new Date(d);
        if (!isNaN(dt)) return dt.toISOString().slice(0, 10);
      } catch {}
      return '';
    };

    const buildUrl = (personId) => `/child-health/ajax/person-basic/${encodeURIComponent(personId)}/`;

    const assignFromDetails = (details) => {
      if (!details) return;

      // Basics
      setValue(fldFamilyNo, details.family_num ?? '');
      setValue(fldUfcNo,    details.ufc_num ?? '');
      setSelectByValueOrText(fldSex, details.sex ?? '');
      setValue(fldDob, toISODate(details.date_of_birth));

      // Parent IDs + names (silent to avoid triggering other scripts)
      setValue(hidMotherId,  details.mother_id ?? '',        { silent: true });
      setValue(hidFatherId,  details.father_id ?? '',        { silent: true });
      setValue(fldMotherName, details.mother_full_name ?? '', { silent: true });
      setValue(fldFatherName, details.father_full_name ?? '', { silent: true });

      // Parent occupations
      setValue(fldMotherOcc, details.mother_occupation ?? '');
      setValue(fldFatherOcc, details.father_occupation ?? '');

      // Parent ages (numbers → strings)
      setValue(fldMotherAge, (details.mother_age_years ?? '') === '' ? '' : details.mother_age_years);
      setValue(fldFatherAge, (details.father_age_years ?? '') === '' ? '' : details.father_age_years);
    };

    const fetchChildBasics = async () => {
      const personId = childHidden?.value?.trim();
      if (!personId) return;

      try {
        const res = await fetch(buildUrl(personId), { method: 'GET' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        const info = (data && data.ok && Array.isArray(data.details) && data.details.length)
          ? data.details[0]
          : null;

        assignFromDetails(info);
      } catch (err) {
        console.error('[CHR] Failed to load CHILD basics:', err);
      }
    };

    const fetchChildBasicsDebounced = debounce(fetchChildBasics, 300);

    // Listen to the hidden person_id (set by your autocomplete)
    if (childHidden) {
      childHidden.addEventListener('change', fetchChildBasicsDebounced);
      childHidden.addEventListener('input',  fetchChildBasicsDebounced);
    }

    // Also listen on visible name field (safety)
    if (childNameInput) {
      childNameInput.addEventListener('change', fetchChildBasicsDebounced);
      childNameInput.addEventListener('blur',   fetchChildBasicsDebounced);
      childNameInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') fetchChildBasicsDebounced();
      });
    }

    // Dev helper
    window.__chrDebug = Object.assign(window.__chrDebug || {}, { fetchChildBasics });
  });
})();
