// Small helper to debounce input and perform search by updating the query string.
document.addEventListener('DOMContentLoaded', function () {
  const input = document.getElementById('faq-search');
  const form = document.getElementById('faq-search-form');
  if (!input || !form) return;

  let timer = null;
  const debounceMs = 350;

  function doSearch(q) {
    const params = new URLSearchParams(window.location.search);
    if (q) params.set('q', q);
    else params.delete('q');
    // reset to first page on new search
    params.delete('page');
    const newUrl = `${window.location.pathname}?${params.toString()}`;
    window.location.href = newUrl;
  }

  input.addEventListener('input', function (e) {
    const v = e.target.value;
    clearTimeout(timer);
    timer = setTimeout(function () { doSearch(v.trim()); }, debounceMs);
  });

  // allow pressing Enter to submit immediately
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    clearTimeout(timer);
    doSearch(input.value.trim());
  });
});
