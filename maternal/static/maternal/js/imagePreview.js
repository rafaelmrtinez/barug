(function () {
	'use strict';

	// Avoid attaching the handler multiple times when script executes repeatedly
	if (globalThis.__downloadAllLabImagesAttached) return;
	globalThis.__downloadAllLabImagesAttached = true;

	// Helper: read the hidden input `#mhr-id`. Per requirement we only send
	// the single value contained in that hidden input. No scanning or loops.
	function getMhrIdFromHiddenInput() {
		const hid = document.getElementById('mhr-id');
		if (!hid) return null;
		const v = String(hid.value || '').trim();
		return v === '' ? null : v;
	}

	// Read CSRF token either from a hidden input (common in Django templates)
	// or from the csrftoken cookie. Returns null if not found.
	function readCsrfToken() {
		const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
		if (input && String(input.value || '').trim() !== '') return String(input.value);

		// Fallback to cookie named 'csrftoken'
		const name = 'csrftoken=';
		const ca = document.cookie.split(';');
		for (let i = 0; i < ca.length; i++) {
			const c = ca[i].trim();
			if (c.indexOf(name) === 0) return c.substring(name.length, c.length);
		}
		return null;
	}

	async function downloadZipForMhr(mhrId) {
		if (!mhrId) throw new Error('Missing maternal record id');

		const url = `/maternal/api/v1/mhr/lab-images/zip/`;
		const csrf = readCsrfToken();
		const headers = { 'Content-Type': 'application/json' };
		if (csrf) headers['X-CSRFToken'] = csrf;

		// Include CSRF in payload as well to satisfy APIs that expect it in form body
		const payload = { mhr_id: String(mhrId) };
		if (csrf) payload['csrfmiddlewaretoken'] = csrf;

		const resp = await fetch(url, {
			method: 'POST',
			credentials: 'same-origin',
			headers: headers,
			body: JSON.stringify(payload)
		});
		if (!resp.ok) {
			let msg = `Server returned ${resp.status}`;
			try {
				const j = await resp.json();
				if (j && j.message) msg = j.message;
			} catch (e) {
				// ignore JSON parse errors
				console.debug('downloadAll: no json body', e);
			}
			throw new Error(msg);
		}

		const blob = await resp.blob();
		// Try to read filename from Content-Disposition
		let filename = `lab_images_mhr_${mhrId}.zip`;
		try {
			const cd = resp.headers.get('Content-Disposition') || '';
			const m = cd.match(/filename\*=UTF-8''([^;\n\r]+)/i) || cd.match(/filename="?([^";\n\r]+)"?/i);
			if (m && m[1]) filename = decodeURIComponent(m[1]);
		} catch (e) {
			console.debug('downloadAll: cannot parse filename header', e);
		}

		const blobUrl = URL.createObjectURL(blob);
		try {
			const a = document.createElement('a');
			a.href = blobUrl;
			a.download = filename;
			document.body.appendChild(a);
			a.click();
			a.remove();
		} finally {
			setTimeout(() => URL.revokeObjectURL(blobUrl), 2000);
		}
	}

	document.addEventListener('DOMContentLoaded', function () {
		const btn = document.getElementById('btn-download-all-lab-images');
		if (!btn) return;

		btn.addEventListener('click', async function () {
			// prevent double clicks
			if (btn.disabled) return;
			btn.disabled = true;
			try {
				const mhrId = getMhrIdFromHiddenInput();
				if (!mhrId) {
					try { globalThis.MHRToast && globalThis.MHRToast.show('No maternal record id found on page', false); } catch (e) { console.debug('Toast unavailable', e); }
					return;
				}
				await downloadZipForMhr(mhrId);
			} catch (err) {
				console.error('Download all images failed', err);
				try { globalThis.MHRToast && globalThis.MHRToast.show(err.message || 'Failed to download images', false); } catch (e) { console.debug('Toast unavailable', e); }
			} finally {
				btn.disabled = false;
			}
		});
	});
})();

