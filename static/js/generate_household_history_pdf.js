// JS to generate and open/download PDF for household history list
// Attaches to elements with class `btn-generate-household-history-pdf`

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

        // Get current search and filter parameters from URL
        const urlParams = new URLSearchParams(window.location.search);
        const quarter = urlParams.get('quarter') || '';
        const year = urlParams.get('year') || '';
        const searchValue = urlParams.get('search') || '';
        const houseTypeValue = urlParams.get('house_type') || '';
        const houseOwnershipValue = urlParams.get('house_ownership') || '';

        // Build URL with current filters
        const params = new URLSearchParams();
        if (quarter) params.set('quarter', quarter);
        if (year) params.set('year', year);
        if (searchValue) params.set('search', searchValue);
        if (houseTypeValue) params.set('house_type', houseTypeValue);
        if (houseOwnershipValue) params.set('house_ownership', houseOwnershipValue);

        // Detect role from current URL path
        const currentPath = window.location.pathname;
        let rolePrefix = '/bhw';
        if (currentPath.startsWith('/secretary/')) rolePrefix = '/secretary';
        if (currentPath.startsWith('/captain/')) rolePrefix = '/captain';
        
        const url = `${rolePrefix}/api/household/history/pdf/?${params.toString()}`;

        // Open the PDF endpoint in a new tab for preview
        const newTab = globalThis.open ? globalThis.open(url, '_blank') : null;
        if (newTab) {
            return; // PDF will open in new tab
        }
        
        // If popup was blocked, show message
        alert('Please allow popups for this site to preview the PDF.');
    }

    function init() {
        // Attach to existing buttons
        const buttons = document.querySelectorAll('.btn-generate-household-history-pdf');
        buttons.forEach((b) => {
            b.addEventListener('click', handleGenerateClick);
        });

        // Also use event delegation to catch dynamically-added buttons (if any)
        document.addEventListener('click', function (e) {
            const target = e.target.closest && e.target.closest('.btn-generate-household-history-pdf');
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
