// static/child_health/js/fetchChildBasics.js
(() => {
    document.addEventListener('DOMContentLoaded', () => {
        const $ = (id) => document.getElementById(id);

        // Hidden & visible inputs tied to the child
        const childHidden = $('child_person_id');
        const childNameInput = $('id_name');

        // Target fields to populate
        const fldFamilyNo = $('id_family_no');
        const fldUfcNo = $('id_ufc_no');
        const fldSex = $('id_sex');            // <select> (disabled is ok to set)
        const fldDob = $('id_date_of_birth');  // <input type="date">

        // Helpers
        const debounce = (fn, ms = 250) => {
            let t; return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
        };

        const setIfPresent = (el, val) => {
            if (!el) return;
            const v = (val === null || val === undefined) ? '' : String(val);
            el.value = v;
            // Trigger events so any validators/listeners react
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        };

        const setSelectByValueOrText = (selectEl, wanted) => {
            if (!selectEl) return;
            const target = (wanted ?? '').toString().trim();
            if (!target) { selectEl.value = ''; return; }

            // 1) Try by value match
            const byValue = Array.from(selectEl.options).find(o => (o.value || '').toString() === target);
            if (byValue) {
                selectEl.value = byValue.value;
                selectEl.dispatchEvent(new Event('change', { bubbles: true }));
                return;
            }

            // 2) Try by text (case-insensitive)
            const targetLower = target.toLowerCase();
            const byText = Array.from(selectEl.options).find(o => (o.text || '').toLowerCase() === targetLower);
            if (byText) {
                selectEl.value = byText.value;
                selectEl.dispatchEvent(new Event('change', { bubbles: true }));
                return;
            }

            // 3) Fallback: leave as is, but log
            console.warn('[CHR] Sex option not found for:', target);
        };

        const buildUrl = (personId) =>
            `/child_health/ajax/person-basic/${encodeURIComponent(personId)}/`;

        const assignChildBasics = (details) => {
            if (!details) return;

            // family_num and ufc_num may be null -> set empty string
            setIfPresent(fldFamilyNo, details.family_num ?? '');
            setIfPresent(fldUfcNo, details.ufc_num ?? '');

            // sex might be value or label; attempt both
            setSelectByValueOrText(fldSex, details.sex ?? '');

            // date_of_birth is ISO yyyy-mm-dd (works directly for type="date")
            setIfPresent(fldDob, details.date_of_birth ?? '');
        };

        const fetchChildBasics = async () => {
            const personId = childHidden?.value?.trim();
            if (!personId) return;

            try {
                const res = await fetch(buildUrl(personId), { method: 'GET' });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                console.log('[CHR] CHILD basics:', data);

                const info = (data && data.ok && Array.isArray(data.details) && data.details.length)
                    ? data.details[0]
                    : null;

                assignChildBasics(info);
            } catch (err) {
                console.error('[CHR] Failed to load CHILD basics:', err);
            }
        };

        const fetchChildBasicsDebounced = debounce(fetchChildBasics, 300);

        // Listen directly on hidden id (covers autocomplete updates)
        if (childHidden) {
            childHidden.addEventListener('change', fetchChildBasicsDebounced);
            childHidden.addEventListener('input', fetchChildBasicsDebounced);
        }

        // Also listen on visible name field (extra safety)
        if (childNameInput) {
            childNameInput.addEventListener('change', fetchChildBasicsDebounced);
            childNameInput.addEventListener('blur', fetchChildBasicsDebounced);
            childNameInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') fetchChildBasicsDebounced();
            });
        }

        // Dev helper
        window.__chrDebug = Object.assign(window.__chrDebug || {}, {
            fetchChildBasics,
        });
    });
})();
