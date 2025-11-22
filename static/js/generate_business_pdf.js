// JS to generate and open/download PDF for business list
// Attaches to elements with class `btn-generate-business-pdf`

(function () {
    'use strict';

    // Configuration
    const REQUEST_TIMEOUT_MS = 30_000; // 30s per attempt
    const MAX_RETRIES = 2; // number of retries after the first attempt
    const BACKOFF_BASE_MS = 1000; // exponential backoff base

    function showMessage(message, level = 'info') {
        // Simple alert fallback
        alert(message);
    }

    async function fetchWithTimeoutRetry(url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS, retries = MAX_RETRIES) {
        let attempt = 0;
        let lastError = null;
        while (attempt <= retries) {
            const controller = new AbortController();
            const id = setTimeout(() => controller.abort(), timeoutMs);
            try {
                const resp = await fetch(url, Object.assign({}, options, { signal: controller.signal }));
                clearTimeout(id);
                return resp; // success (even if !ok, caller will handle)
            } catch (err) {
                clearTimeout(id);
                lastError = err;
                // If abort due to timeout, err.name === 'AbortError'
                attempt += 1;
                if (attempt > retries) break;
                // exponential backoff
                const backoff = BACKOFF_BASE_MS * Math.pow(2, attempt - 1);
                // small jitter
                const jitter = Math.floor(Math.random() * 300);
                await new Promise((res) => setTimeout(res, backoff + jitter));
            }
        }
        throw lastError;
    }

    async function handleGenerateClick(event) {
        const btn = event.currentTarget;
        if (!btn) return;

        // Get current search and filter parameters
        const searchInput = document.getElementById('search');
        const bCategoryInput = document.querySelector('input[name="b_category"]');
        const ownershipTypeInput = document.querySelector('input[name="ownership_type"]');
        const statusInput = document.querySelector('input[name="status"]');
        
        const searchValue = searchInput ? searchInput.value.trim() : '';
        const bCategoryValue = bCategoryInput ? bCategoryInput.value.trim() : '';
        const ownershipTypeValue = ownershipTypeInput ? ownershipTypeInput.value.trim() : '';
        const statusValue = statusInput ? statusInput.value.trim() : '';

        // Build URL with current filters
        const params = new URLSearchParams();
        if (searchValue) params.set('search', searchValue);
        if (bCategoryValue) params.set('b_category', bCategoryValue);
        if (ownershipTypeValue) params.set('ownership_type', ownershipTypeValue);
        if (statusValue) params.set('status', statusValue);

        const url = `/secretary/api/business/pdf/?${params.toString()}`;

        // First try: open the real endpoint in a new tab
        try {
            const directTab = globalThis.open ? globalThis.open(url, '_blank') : null;
            if (directTab) {
                return; // done; server will handle rendering/download
            }
        } catch (errOpen) {
            // If opening throws for some reason, we'll fall back to fetch below
            console.warn('Direct open failed, will fallback to fetch:', errOpen);
        }

        // If popup was blocked (directTab is null), fallback to fetch+blob flow
        let originalHtml;
        try {
            btn.setAttribute('aria-busy', 'true');
            btn.disabled = true;
            originalHtml = btn.innerHTML;
            // spinner-compatible Bootstrap markup
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Generating...';

            const resp = await fetchWithTimeoutRetry(url, {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    Accept: 'application/pdf, application/json, text/*'
                }
            }, REQUEST_TIMEOUT_MS, MAX_RETRIES);

            if (!resp) {
                throw new Error('No response received');
            }

            if (!resp.ok) {
                // try to parse a JSON error
                let msg = `Server returned ${resp.status}`;
                try {
                    const j = await resp.json();
                    if (j && (j.message || j.detail)) msg = j.message || j.detail;
                } catch (_e) {
                    // ignore parse errors
                }
                console.error('Generate PDF error:', msg);
                showMessage('Failed to generate PDF: ' + msg, 'danger');
                return;
            }

            const contentType = resp.headers.get('content-type') || '';
            if (contentType.includes('application/pdf')) {
                const blob = await resp.blob();
                const blobUrl = globalThis.URL.createObjectURL(blob);
                // Open blob in a new tab
                const newTab = globalThis.open ? globalThis.open(blobUrl, '_blank') : null;
                if (!newTab) {
                    // fallback: start download with a suggested filename
                    const a = document.createElement('a');
                    a.href = blobUrl;
                    a.download = `business_list.pdf`;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                }
                // Release object URL after a short delay
                setTimeout(() => globalThis.URL.revokeObjectURL(blobUrl), 15000);
                showMessage('PDF generated — opening or downloading.', 'success');
            } else {
                // Not a PDF; try to parse and show message
                let text = await resp.text();
                try {
                    const json = JSON.parse(text);
                    text = json.detail || json.message || JSON.stringify(json);
                } catch (_e) {
                    // leave text
                }
                console.error('Generate PDF unexpected content-type:', contentType, text);
                showMessage('Failed to generate PDF: ' + text, 'danger');
            }
        } catch (err) {
            console.error('Generate PDF fetch error', err);
            const msg = err && err.name === 'AbortError' ? 'Request timed out. Please try again.' : (err && err.message) || 'An error occurred while generating the PDF.';
            showMessage(msg, 'danger');
        } finally {
            try {
                btn.removeAttribute('aria-busy');
                btn.disabled = false;
                if (typeof originalHtml !== 'undefined') {
                    btn.innerHTML = originalHtml;
                }
            } catch (_e) {
                /* ignore */
            }
        }
    }

    function init() {
        // Attach to existing buttons
        const buttons = document.querySelectorAll('.btn-generate-business-pdf');
        buttons.forEach((b) => {
            b.addEventListener('click', handleGenerateClick);
        });

        // Also use event delegation to catch dynamically-added buttons (if any)
        document.addEventListener('click', function (e) {
            const target = e.target.closest && e.target.closest('.btn-generate-business-pdf');
            if (target && !target._generatePdfAttached) {
                target.addEventListener('click', handleGenerateClick);
                target._generatePdfAttached = true;
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();