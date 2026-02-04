// JS to generate and open/download Child Health Summary PDF for a given child record
// Mirrors maternal/static/maternal/js/generate_pdf_summary.js but targets the
// child report endpoint and elements with class `btn-generate-child-summary`.

(function () {
    'use strict';

    // Configuration
    const REQUEST_TIMEOUT_MS = 30_000; // 30s per attempt
    const MAX_RETRIES = 2; // number of retries after the first attempt
    const BACKOFF_BASE_MS = 1000; // exponential backoff base

    function showMessage(message, level = 'info') {
        // Prefer the project's MHRToast utility
        try {
            if (globalThis.MHRToast && typeof globalThis.MHRToast.show === 'function') {
                // MHRToast only supports success (green) or danger (red). Treat
                // anything other than explicit 'danger' as success so info
                // messages render as green.
                const isSuccess = String(level).toLowerCase() !== 'danger';
                globalThis.MHRToast.show(String(message), isSuccess);
                return;
            }
            if (typeof globalThis.showToast === 'function') {
                globalThis.showToast(message, level);
                return;
            }
            if (globalThis.mhrToast && typeof globalThis.mhrToast.show === 'function') {
                globalThis.mhrToast.show(message, level);
                return;
            }
        } catch (_e) {
            // ignore and fallback to alert
        }
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
                return resp;
            } catch (err) {
                clearTimeout(id);
                lastError = err;
                attempt += 1;
                if (attempt > retries) break;
                const backoff = BACKOFF_BASE_MS * Math.pow(2, attempt - 1);
                const jitter = Math.floor(Math.random() * 300);
                await new Promise((res) => setTimeout(res, backoff + jitter));
            }
        }
        throw lastError;
    }

    async function handleGenerateClick(event) {
        const btn = event.currentTarget;
        if (!btn) return;
        const childId = btn.dataset.childId || btn.getAttribute('data-child-id');
        if (!childId) {
            console.error('Generate Child PDF: missing child id on clicked element');
            showMessage('Unable to generate report: missing record id.', 'danger');
            return;
        }

        const url = `/child-health/api/v1/chr/report/?child_record_id=${encodeURIComponent(childId)}`;

        // Try opening the real endpoint first so browser gets headers/filename
        try {
            const directTab = globalThis.open ? globalThis.open(url, '_blank') : null;
            if (directTab) {
                showMessage('Opening report in a new tab...', 'info');
                return;
            }
        } catch (errOpen) {
            console.warn('Direct open failed, will fallback to fetch:', errOpen);
        }

        let originalHtml;
        try {
            btn.setAttribute('aria-busy', 'true');
            btn.disabled = true;
            originalHtml = btn.innerHTML;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Generating...';

            const resp = await fetchWithTimeoutRetry(url, {
                method: 'GET',
                credentials: 'same-origin',
                headers: { Accept: 'application/pdf, application/json, text/*' }
            }, REQUEST_TIMEOUT_MS, MAX_RETRIES);

            if (!resp) throw new Error('No response received');

            if (!resp.ok) {
                let msg = `Server returned ${resp.status}`;
                try {
                    const j = await resp.json();
                    if (j && (j.message || j.detail)) msg = j.message || j.detail;
                } catch (_e) {
                    /* ignore parse error */
                }
                console.error('Generate Child PDF error:', msg);
                showMessage('Failed to generate report: ' + msg, 'danger');
                return;
            }

            const contentType = resp.headers.get('content-type') || '';
            if (contentType.includes('application/pdf')) {
                const blob = await resp.blob();
                const blobUrl = globalThis.URL.createObjectURL(blob);
                const newTab = globalThis.open ? globalThis.open(blobUrl, '_blank') : null;
                if (!newTab) {
                    const a = document.createElement('a');
                    a.href = blobUrl;
                    a.download = `child_${childId}_summary.pdf`;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                }
                setTimeout(() => globalThis.URL.revokeObjectURL(blobUrl), 15000);
                showMessage('PDF generated — opening or downloading.', 'success');
            } else {
                let text = await resp.text();
                try {
                    const json = JSON.parse(text);
                    text = json.detail || json.message || JSON.stringify(json);
                } catch (_e) {
                    /* ignore parse error */
                }
                console.error('Generate Child PDF unexpected content-type:', contentType, text);
                showMessage('Failed to generate report: ' + text, 'danger');
            }
        } catch (err) {
            console.error('Generate Child PDF fetch error', err);
            const msg = err && err.name === 'AbortError' ? 'Request timed out. Please try again.' : (err && err.message) || 'An error occurred while generating the report.';
            showMessage(msg, 'danger');
        } finally {
            try {
                btn.removeAttribute('aria-busy');
                btn.disabled = false;
                if (typeof originalHtml !== 'undefined') btn.innerHTML = originalHtml;
            } catch (_e) {
                /* ignore */
            }
        }
    }

    function init() {
        const buttons = document.querySelectorAll('.btn-generate-child-summary');
        buttons.forEach((b) => b.addEventListener('click', handleGenerateClick));

        document.addEventListener('click', function (e) {
            const target = e.target.closest && e.target.closest('.btn-generate-child-summary');
            if (target && !target._attachedGenerateChild) {
                target.addEventListener('click', handleGenerateClick);
                target._attachedGenerateChild = true;
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
