// static/bhw/js/findPersonClient.min.js  (edited)
(() => {
  // ---------- CONFIG: attach to multiple fields ----------
  const attachPersonAutocomplete = ({ inputId, hiddenId, addressId }) => {
    const nameInput    = document.getElementById(inputId);
    const personIdInput = hiddenId ? document.getElementById(hiddenId) : null;
    const addressInput = addressId ? document.getElementById(addressId) : null;
    if (!nameInput) return; // field not on this page

    // --- inject minimal CSS once ---
    const styleId = 'person-dropdown-style';
    if (!document.getElementById(styleId)) {
      const s = document.createElement('style');
      s.id = styleId;
      s.textContent = `
        .person-dd {
          position: absolute;
          top: 100%;
          left: 0;
          margin-top: 2px;
          display: none;
          background: #fff;
          border: 1px solid rgba(0,0,0,.125);
          border-radius: .375rem;
          box-shadow: 0 .25rem .75rem rgba(0,0,0,.06);
          max-height: 260px;
          overflow: auto;
          z-index: 9999;
        }
        .person-dd ul { list-style: none; margin: 0; padding: 4px 0; }
        .person-dd li {
          padding: 6px 10px;
          cursor: pointer;
          white-space: normal;
        }
        .person-dd li:hover, .person-dd li:focus { background: #f7f7f7; }
        .person-dd .muted { color: #6c757d; font-size: .825rem; padding: 8px 10px; }
      `;
      document.head.appendChild(s);
    }

    // anchor dropdown under this input
    const parent = nameInput.parentElement;
    if (getComputedStyle(parent).position === 'static') {
      parent.style.position = 'relative';
    }

    const dd = document.createElement('div');
    dd.className = 'person-dd';
    nameInput.insertAdjacentElement('afterend', dd);

    const sizeDropdown = () => { dd.style.width = `${nameInput.offsetWidth}px`; };
    sizeDropdown(); window.addEventListener('resize', sizeDropdown);

    // per-field debounce & abort controller
    const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
    let activeController = null;

    const hide = () => { dd.style.display = 'none'; dd.innerHTML = ''; };
    const show = () => { dd.style.display = 'block'; };
    const showLoading = () => { dd.innerHTML = `<div class="muted">Searching…</div>`; show(); };

    const render = (items) => {
      if (!items || items.length === 0) {
        dd.innerHTML = `<div class="muted">No matches</div>`;
        show(); return;
      }
      const html = [
        '<ul>',
        ...items.map(r => `
          <li tabindex="0"
              data-id="${r.id}"
              data-name="${(r.name || '').replace(/"/g, '&quot;')}"
              data-address="${(r.address || '').replace(/"/g, '&quot;')}">
            <div>${r.name}</div>
            <div class="text-muted small">${r.address || ''}</div>
          </li>
        `),
        '</ul>'
      ].join('');
      dd.innerHTML = html; show();
    };

    const search = async (q) => {
      if (activeController) activeController.abort();
      activeController = new AbortController();
      try {
        const res = await fetch(`/child-health/ajax/find-person/?q=${encodeURIComponent(q)}`, { signal: activeController.signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const normalized = (data.results || []).map(r => ({
          id:      r.id ?? r.person_id,
          name:    r.name ?? r.full_name,
          address: r.address ?? ''
        }));
        render(normalized);
      } catch (e) {
        if (e.name === 'AbortError') return;
        console.error(e);
        dd.innerHTML = `<div class="muted">Network error</div>`;
        show();
      } finally {
        activeController = null;
      }
    };

    // typing: clear stale id, then search
    const onInput = debounce((e) => {
      const q = (e.target.value || '').trim();
      if (personIdInput) personIdInput.value = '';         // clear hidden id when typing
      if (q.length < 2) { hide(); return; }
      sizeDropdown(); showLoading(); search(q);
    }, 250);
    nameInput.addEventListener('input', onInput);

    // click select — <<-- REDUNDANT name change dispatch REMOVED HERE
    dd.addEventListener('click', (e) => {
      const li = e.target.closest('li[data-name]');
      if (!li) return;
      nameInput.value = li.dataset.name || '';
      if (addressInput)   { addressInput.value   = li.dataset.address || ''; addressInput.dispatchEvent(new Event('change')); }
      if (personIdInput)  { personIdInput.value  = li.dataset.id || '';      personIdInput.dispatchEvent(new Event('change')); }
      hide();
      // removed: nameInput.dispatchEvent(new Event('change'));
    });

    // keyboard select — <<-- REDUNDANT name change dispatch REMOVED HERE
    dd.addEventListener('keydown', (e) => {
      if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('li[data-name]')) {
        e.preventDefault();
        const li = e.target;
        nameInput.value = li.dataset.name || '';
        if (addressInput)   { addressInput.value   = li.dataset.address || ''; addressInput.dispatchEvent(new Event('change')); }
        if (personIdInput)  { personIdInput.value  = li.dataset.id || '';      personIdInput.dispatchEvent(new Event('change')); }
        hide();
        nameInput.focus();
        // removed: nameInput.dispatchEvent(new Event('change'));
      }
    });

    // hide on outside click
    document.addEventListener('click', (e) => { if (!dd.contains(e.target) && e.target !== nameInput) hide(); });

    // show suggestions on focus if already has text
    nameInput.addEventListener('focus', () => {
      const q = (nameInput.value || '').trim();
      if (q.length >= 2) { sizeDropdown(); showLoading(); search(q); }
    });
  };

  // ---------- WIRE FIELDS ----------
  attachPersonAutocomplete({
    inputId:   'id_name',
    hiddenId:  'id_person_id',
    addressId: 'id_address'
  });

  attachPersonAutocomplete({
    inputId:  'id_husband_name',
    hiddenId: 'id_husband_person_id',
  });
})();
