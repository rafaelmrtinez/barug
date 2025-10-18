// static/child_health/js/fetchParentBasics.js
(() => {
    document.addEventListener('DOMContentLoaded', () => {
        const $ = (id) => document.getElementById(id);

        // Visible inputs we watch
        const motherInput = $('id_mother');
        const fatherInput = $('id_father');

        // Hidden IDs populated by your autocomplete
        const motherHidden = $('mother_person_id');
        const fatherHidden = $('father_person_id');

        // Target fields to populate
        const fields = {
            mother: {
                age: $('id_mother_age'),
                occupation: $('id_mother_occupation'),
            },
            father: {
                age: $('id_father_age'),
                occupation: $('id_father_occupation'),
            },
        };

        const setIfPresent = (el, val) => {
            if (!el) return;
            // Convert undefined/null to empty string; numbers to string
            const v = (val === undefined || val === null) ? '' : String(val);
            el.value = v;
            // Fire input/change so any listeners or validation can react
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        };

        // Simple debounce to avoid burst calls
        const debounce = (fn, ms = 250) => {
            let t;
            return (...args) => {
                clearTimeout(t);
                t = setTimeout(() => fn(...args), ms);
            };
        };

        // Build endpoint url safely (trailing slash included)
        const buildBasicsUrl = (personId) =>
            `/child_health/ajax/child-basic-info/${encodeURIComponent(personId)}/`;

        // Assign fetched basics into correct form fields
        const assignParentBasics = (role, details) => {
            if (!details) return;
            const ageYears = details.age_years ?? '';
            const occupation = details.occupation ?? '';

            if (role === 'mother') {
                setIfPresent(fields.mother.age, ageYears);
                setIfPresent(fields.mother.occupation, occupation);
            } else if (role === 'father') {
                setIfPresent(fields.father.age, ageYears);
                setIfPresent(fields.father.occupation, occupation);
            }
        };

        // Core fetcher
        const fetchBasics = async (role, personId) => {
            if (!personId) return; // nothing to do
            try {
                const url = buildBasicsUrl(personId);
                const res = await fetch(url, { method: 'GET' });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                console.log(`[CHR] ${role.toUpperCase()} basics:`, data);

                // Expecting: { ok: true, details: [{...}] }
                const info =
                    data && data.ok && Array.isArray(data.details) && data.details.length
                        ? data.details[0]
                        : null;

                assignParentBasics(role, info);
            } catch (err) {
                console.error(`[CHR] Failed to load ${role} basics:`, err);
            }
        };

        // Debounced wrappers (separate to keep logs readable)
        const fetchMotherBasicsDebounced = debounce(() => {
            const personId = motherHidden?.value?.trim();
            fetchBasics('mother', personId);
        }, 300);

        const fetchFatherBasicsDebounced = debounce(() => {
            const personId = fatherHidden?.value?.trim();
            fetchBasics('father', personId);
        }, 300);

        // Attach listeners to visible inputs
        if (motherInput) {
            motherInput.addEventListener('change', fetchMotherBasicsDebounced);
            motherInput.addEventListener('blur', fetchMotherBasicsDebounced);
            motherInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') fetchMotherBasicsDebounced();
            });
        }

        if (fatherInput) {
            fatherInput.addEventListener('change', fetchFatherBasicsDebounced);
            fatherInput.addEventListener('blur', fetchFatherBasicsDebounced);
            fatherInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') fetchFatherBasicsDebounced();
            });
        }

        // Also listen directly on hidden inputs (in case your autocomplete sets them
        // without triggering change on the visible input for some reason).
        if (motherHidden) {
            motherHidden.addEventListener('change', fetchMotherBasicsDebounced);
            motherHidden.addEventListener('input', fetchMotherBasicsDebounced);
        }
        if (fatherHidden) {
            fatherHidden.addEventListener('change', fetchFatherBasicsDebounced);
            fatherHidden.addEventListener('input', fetchFatherBasicsDebounced);
        }

        // Dev helpers to trigger manually from console if needed:
        window.__chrDebug = Object.assign(window.__chrDebug || {}, {
            fetchMotherBasics: () => fetchBasics('mother', motherHidden?.value?.trim()),
            fetchFatherBasics: () => fetchBasics('father', fatherHidden?.value?.trim()),
        });
    });
})();
