// /static/js/business_owner_resident.js
(() => {
  'use strict';

  function onReady(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  onReady(() => {
    const root = document.getElementById('ownerPage');
    if (!root) return; // Not on this page

    // Dynamic values passed via data-* on #ownerPage
    const SEARCH_URL     = root.dataset.searchUrl || '';
    const CONTINUE_BASE  = root.dataset.continueBase || '';
    const HAS_SELECTED   = (root.dataset.hasSelected === 'true');
    const INITIAL_SEARCH = (root.dataset.initialSearch || '').trim();

    // DOM refs
    const form         = document.getElementById('ownerSearchForm');
    const input        = document.getElementById('search')
                          || document.getElementById('id_search')
                          || document.querySelector('#ownerSearchForm [name="search"]');
    const results      = document.getElementById('ownerResults');
    const matchesCount = document.getElementById('matchesCount');
    const changeLink   = document.getElementById('changeSelected');
    const continueBtn  = document.getElementById('continueBtn');
    const actionBar  = document.getElementById('actionBar');

    const HERE = window.location.pathname + window.location.search;

    // CSRF
    function getCookie(name){
      const value = `; ${document.cookie}`;
      const parts = value.split(`; ${name}=`);
      if (parts.length === 2) return parts.pop().split(';').shift();
      return '';
    }
    const CSRF_TOKEN = getCookie('csrftoken');

    // Utils
    function escapeHtml(s){
      return (s || "").replace(/[&<>"']/g, m => (
        { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[m]
      ));
    }

    function setMatchesCount(n){
      if (!matchesCount) return;
      if (n == null || n === "") {
        matchesCount.classList.add('d-none');
        matchesCount.textContent = "";
        return;
      }
      matchesCount.classList.remove('d-none');
      matchesCount.textContent = `${n} Match${n === 1 ? "" : "es"}`;
    }

    function buildCard(r){
      const personName = escapeHtml(r.person_name || "—");
      const personCode = escapeHtml(r.person_code || "—");
      const addrParts  = [r.street, r.purok, r.barangay, r.city].filter(Boolean).map(escapeHtml);
      const addr       = addrParts.join(", ");

      const wrapper = document.createElement('div');
      wrapper.className = "result-item border rounded-3 p-3 d-flex align-items-start justify-content-between";

      const left = document.createElement('div');
      left.className = "pe-3";
      left.innerHTML = `
        <div class="d-flex align-items-center gap-2 mb-1">
          <h6 class="mb-0 fw-semibold">${personName}</h6>
          <span class="badge bg-white text-dark border rounded-pill fw-semibold small px-2 py-1">${personCode}</span>
        </div>
        <div class="text-muted small mt-1">${addr || "—"}</div>
      `;

      const rightForm = document.createElement('form');
      rightForm.className = "ms-2 m-0";
      rightForm.method = "post";
      rightForm.action = HERE;
      rightForm.innerHTML = `
        <input type="hidden" name="csrfmiddlewaretoken" value="${CSRF_TOKEN}">
        <input type="hidden" name="owner_person_id" value="${r.person_id}">
        <input type="hidden" name="search" value="${escapeHtml(input?.value || "")}">
        <button type="submit" class="btn btn-submit btn-sm">Select as Owner</button>
      `;

      wrapper.appendChild(left);
      wrapper.appendChild(rightForm);
      return wrapper;
    }

    async function runSearch(q){
      if (!results) return;
      results.innerHTML = "";
      setMatchesCount("");

      if (!q){
        const msg = document.createElement('div');
        msg.className = "text-muted text-center py-4";
        msg.textContent = "Please enter a resident code or name.";
        results.appendChild(msg);
        return;
      }

      const loading = document.createElement('div');
      loading.className = "text-muted text-center py-4";
      loading.textContent = "Searching…";
      results.appendChild(loading);

      try{
        const resp = await fetch(`${SEARCH_URL}?search=${encodeURIComponent(q)}`, {
          headers: { "X-Requested-With": "XMLHttpRequest" }
        });
        const data = await resp.json();
        results.innerHTML = "";

        const arr = (data && data.results) ? data.results : [];
        setMatchesCount(arr.length);

        if (arr.length === 0){
          const none = document.createElement('div');
          none.className = "alert alert-light border";
          none.innerHTML = `No results for <strong>${escapeHtml(q)}</strong>.`;
          results.appendChild(none);
          return;
        }

        const list = document.createElement('div');
        list.className = "d-flex flex-column";
        arr.forEach(r => list.appendChild(buildCard(r)));
        results.appendChild(list);

      } catch (err){
        console.error(err);
        results.innerHTML = "";
        const fail = document.createElement('div');
        fail.className = "alert alert-danger";
        fail.textContent = "Search failed. Please try again.";
        results.appendChild(fail);
      }
    }

    // ---- Wire live search (callable after "Change") ----
    let wired = false;
    let debounceTimer = null;

    /**
     * Wire the search input.
     * @param {Object} opts
     * @param {boolean} opts.hydrate - run an initial search using provided initial value (or input value)
     * @param {string}  opts.initial - initial term to hydrate with (optional)
     */
    function wireLiveSearch({ hydrate = false, initial = "" } = {}) {
      if (wired) return;
      wired = true;

      if (form) {
        form.addEventListener('submit', function(e){
          e.preventDefault();
          runSearch((input?.value || "").trim());
        });
      }

      input?.addEventListener('input', () => {
        const q = (input.value || "").trim();
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => runSearch(q), 250);
      });

      const start = hydrate ? ((input?.value || initial || "").trim()) : "";
      if (start) {
        runSearch(start);
      } else if (results) {
        results.innerHTML = '<div class="text-muted text-center py-4">Start by typing a code or name.</div>';
      }
    }

    // ----- Selection-aware behavior -----
    if (HAS_SELECTED) {
      // Disable search and hide results list
      if (input) { input.disabled = true; input.classList.add('disabled'); }
      if (results) results.classList.add('d-none');
      if (form) form.addEventListener('submit', e => e.preventDefault());

      // Clicking "Change" clears selection without full reload, then wires search
      if (changeLink) {
        changeLink.addEventListener('click', function(e){
          e.preventDefault();

          // Remove selected card
          document.getElementById('selectedCard')?.remove();

          actionBar?.remove();

          // Re-enable search
          if (input) {
            input.disabled = false;
            input.value = "";
            input.focus();
          }

          // Show empty results panel
          if (results) {
            results.classList.remove('d-none');
            results.innerHTML = '<div class="text-muted text-center py-4">Start by typing a code or name.</div>';
          }

          // Hide matches badge
          setMatchesCount("");

          // Reset Continue link to base (drop ?owner_id=…)
          if (continueBtn) continueBtn.setAttribute('href', CONTINUE_BASE);

          // Optional: remove ?search=... from URL so refresh stays clean
          if (window.history?.replaceState) {
            window.history.replaceState({}, "", window.location.pathname);
          }

          // NOW wire live search WITHOUT hydrating previous results
          wireLiveSearch({ hydrate: false });
        });
      }
    } else {
      // Normal path: hydrate using INITIAL_SEARCH (if any)
      wireLiveSearch({ hydrate: true, initial: INITIAL_SEARCH });
    }

    // Scroll to selected card if present
    const selCard = document.getElementById('selectedCard');
    if (selCard) {
      selCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
})();
