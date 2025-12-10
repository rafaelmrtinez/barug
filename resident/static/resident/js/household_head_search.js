// Ensure DOM is ready before querying elements — script may be included in the <head>
document.addEventListener('DOMContentLoaded', function () {
  // Debounce helper
  function debounce(fn, delay){
    let t;
    return function(...args){
      clearTimeout(t);
      t = setTimeout(()=>fn.apply(this,args), delay);
    }
  }

  // Elements
  const input = document.getElementById('household_head_search');
  const resultsEl = document.getElementById('hhSearchResults');
  const hiddenIdEl = document.getElementById('id_household_head') || document.getElementById('household_head') || document.querySelector('input[name="household_head"]');

  if (!input || !resultsEl) return; // nothing to do

  // utility to clear results
  function clearResults(){
    resultsEl.innerHTML = '';
    resultsEl.style.display = 'none';
  }

  // Render list of persons
  function renderResults(list){
    resultsEl.innerHTML = '';
    if (!list || list.length === 0){
      const empty = document.createElement('div');
      empty.className = 'hh-search-empty';
      empty.textContent = 'No residents found';
      resultsEl.appendChild(empty);
      resultsEl.style.display = 'block';
      return;
    }

    list.forEach(item => {
      const row = document.createElement('div');
      row.className = 'hh-search-item';
      const name = item.full_name || (item.first_name + ' ' + (item.middle_name? item.middle_name + ' ' : '') + item.last_name) || item.person_code || '—';
      const sub = item.person_code ? (' — ' + item.person_code) : '';
      row.textContent = name + sub;
      row.dataset.personId = item.person_id || item.person_id;
      row.dataset.personName = name;
      row.addEventListener('click', (e) => {
        // set visible input and hidden id
        input.value = row.dataset.personName;
        if (hiddenIdEl) hiddenIdEl.value = row.dataset.personId;
        clearResults();
      });
      resultsEl.appendChild(row);
    });
    resultsEl.style.display = 'block';
  }

  // Perform search call
  async function doSearch(q){
    if (!q || q.trim().length < 2){ clearResults(); return; }
    try {
      const url = `/resident/api/search/?q=${encodeURIComponent(q)}&limit=8`;
      const res = await fetch(url, { credentials: 'same-origin' });
      if (!res.ok) { clearResults(); return; }
      const data = await res.json();
      // API may return object for single item; ensure array
      const list = Array.isArray(data) ? data : (data ? [data] : []);
      renderResults(list);
    } catch (err){
      console.error('Search error', err);
      clearResults();
    }
  }

  const debouncedSearch = debounce((e) => doSearch(e.target.value), 250);

  input.addEventListener('input', function(e){
    const v = e.target.value;
    if (!v) {
      // cleared by user -> clear hidden as well
      if (hiddenIdEl) hiddenIdEl.value = '';
      clearResults();
      return;
    }
    debouncedSearch(e);
  });

  // If user uses backspace to clear, event above handles empty value; also close on blur
  document.addEventListener('click', function(e){
    if (!resultsEl.contains(e.target) && e.target !== input){
      clearResults();
    }
  });

  // When user manually edits input, if they change content, clear hidden id to avoid stale id
  input.addEventListener('keydown', function(e){
    // allow navigation keys
    const nav = ['ArrowUp','ArrowDown','Enter','Tab','Escape'];
    if (nav.includes(e.key)) return;
    if (hiddenIdEl) hiddenIdEl.value = '';
  });

});
