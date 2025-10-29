(function () {
    function renderThumbs(galleryEl, filesOrUrls) {
        galleryEl.innerHTML = '';
        if (!filesOrUrls || filesOrUrls.length === 0) {
            galleryEl.innerHTML = '<small class="text-muted">No images yet.</small>';
            return;
        }

        filesOrUrls.forEach(item => {
            const isString = typeof item === 'string';
            const url = isString ? item : URL.createObjectURL(item);
            const tile = document.createElement('div');
            tile.className = 'upload-thumb';

            // Build inner HTML with image and a download button overlay
            const img = document.createElement('img');
            img.src = url;
            img.alt = 'Upload preview';
            tile.appendChild(img);

            // download button
            const dl = document.createElement('button');
            dl.type = 'button';
            dl.className = 'btn btn-sm btn-light download-thumb-btn';
            dl.title = 'Download image';
            dl.textContent = '\u2B07'; // downward arrow

            dl.addEventListener('click', function (ev) {
                ev.stopPropagation();
                // If the item is a File object, use its name; otherwise derive from URL
                let filename = 'image';
                if (!isString && item && item.name) filename = item.name;
                else {
                    try {
                        const parts = url.split('/');
                        filename = parts[parts.length - 1].split('?')[0] || 'image';
                    } catch {}
                }
                triggerDownload(url, filename, !isString);
            });

            tile.appendChild(dl);

            // open modal when user clicks a thumbnail (but not the download btn)
            tile.style.cursor = 'pointer';
            tile.addEventListener('click', function (e) {
                // ignore clicks on the download button
                if (e.target === dl) return;
                openPreviewModal(url);
            });
            galleryEl.appendChild(tile);
        });
    }

    // Trigger a download for a given URL. If isBlob (true), we will fetch the
    // resource as a blob to ensure a proper filename and download; otherwise we
    // create an anchor with download attribute.
    async function triggerDownload(url, filename, isBlobUrl) {
        try {
            if (isBlobUrl) {
                // For File object URLs (created with URL.createObjectURL), simply
                // create an anchor and click it. We revoke the object URL shortly after.
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                a.remove();
                // revoke after small timeout to allow download to start
                setTimeout(() => URL.revokeObjectURL(url), 1000);
                return;
            }

            // For remote URLs, attempt to fetch and download as blob to set filename
            try {
                const resp = await fetch(url, { credentials: 'same-origin' });
                if (!resp.ok) throw new Error('Fetch failed');
                const blob = await resp.blob();
                const blobUrl = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = blobUrl;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                a.remove();
                setTimeout(() => URL.revokeObjectURL(blobUrl), 1500);
                return;
            } catch (err) {
                // fallback: open in new tab/window (user can right-click to save)
                try { window.open(url, '_blank'); } catch (_) { /* noop */ }
            }
        } catch (e) {
            console.error('Download failed', e);
        }
    }

    // Open a Bootstrap modal to preview the image at full size (or as large as modal)
    function openPreviewModal(url) {
        try {
            const modalEl = document.getElementById('imagePreviewModal');
            const modalImg = document.getElementById('imagePreviewModalImg');
            if (!modalEl || !modalImg) return;
            modalImg.src = url;
            // use Bootstrap's modal API (v5+)
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
        } catch (_e) {
            // fallback: open in new tab/tab-equivalent
            try { globalThis.open(url, '_blank'); } catch { /* noop */ }
        }
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

            // Download all laboratory images button (global) - prefer server ZIP endpoint
            const downloadAllBtn = document.getElementById('btn-download-all-lab-images');
            if (downloadAllBtn) {
                downloadAllBtn.addEventListener('click', async function () {
                    // Determine the current/latest MHR id on the page by scanning data-mhr-id attributes
                    const ids = [];
                    document.querySelectorAll('[data-mhr-id]').forEach(function (el) {
                        const v = el.getAttribute('data-mhr-id');
                        if (v != null && String(v).trim() !== '') {
                            const n = Number(String(v).trim());
                            if (!Number.isNaN(n)) ids.push(n);
                        }
                    });
                    document.querySelectorAll('table.visit-table tbody tr').forEach(function (tr) {
                        const td = tr.querySelector('td');
                        if (td) {
                            const t = td.textContent.trim();
                            const n = Number(t);
                            if (!Number.isNaN(n)) ids.push(n);
                        }
                    });
                    if (!ids.length) {
                        try { globalThis.MHRToast && globalThis.MHRToast.show('No maternal record id found on page', false); } catch (e) { console.debug('Toast unavailable', e); }
                        return;
                    }
                    const mhrId = String(Math.max.apply(null, ids));

                    // Call server-side ZIP endpoint
                    try {
                        const resp = await fetch(`/maternal/api/v1/mhr/lab-images/zip/?mhr_id=${encodeURIComponent(mhrId)}`, {
                            method: 'GET',
                            credentials: 'same-origin'
                        });

                        if (!resp.ok) {
                            let msg = `Server returned ${resp.status}`;
                            try { const j = await resp.json(); if (j && j.message) msg = j.message; } catch (_e) { console.debug('No JSON body', _e); }
                            try { globalThis.MHRToast && globalThis.MHRToast.show(msg, false); } catch (e) { console.debug('Toast unavailable', e); }
                            return;
                        }

                        const blob = await resp.blob();
                        // Derive filename from content-disposition header if present
                        let filename = `lab_images_mhr_${mhrId}.zip`;
                        try {
                            const cd = resp.headers.get('Content-Disposition') || '';
                            const m = cd.match(/filename\*=UTF-8''([^;\n\r]+)/i) || cd.match(/filename="?([^";\n\r]+)"?/i);
                            if (m && m[1]) filename = decodeURIComponent(m[1]);
                        } catch (_e) { console.debug('Failed to parse filename from header', _e); }

                        const blobUrl = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = blobUrl;
                        a.download = filename;
                        document.body.appendChild(a);
                        a.click();
                        a.remove();
                        setTimeout(() => URL.revokeObjectURL(blobUrl), 2000);
                    } catch (err) {
                        console.error('Failed to download ZIP', err);
                        try { globalThis.MHRToast && globalThis.MHRToast.show('Failed to download images', false); } catch (e) { console.debug('Toast unavailable', e); }
                    }
                });
            }
        });
    });
})();
