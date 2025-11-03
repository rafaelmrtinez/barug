// API client for FAQ ingestion endpoint
(function () {
	'use strict';

	const uploadBtn = document.getElementById('faqUploadBtn');
	const fileInput = document.getElementById('faqFileInput');
	const _previewContainer = document.getElementById('faqPreviewContainer');
	const spinner = document.getElementById('faqSpinner');
	const previewBtn = document.getElementById('faqPreviewBtn');

	const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5MB client-side
	const MAX_ROWS = 500;
	// API endpoint to call (server-side route)
	const ENDPOINT = '/docs/api/faq-upload/';

	function getCookie(name) {
		const value = `; ${document.cookie}`;
		const parts = value.split(`; ${name}=`);
		if (parts.length === 2) return parts.pop().split(';').shift();
		return null;
	}

	function showToast(msg, success) {
		try {
			if (globalThis.MHRToast && typeof globalThis.MHRToast.show === 'function') {
				// Clear any existing toasts in the shared container so transient
				// messages (like "Validating...") don't pile up with results.
				try {
					const c = document.getElementById('mhrToastContainer');
					if (c) {
						while (c.firstChild) c.removeChild(c.firstChild);
					}
				} catch (_e) { /* ignore DOM clearing failures */ }
				globalThis.MHRToast.show(String(msg), Boolean(success === true));
			} else {
				console.warn('MHRToast not available:', msg);
				// eslint-disable-next-line no-alert
				alert(String(msg));
			}
		} catch (err) {
			console.warn('Toast failed:', err, msg);
		}
	}

	async function validateWorkbookHeaders(file) {
		try {
			const ab = await file.arrayBuffer();
			const wb = XLSX.read(ab, { type: 'array' });
			const sheetName = wb.SheetNames[0];
			const sheet = wb.Sheets[sheetName];
			// Read all rows as arrays. Note: some workbooks have a large used-range
			// (many empty rows). Filter out fully-empty rows to get the real row
			// count and a reliable header row.
			const rows = XLSX.utils.sheet_to_json(sheet, { header: 1 });
			if (!rows || rows.length === 0) return { ok: false, reason: 'Empty sheet' };
			const nonEmptyRows = rows.filter(r => Array.isArray(r) && r.some(c => {
				const v = (c === null || c === undefined) ? '' : String(c).trim();
				return v !== '';
			}));
			if (!nonEmptyRows || nonEmptyRows.length === 0) return { ok: false, reason: 'Empty sheet' };
			const headerRow = nonEmptyRows[0];
			const header = headerRow.map(h => (h || '').toString().trim().toLowerCase());
			// Consider only non-empty header labels when validating column count
			const headerLabels = header.filter(h => h !== '');
			if (headerLabels.length !== 2) return { ok: false, reason: 'Sheet must have exactly two columns: question and answer' };
			const set = new Set(headerLabels);
			if (!(set.has('question') && set.has('answer'))) return { ok: false, reason: 'Headers must be exactly "question" and "answer"' };
			const totalRows = Math.max(0, nonEmptyRows.length - 1);
			if (totalRows > MAX_ROWS) return { ok: false, reason: `Too many rows (${totalRows}). Limit is ${MAX_ROWS}.` };
			return { ok: true, sheetName, totalRows };
		} catch (err) {
			console.debug('validateWorkbookHeaders error', err);
			return { ok: false, reason: 'Failed to parse workbook for validation' };
		}
	}

	if (!uploadBtn) return; // nothing to wire

	uploadBtn.addEventListener('click', async function (_e) {
		// Synchronous-seeming flow: disable UI, validate (await), then upload
		try {
			if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
				showToast('Please select an Excel file to upload.', false);
				return;
			}
			const file = fileInput.files[0];

			// Basic sanitation of filename
			const rawName = (file.name || '').toString();
			const filename = rawName.trim().replace(/\s+/g, ' ').slice(0, 255);
			const ext = (filename.split('.').pop() || '').toLowerCase();
			const allowedExt = ['xlsx', 'xls'];

			if (!filename) {
				showToast('Invalid filename.', false);
				return;
			}
			if (!allowedExt.includes(ext)) {
				showToast('Invalid file type. Only Excel (.xlsx, .xls) files are allowed.', false);
				return;
			}
			if (file.size > MAX_FILE_SIZE) {
				showToast(`File too large. Max ${MAX_FILE_SIZE / (1024 * 1024)} MB allowed.`, false);
				return;
			}

			// disable UI and show spinner BEFORE validation
			uploadBtn.disabled = true;
			if (previewBtn) previewBtn.disabled = true;
			try { spinner.style.display = 'inline-block'; } catch (_e) { /* ignore */ }

			// validate workbook headers and rows count
			showToast('Validating workbook...', true);
			const v = await validateWorkbookHeaders(file);			if (!v.ok) {
                console.log(`Validation failed: ${JSON.stringify(v)}`);
				showToast(`Validation failed: ${v.reason}`, false);
				return;
			}

			// build FormData and append sanitized filename so server receives clean name
			const fd = new FormData();
			fd.append('file', file, filename);

			const csrf = getCookie('csrftoken');
			const resp = await fetch(ENDPOINT, {
				method: 'POST',
				body: fd,
				headers: csrf ? { 'X-CSRFToken': csrf } : {},
				credentials: 'same-origin',
			});

			const data = await resp.json().catch(() => null);
			if (resp.ok) {
				showToast((data && data.message) ? data.message : 'FAQs uploaded successfully.', true);

				// Reset paginator state via its public API if available.
				try {
					if (globalThis.FAQPaginator && typeof globalThis.FAQPaginator.reset === 'function') {
						globalThis.FAQPaginator.reset();
					} else {
						// Fallback: clear DOM and dispatch change so older code reacts
						if (fileInput) {
							fileInput.value = '';
							try { fileInput.dispatchEvent(new Event('change', { bubbles: true })); } catch (_e) { /* ignore */ }
						}
						if (_previewContainer) {
							_previewContainer.innerHTML = '';
							try { _previewContainer.style.display = 'none'; } catch (_e) { /* ignore */ }
						}
						if (previewBtn) previewBtn.disabled = true;
					}
				} catch (_e) {
					console.debug('Failed to reset paginator after upload', _e);
				}

			} else {
				const msg = (data && data.message) ? data.message : `Upload failed: ${resp.status}`;
				showToast(msg, false);
			}

		} catch (err) {
			console.error(err);
			showToast('Unexpected error during upload.', false);
		} finally {
			try { spinner.style.display = 'none'; } catch (_e) { /* ignore */ }
			uploadBtn.disabled = false;
			try { if (fileInput && fileInput.files && fileInput.files.length) previewBtn.disabled = false; } catch (_e) { /* ignore */ }
		}
	});

})();

