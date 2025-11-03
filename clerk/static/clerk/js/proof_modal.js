// static/clerk/js/proof_modal.js
// Requires Bootstrap JS (v5). Works with your modal markup that contains:
// #proofCarousel, #proofCarouselInner, #proofCarouselIndicators, #proofEmptyState, #proofModalMeta
// Also supports optional #proofLightbox + #lightboxImg for full-screen viewing.

(function () {
  function fmtBytes(bytes) {
    if (!bytes) return '0 B';
    const k = 1024, sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(sizes.length - 1, Math.floor(Math.log(bytes) / Math.log(k)));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  }

  function initProofModalPreview(opts = {}) {
    // Elements
    const input =
      opts.inputEl ||
      document.querySelector('input[name="proof"]'); // Django form field: name="proof"

    const btnOpen    = opts.btnOpenEl     || document.getElementById('openProofModalBtn');
    const metaInline = opts.metaInlineEl  || document.getElementById('proofMeta');
    const metaModal  = opts.metaModalEl   || document.getElementById('proofModalMeta');

    const carousel        = opts.carouselEl       || document.getElementById('proofCarousel');
    const inner           = opts.innerEl          || document.getElementById('proofCarouselInner');
    const indicators      = opts.indicatorsEl     || document.getElementById('proofCarouselIndicators');
    const emptyState      = opts.emptyStateEl     || document.getElementById('proofEmptyState');

    const proofModal      = opts.proofModalEl     || document.getElementById('proofModal');
    const lightbox        = opts.lightboxEl       || document.getElementById('proofLightbox');
    const lightboxImg     = opts.lightboxImgEl    || document.getElementById('lightboxImg');

    if (!input || !btnOpen || !carousel || !inner || !indicators || !proofModal) return;

    // Ensure input accepts images & multiple
    input.setAttribute('accept', 'image/*');
    input.setAttribute('multiple', 'multiple');

    // Keep track of object URLs to revoke later
    let createdURLs = [];
    let imgCount = 0;

    function clearCarousel() {
      // Revoke blob URLs
      createdURLs.forEach(url => { try { URL.revokeObjectURL(url); } catch(_){}; });
      createdURLs = [];

      // Clear DOM
      inner.innerHTML = '';
      indicators.innerHTML = '';
      imgCount = 0;

      // States
      if (emptyState) emptyState.classList.add('d-none');
      if (metaModal) metaModal.textContent = '';
    }

    function updateSummaryInline(files, imageOnlyCount) {
      let totalBytes = 0, totalCount = 0;
      Array.from(files || []).forEach(f => { totalBytes += f.size; totalCount++; });

      const ignored = totalCount - imageOnlyCount;
      const summary = imageOnlyCount
        ? `${imageOnlyCount} image${imageOnlyCount > 1 ? 's' : ''} • ${fmtBytes(totalBytes)} total${ignored > 0 ? ` (${ignored} non-image ignored)` : ''}`
        : (totalCount ? `0 images • ${fmtBytes(totalBytes)} total (${ignored} non-image ignored)` : '');

      if (metaInline) metaInline.textContent = summary;
      if (metaModal)  metaModal.textContent  = imageOnlyCount ? `Image 1 of ${imageOnlyCount}` : summary;
    }

    function buildCarouselFromFiles(fileList) {
      clearCarousel();

      if (!fileList || fileList.length === 0) {
        if (btnOpen) btnOpen.classList.add('d-none');
        if (emptyState) emptyState.classList.remove('d-none');
        updateSummaryInline([], 0);
        return;
      }

      const images = Array.from(fileList).filter(f => f.type && f.type.startsWith('image/'));
      imgCount = images.length;

      if (imgCount === 0) {
        if (btnOpen) btnOpen.classList.add('d-none');
        if (emptyState) emptyState.classList.remove('d-none');
        updateSummaryInline(fileList, 0);
        return;
      }

      // Show the preview button
      if (btnOpen) btnOpen.classList.remove('d-none');

      // Build indicators + items
      images.forEach((file, idx) => {
        const url = URL.createObjectURL(file);
        createdURLs.push(url);

        // Indicator
        const ind = document.createElement('button');
        ind.type = 'button';
        ind.setAttribute('data-bs-target', '#proofCarousel');
        ind.setAttribute('data-bs-slide-to', String(idx));
        ind.setAttribute('aria-label', `Slide ${idx + 1}`);
        if (idx === 0) ind.classList.add('active');
        indicators.appendChild(ind);

        // Item
        const item = document.createElement('div');
        item.className = `carousel-item${idx === 0 ? ' active' : ''}`;

        const img = document.createElement('img');
        img.src = url;
        img.alt = file.name;
        img.className = 'd-block w-100';
        img.style.maxHeight = '300px';
        img.style.objectFit = 'contain';
        img.loading = 'lazy';

        // Click to open lightbox
        if (lightbox && lightboxImg && window.bootstrap?.Modal) {
          img.style.cursor = 'zoom-in';
          img.addEventListener('click', () => {
            lightboxImg.src = url;
            const m = bootstrap.Modal.getOrCreateInstance(lightbox);
            m.show();
          });
        }

        // Revoke URL after image has loaded into DOM (optional; we'll also revoke on clear)
        img.addEventListener('load', () => {
          // keep URL alive for lightbox/carousel session; we'll revoke on clear
        });

        item.appendChild(img);
        inner.appendChild(item);
      });

      // Bootstrap carousel instance (no auto-slide)
      const bsCarousel = bootstrap.Carousel.getOrCreateInstance(carousel, { interval: false, ride: false });

      // Update modal footer meta on slide
      carousel.addEventListener('slid.bs.carousel', () => {
        const activeIdx = Array.from(inner.children).findIndex(el => el.classList.contains('active'));
        if (metaModal && imgCount > 0) {
          metaModal.textContent = `Image ${activeIdx + 1} of ${imgCount}`;
        }
      }, { once: false });

      // Initial inline+modal summary
      updateSummaryInline(fileList, imgCount);
    }

    // Events
    input.addEventListener('change', () => {
      buildCarouselFromFiles(input.files);
    });

    // Build when the modal is opened (useful for bfcache or pre-selected files)
    proofModal.addEventListener('show.bs.modal', () => {
      buildCarouselFromFiles(input.files || []);
    });

    // Optional: clear lightbox src when hidden
    if (lightbox) {
      lightbox.addEventListener('hidden.bs.modal', () => {
        if (lightboxImg) lightboxImg.src = '';
      });
    }

    // Initial state (e.g., bfcache)
    if (input.files && input.files.length) {
      buildCarouselFromFiles(input.files);
    } else {
      buildCarouselFromFiles([]);
    }

    // Expose a tiny API if you ever need it elsewhere
    return {
      rebuild: () => buildCarouselFromFiles(input.files || []),
      clear: () => {
        input.value = '';
        buildCarouselFromFiles([]);
      }
    };
  }

  // Auto-init on DOM ready
  document.addEventListener('DOMContentLoaded', () => {
    window.__proofPreview = initProofModalPreview();
  });

  // Public export
  window.initProofModalPreview = initProofModalPreview;
})();
