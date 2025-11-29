document.addEventListener('DOMContentLoaded', function () {
  function autosize(el) {
    // reset height so scrollHeight is accurate
    el.style.height = 'auto';
    el.style.height = (el.scrollHeight) + 'px';
  }

  var areas = document.querySelectorAll('.autosize-textarea');
  areas.forEach(function (ta) {
    // initialize height
    autosize(ta);
    // on input adjust height
    ta.addEventListener('input', function () { autosize(ta); });
    // also adjust on window resize in case of wrapping changes
    window.addEventListener('resize', function () { autosize(ta); });
  });
});
