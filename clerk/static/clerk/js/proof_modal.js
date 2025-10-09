// static/clerk/js/proof_modal.js
// Requires Bootstrap JS on the page (bootstrap.Modal). Safe with multiple forms per page if IDs are unique.

(function () {
  function fmtBytes(bytes) {
    if (!bytes) return '0 B';
    const k = 1024, sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  function initProofModalPreview(opts = {}) {
    const input =
      opts.inputEl ||
      document.querySelector('input[name="proof"]'); // fallback by name

    const btnOpen   = opts.btnOpenEl   || document.getElementById('openProofModalBtn');
    const metaInline= opts.metaInlineEl|| document.getElementById('proofMeta');

    const grid      = opts.gridEl      || document.getElementById('proofModalGrid');
    const metaModal = opts.metaModalEl || document.getElementById('proofModalMeta');

    const lightbox  = opts.lightboxEl  || document.getElementById('proofLightbox');
    const lightboxImg = opts.lightboxImgEl || document.getElementById('lightboxImg');

    const proofModal = opts.proofModalEl || document.getElementById('proofModal');

    if (!input || !btnOpen || !grid || !proofModal) return;

    // Ensure input accepts multiple images
    input.setAttribute('accept', 'image/*');
    input.setAttribute('multiple', 'multiple');

    function updateButtonState(files) {
      const has = files && files.length > 0;

      // show/hide the button (button is hidden by default via d-none in template)
      btnOpen.classList.toggle('d-none', !has);

      // update inline and modal meta text
      let total = 0, count = 0;
      Array.from(files || []).forEach(f => { total += f.size; count++; });
      const summary = has ? `${count} image${count > 1 ? 's' : ''} • ${fmtBytes(total)} total` : '';
      if (metaInline) metaInline.textContent = summary;
      if (metaModal)  metaModal.textContent  = summary;
    }

    function renderModalGrid(files) {
      grid.innerHTML = '';
      Array.from(files || []).forEach((file, idx) => {
        if (!file.type || !file.type.startsWith('image/')) return;

        const url = URL.createObjectURL(file);

        const col = document.createElement('div');
        col.className = 'col-12 col-sm-6 col-md-4';

        const card = document.createElement('div');
        card.className = 'card h-100 shadow-sm';

        const img = document.createElement('img');
        img.className = 'card-img-top img-fluid';
        img.alt = file.name;
        img.loading = 'lazy';
        img.src = url;
        img.style.objectFit = 'cover';
        img.style.height = '200px';
        img.style.cursor = 'zoom-in';

        // Full-size lightbox
        if (lightbox && lightboxImg && window.bootstrap?.Modal) {
          img.addEventListener('click', () => {
            lightboxImg.src = url;
            const m = new bootstrap.Modal(lightbox);
            m.show();
          });
        }

        const body = document.createElement('div');
        body.className = 'card-body p-2';

        const name = document.createElement('div');
        name.className = 'small text-truncate';
        name.title = file.name;
        name.textContent = file.name;

        const size = document.createElement('div');
        size.className = 'text-muted small';
        size.textContent = fmtBytes(file.size);

        const actions = document.createElement('div');
        actions.className = 'mt-2 d-flex justify-content-end gap-2';

        // Remove button (rebuild FileList)
        const btnRemove = document.createElement('button');
        btnRemove.type = 'button';
        btnRemove.className = 'btn btn-sm btn-outline-danger';
        btnRemove.textContent = 'Remove';
        btnRemove.addEventListener('click', function () {
          const dt = new DataTransfer();
          Array.from(input.files).forEach((f, j) => { if (j !== idx) dt.items.add(f); });
          input.files = dt.files;
          updateButtonState(input.files);
          renderModalGrid(input.files);
        });

        actions.appendChild(btnRemove);
        body.appendChild(name);
        body.appendChild(size);

        card.appendChild(img);
        card.appendChild(body);
        card.appendChild(actions);
        col.appendChild(card);
        grid.appendChild(col);

        img.addEventListener('load', () => URL.revokeObjectURL(url));
      });
    }

    // Events
    input.addEventListener('change', () => {
      updateButtonState(input.files);
      if (document.body.classList.contains('modal-open')) {
        renderModalGrid(input.files);
      }
    });

    proofModal.addEventListener('show.bs.modal', () => {
      renderModalGrid(input.files || []);
    });

    // Initial (in case of bfcache restore)
    if (input.files && input.files.length) updateButtonState(input.files);
    else updateButtonState([]);
  }

  // Auto-init on DOM ready
  document.addEventListener('DOMContentLoaded', () => {
    // Default init with standard IDs / name="proof"
    initProofModalPreview();
  });

  // Expose for custom init if needed elsewhere
  window.initProofModalPreview = initProofModalPreview;
})();
