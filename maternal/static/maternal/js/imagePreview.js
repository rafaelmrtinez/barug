(function () {
    function renderThumbs(galleryEl, filesOrUrls) {
        galleryEl.innerHTML = '';
        if (!filesOrUrls || filesOrUrls.length === 0) {
            galleryEl.innerHTML = '<small class="text-muted">No images yet.</small>';
            return;
        }

        filesOrUrls.forEach(item => {
            const url = typeof item === 'string' ? item : URL.createObjectURL(item);
            const tile = document.createElement('div');
            tile.className = 'upload-thumb';
            tile.innerHTML = `<img src="${url}" alt="Upload preview">`;
            galleryEl.appendChild(tile);
        });
    }

    // Read pre-existing URLs from a data attribute on the input (if present)
    function getExistingUrls(input) {
        try {
            // support either data-existing-images (new) or data-existing (legacy)
            const raw = input.getAttribute('data-existing-images') || input.getAttribute('data-existing');
            if (!raw) return [];
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        // When the user clicks "Preview uploads"
        document.querySelectorAll('.preview-uploads-link').forEach(link => {
            link.addEventListener('click', function () {
                const inputId = this.getAttribute('data-input-id');
                const galleryId = this.getAttribute('data-gallery-id');
                const inputEl = document.getElementById(inputId);
                const galleryEl = document.getElementById(galleryId);
                if (!inputEl || !galleryEl) return;

                const files = Array.from(inputEl.files || []);
                const existing = getExistingUrls(inputEl);

                // Show existing + newly selected together
                renderThumbs(galleryEl, [...existing, ...files]);
            });
        });

        // Live updates: whenever files change, if gallery is open, re-render
        document.querySelectorAll('input[type="file"][multiple]').forEach(inputEl => {
            inputEl.addEventListener('change', function () {
                const link = document.querySelector(
                    `.preview-uploads-link[data-input-id="${this.id}"]`
                );
                if (!link) return;

                const galleryId = link.getAttribute('data-gallery-id');
                const galleryEl = document.getElementById(galleryId);
                if (!galleryEl) return;

                // If it's currently visible (Bootstrap collapse has 'show' class), update immediately
                if (galleryEl.classList.contains('show')) {
                    const files = Array.from(this.files || []);
                    const existing = getExistingUrls(inputEl);
                    renderThumbs(galleryEl, [...existing, ...files]);
                }
            });
        });
    });
})();
