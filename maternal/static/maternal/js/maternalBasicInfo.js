// static/bhw/js/maternalBasicInfo.js
(() => {
  // --- form elements ---
  const personIdInput   = document.getElementById('id_person_id');   // hidden
  const familyNoInput   = document.getElementById('id_family_no');
  const dobInput        = document.getElementById('id_date_of_birth');
  const ageInput        = document.getElementById('id_age');
  const occupationInput = document.getElementById('id_occupation');
  const ageGroupSelect  = document.getElementById('id_age_group');   // <select>

  if (!personIdInput) return;

  // Helpers
  const setIfPresent = (el, val) => {
    if (!el) return;
    if (val !== null && val !== undefined && val !== '') {
      el.value = val;
      el.dispatchEvent(new Event('change'));
    }
  };

  // Map numeric age -> one of: '10-14','15-19','20-49' (cap >=20 to '20-49')
  const computeGroupValueFromAge = (ageNum) => {
    if (!(ageNum > 0)) return '';
    if (ageNum >= 10 && ageNum <= 14) return '10-14';
    if (ageNum >= 15 && ageNum <= 19) return '15-19';
    if (ageNum >= 20) return '20-49';   // <-- IMPORTANT: covers 20..∞, including 50+
    return '';
  };

  // Set the select by value, fallback to text match if needed
  const setAgeGroup = (val) => {
    if (!ageGroupSelect) return;
    if (!val) {
      ageGroupSelect.value = '';
      ageGroupSelect.dispatchEvent(new Event('change'));
      return;
    }
    // try direct value
    ageGroupSelect.value = val;
    if (ageGroupSelect.value === val) {
      ageGroupSelect.dispatchEvent(new Event('change'));
      return;
    }
    // fallback: by label text (handles en dashes in labels)
    const upper = val.toUpperCase();
    let matched = false;
    for (const opt of Array.from(ageGroupSelect.options)) {
      const t = (opt.text || '').toUpperCase();
      if (t === upper || t.includes(upper)) { opt.selected = true; matched = true; break; }
    }
    if (!matched) ageGroupSelect.value = '';
    ageGroupSelect.dispatchEvent(new Event('change'));
  };

  const applyAgeGroupFromAgeNumber = (n) => {
    const groupVal = computeGroupValueFromAge(n);
    setAgeGroup(groupVal);
  };

  const applyAgeGroupFromCurrentField = () => {
    if (!ageInput) return;
    const n = parseFloat((ageInput.value ?? '').toString().trim());
    if (!Number.isNaN(n)) applyAgeGroupFromAgeNumber(n);
  };

  // Fetch + fill routine
  const fetchAndFill = async (personId) => {
    if (!personId || String(personId).trim() === '') return;
    try {
      const res = await fetch(`/midwife/maternal-basic-info/${encodeURIComponent(personId)}/`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (!data.ok || !data.person) return;

      const p = data.person;
      setIfPresent(familyNoInput,   p.family_num);
      setIfPresent(dobInput,        p.date_of_birth);
      setIfPresent(ageInput,        p.age);
      setIfPresent(occupationInput, p.occupation);

      // ✅ Set age group directly from the numeric age we just received
      const n = parseFloat(p.age);
      if (!Number.isNaN(n)) {
        applyAgeGroupFromAgeNumber(n);
      } else {
        // fallback: parse whatever is currently in the field
        applyAgeGroupFromCurrentField();
      }
    } catch (err) {
      console.error('maternalBasicInfo fetch failed:', err);
    }
  };

  // Keep age group in sync when the user types/changes age
  if (ageInput) {
    ageInput.addEventListener('input',  applyAgeGroupFromCurrentField);
    ageInput.addEventListener('change', applyAgeGroupFromCurrentField);
    ageInput.addEventListener('blur',   applyAgeGroupFromCurrentField);
  }

  // Trigger fetch when person id changes
  personIdInput.addEventListener('change', (e) => {
    fetchAndFill(e.target.value);
  });

  // Prefill once on load if person already selected
  if (personIdInput.value && String(personIdInput.value).trim() !== '') {
    fetchAndFill(personIdInput.value);
  }

  // Optional global trigger
  window.prefillMaternalFromSelectedPerson = () => {
    fetchAndFill(personIdInput.value);
  };
})();