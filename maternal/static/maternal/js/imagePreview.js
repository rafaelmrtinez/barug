/*
 * imagePreview.js
 * Lightweight preview helper for laboratory image uploads.
 * When a user selects files in the rendered file input, thumbnails are
 * displayed inside the corresponding `.upload-gallery` element.
 *
 * The template renders preview links like:
 * <a class="preview-uploads-link" data-input-id="{{ lab_form.cbc_images.id_for_label }}" data-gallery-id="gallery-cbc">Preview uploads</a>
 * and a container <div id="gallery-cbc" class="upload-gallery collapse"></div>
 */

(function () {
	'use strict';

	if (globalThis.__imagePreviewAttached) return;
	globalThis.__imagePreviewAttached = true;

	function makeThumbnail(file) {
		const img = document.createElement('img');
		img.className = 'rounded border';
		img.style.width = '84px';
		img.style.height = '84px';
		img.style.objectFit = 'cover';
		img.style.cursor = 'pointer';

		const url = URL.createObjectURL(file);
		img.src = url;
		// When clicked show larger image in the preview modal (if available),
		// otherwise fallback to opening in a new tab.
		img.addEventListener('click', function () {
			showPreviewModal(url, /* isBlob */ true, img);
		});
		// Remember url and filename on element so callers can revoke later and
		// provide a sensible download name.
		img._blobUrl = url;
		try { img._fileName = file.name || null; } catch (_e) { img._fileName = null; }
		return img;
	}

	function makeThumbnailFromUrl(url) {
		const img = document.createElement('img');
		img.className = 'rounded border';
		img.style.width = '84px';
		img.style.height = '84px';
		img.style.objectFit = 'cover';
		img.style.cursor = 'pointer';
		img.src = url;
		img.addEventListener('click', function () { showPreviewModal(url, /* isBlob */ false, img); });
		try { img._remoteName = (new URL(url)).pathname.split('/').pop() || null; } catch (_e) { img._remoteName = null; }
		return img;
	}

	// Show image in modal if modal exists, else open in new tab. We pass the
	// thumbnail element so we can optionally manage focus or cleanup.
	function showPreviewModal(src, _isBlob, _thumbEl) {
		try {
			const modalEl = document.getElementById('imagePreviewModal');
			const modalImg = document.getElementById('imagePreviewModalImg');
			if (modalEl && modalImg) {
				modalImg.src = src;
				// Ensure modal instance exists (Bootstrap 5)
				if (globalThis.bootstrap && typeof globalThis.bootstrap.Modal !== 'undefined') {
					const inst = globalThis.bootstrap.Modal.getOrCreateInstance(modalEl);
					inst.show();
					return;
				}
			}
		} catch (_e) {
			// fallthrough to window.open
		}
		// Fallback: open in new tab
		globalThis.open && globalThis.open(src, '_blank');
	}

	function clearGallery(gallery) {
		if (!gallery) return;
		// revoke blob urls used by thumbnails
		Array.from(gallery.querySelectorAll('img')).forEach(function (img) {
			try { if (img._blobUrl) URL.revokeObjectURL(img._blobUrl); } catch (_e) { /* ignore */ }
		});
		gallery.innerHTML = '';
	}

	function renderFilesIntoGallery(files, gallery, existingUrls) {
		clearGallery(gallery);
		const anyExisting = Array.isArray(existingUrls) && existingUrls.length > 0;
		const anyFiles = files && files.length > 0;
		if (!anyExisting && !anyFiles) {
			const empty = document.createElement('div');
			empty.className = 'text-muted small';
			empty.textContent = 'No uploads selected.';
			gallery.appendChild(empty);
			return;
		}

		const row = document.createElement('div');
		// Render thumbnails in a horizontal, scrollable row so groups display
		// inline rather than stacking vertically.
		row.className = 'd-flex flex-nowrap gap-2';
		row.style.cssText = 'overflow-x: auto; padding: .25rem 0; -webkit-overflow-scrolling: touch;';

		// Render existing server-side images first (if any)
		if (anyExisting) {
			existingUrls.forEach(function (u) {
				if (!u || typeof u !== 'string') return;
				const thumb = makeThumbnailFromUrl(u);
				row.appendChild(thumb);
			});
		}

		// Then render newly selected files
		if (anyFiles) {
			Array.from(files).forEach(function (file) {
				if (!file || !file.type || !file.type.startsWith('image/')) return;
				const thumb = makeThumbnail(file);
				row.appendChild(thumb);
			});
		}

		gallery.appendChild(row);
	}

	document.addEventListener('DOMContentLoaded', function () {
		const links = document.querySelectorAll('.preview-uploads-link');
		links.forEach(function (link) {
			const inputId = link.getAttribute('data-input-id');
			const galleryId = link.getAttribute('data-gallery-id');
			if (!inputId || !galleryId) return;

			let input = document.getElementById(inputId);
			const gallery = document.getElementById(galleryId);
			if (!gallery) return;
			// fallback: try to locate the file input by name or within the same form
			if (!input) {
				input = document.querySelector(`input[name="${inputId}"]`) || link.closest('form') && link.closest('form').querySelector('input[type="file"]');
			}
			if (!input) return;

			// Render currently selected files when the preview link is opened.
			// Use a short timeout to let Bootstrap toggle the collapse state.
			link.addEventListener('click', function () {
				setTimeout(function () {
					// Always attempt to render the currently selected files so
					// users see previews even if the collapse timing is delayed.
					const existingJson = input.getAttribute('data-existing-images') || input.dataset.existingImages || null;
					let existing = [];
					if (existingJson) {
						try { existing = JSON.parse(existingJson) || []; } catch (_e) { existing = []; }
					}
					renderFilesIntoGallery(input.files, gallery, existing);
				}, 150);
			});

			// When the collapse is hidden, clear thumbnails to save memory.
			// Bootstrap will fire the `hidden.bs.collapse` event; listen for it
			// if available, else fallback to checking class on toggle.
			gallery.addEventListener('hidden.bs.collapse', function () { clearGallery(gallery); });

			// When user selects files, immediately show previews (even if gallery
			// is collapsed). This gives immediate feedback prior to saving.
			input.addEventListener('change', function () {
				const existingJson = input.getAttribute('data-existing-images') || input.dataset.existingImages || null;
				let existing = [];
				if (existingJson) {
					try { existing = JSON.parse(existingJson) || []; } catch (_e) { existing = []; }
				}
				renderFilesIntoGallery(this.files, gallery, existing);
			});
		});
	});
})();

