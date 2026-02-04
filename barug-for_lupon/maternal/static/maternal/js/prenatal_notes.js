// Inject notes modal into the DOM and handle view-notes button clicks.
(function () {
  'use strict';

  function createModal() {
    var tpl = "" +
      '<div class="modal fade" id="notesModal" tabindex="-1" aria-hidden="true">' +
      '  <div class="modal-dialog modal-dialog-centered modal-lg">' +
      '    <div class="modal-content">' +
      '      <div class="modal-header">' +
      '        <h5 class="modal-title" id="notesModalTitle">Details</h5>' +
      '        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>' +
      '      </div>' +
      '      <div class="modal-body"><div id="notesModalContent" style="white-space:pre-wrap;"></div></div>' +
      '      <div class="modal-footer">' +
      '        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>' +
      '      </div>' +
      '    </div>' +
      '  </div>' +
      '</div>';
    var div = document.createElement('div');
    div.innerHTML = tpl;
    document.body.appendChild(div.firstElementChild);
  }

  function showModal(title, contentText) {
    var titleEl = document.getElementById('notesModalTitle');
    var content = document.getElementById('notesModalContent');
    if (titleEl) titleEl.textContent = title || 'Details';
    if (content) content.textContent = contentText || '';
    var modalEl = document.getElementById('notesModal');
    if (modalEl && typeof bootstrap !== 'undefined' && bootstrap.Modal) {
      var modal = new bootstrap.Modal(modalEl);
      modal.show();
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    // create modal once
    if (!document.getElementById('notesModal')) createModal();

    document.body.addEventListener('click', function (ev) {
      var t = ev.target;
      if (!t) return;
      // handle clicks on inner svg or on the button wrapper
      var btn = t.closest && t.closest('.view-entry');
      if (!btn) return;
      var content = btn.getAttribute('data-content') || '';
      var title = btn.getAttribute('data-title') || 'Details';
      showModal(title, content);
    }, false);
  });
})();
