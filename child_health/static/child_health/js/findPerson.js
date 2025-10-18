(() => {
    // static/child_health/js/findPerson.js
    document.addEventListener('DOMContentLoaded', () => {

        const attachPersonAutocomplete = ({ inputId, hiddenId = null, addressId = null }) => {
            const nameInput = document.getElementById(inputId);
            if (!nameInput) return;

            const personIdInput = hiddenId ? document.getElementById(hiddenId) : null;
            const addressInput = addressId ? document.getElementById(addressId) : null;

            // Inject CSS (once)
            if (!document.getElementById('person-dd-style')) {
                const s = document.createElement('style');
                s.id = 'person-dd-style';
                s.textContent = `
          .person-dd {
            position: absolute;
            top: 100%;
            left: 0;
            width: 100%;
            margin-top: 2px;
            display: none;
            background: #fff;
            border: 1px solid rgba(0,0,0,.15);
            border-radius: .375rem;
            box-shadow: 0 .25rem .75rem rgba(0,0,0,.06);
            max-height: 250px;
            overflow: auto;
            z-index: 1050;
          }
          .person-dd ul { list-style: none; margin: 0; padding: 0; }
          .person-dd li { padding: 6px 10px; cursor: pointer; }
          .person-dd li:hover { background: var(--brand-100, #f8eef0); }
          .person-dd .muted { color: #6c757d; font-size: 0.875rem; padding: 6px 10px; }
        `;
                document.head.appendChild(s);
            }

            const parent = nameInput.parentElement;
            if (getComputedStyle(parent).position === 'static') parent.style.position = 'relative';

            const dd = document.createElement('div');
            dd.className = 'person-dd';
            nameInput.insertAdjacentElement('afterend', dd);

            const hide = () => { dd.style.display = 'none'; dd.innerHTML = ''; };
            const show = () => { dd.style.display = 'block'; };

            const render = (items) => {
                if (!items?.length) {
                    dd.innerHTML = `<div class="muted">No matches found</div>`;
                    show();
                    return;
                }
                dd.innerHTML = `<ul>${items.map(r => `
          <li data-id="${r.id ?? ''}" data-name="${r.name ?? ''}" data-address="${r.address ?? ''}">
            <div>${r.name ?? ''}</div>
            <div class="text-muted small">${r.address ?? ''}</div>
          </li>`).join('')}</ul>`;
                show();
            };

            const debounce = (fn, ms = 250) => {
                let t; return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
            };

            let controller = null;
            const search = async (query) => {
                if (controller) controller.abort();
                controller = new AbortController();
                try {
                    const res = await fetch(`/child-health/ajax/find-person/?q=${encodeURIComponent(query)}`, {
                        signal: controller.signal
                    });
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    const data = await res.json();
                    render((data.results || []).map(r => ({
                        id: r.id ?? r.person_id,
                        name: r.name ?? r.full_name,
                        address: r.address ?? ''
                    })));
                } catch (e) {
                    if (e.name !== 'AbortError') {
                        dd.innerHTML = `<div class="muted">Network error</div>`;
                        show();
                    }
                }
            };

            // When the user types, clear hiddenId (avoid stale selection)
            nameInput.addEventListener('input', debounce(e => {
                const q = e.target.value.trim();
                // Clear hidden person id and address while user is editing
                if (personIdInput) personIdInput.value = '';
                if (addressInput) addressInput.value = '';

                if (q.length < 2) return hide();
                dd.innerHTML = `<div class="muted">Searching…</div>`;
                show();
                search(q);
            }, 300));

            // Selecting a result writes name, hidden person_id, and optional address
            dd.addEventListener('click', e => {
                const li = e.target.closest('li[data-name]');
                if (!li) return;
                nameInput.value = li.dataset.name || '';
                if (personIdInput) personIdInput.value = li.dataset.id || '';
                if (addressInput) addressInput.value = li.dataset.address || '';
                hide();
                nameInput.dispatchEvent(new Event('change'));
            });

            document.addEventListener('click', e => {
                if (!dd.contains(e.target) && e.target !== nameInput) hide();
            });
        };

        // Attach fields with proper hiddenId/addressId mappings
        attachPersonAutocomplete({
            inputId: 'id_name',
            hiddenId: 'child_person_id',
            addressId: 'id_address' // fills the Identification/Parent address field if present
        });
        attachPersonAutocomplete({
            inputId: 'id_mother',
            hiddenId: 'mother_person_id'
            // no address fill for mother field (leave as your current behavior)
        });
        attachPersonAutocomplete({
            inputId: 'id_father',
            hiddenId: 'father_person_id'
            // no address fill for father field
        });
    });
})();
