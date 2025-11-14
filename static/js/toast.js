(function () {
    'use strict';

    // Default container id and z-index are configurable
    const DEFAULT_CONTAINER_ID = 'customToastContainer';
    const DEFAULT_Z_INDEX = '10800';

    function ensureContainer(containerId = DEFAULT_CONTAINER_ID) {
        let container = document.getElementById(containerId);
        if (!container) {
            container = document.createElement('div');
            container.id = containerId;
            container.className = 'position-fixed top-0 end-0 p-3';
            container.style.zIndex = DEFAULT_Z_INDEX;
            document.body.appendChild(container);
        }
        return container;
    }

    function createToastElement(message, variant) {
        const toastEl = document.createElement('div');
        toastEl.className = `toast align-items-center text-bg-${variant} border-0`;
        toastEl.setAttribute('role', 'alert');
        toastEl.setAttribute('aria-live', 'assertive');
        toastEl.setAttribute('aria-atomic', 'true');

        const toastBody = document.createElement('div');
        toastBody.className = 'd-flex';
        const body = document.createElement('div');
        body.className = 'toast-body';
        // Use textContent to avoid XSS from HTML input
        body.textContent = message;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn-close btn-close-white me-2 m-auto';
        btn.setAttribute('data-bs-dismiss', 'toast');
        btn.setAttribute('aria-label', 'Close');

        toastBody.appendChild(body);
        toastBody.appendChild(btn);
        toastEl.appendChild(toastBody);
        return toastEl;
    }

    // Show API: show(message, isSuccessOrOptions, options)
    // Backwards-compatible boolean second arg supported for isSuccess,
    // but passing options object is preferred: { type, delay, containerId }
    function show(message, isSuccessOrOptions = {}, options = {}) {
        try {
            // Normalize inputs
            let opts = {};
            if (typeof isSuccessOrOptions === 'boolean') {
                opts = Object.assign({}, options, { isSuccess: isSuccessOrOptions });
            } else if (isSuccessOrOptions && typeof isSuccessOrOptions === 'object') {
                opts = isSuccessOrOptions;
            }

            // Validate message
            const safeMessage = (message === null || message === undefined) ? '' : String(message);

            const delay = Number(opts.delay) || 4000;
            const containerId = String(opts.containerId || DEFAULT_CONTAINER_ID);

            // Determine variant from either opts.type or boolean isSuccess
            const type = (opts.type && String(opts.type).toLowerCase()) || (opts.isSuccess ? 'success' : 'error');
            const variantMap = { success: 'success', error: 'danger', danger: 'danger', info: 'primary', warning: 'warning', default: 'secondary' };
            const variant = variantMap[type] || 'secondary';

            const container = ensureContainer(containerId);
            const toastEl = createToastElement(safeMessage, variant);
            container.appendChild(toastEl);

            // If Bootstrap is loaded, use its Toast for show/hide lifecycle
            const bsToast = globalThis.bootstrap && typeof globalThis.bootstrap.Toast === 'function'
                ? new globalThis.bootstrap.Toast(toastEl, { delay })
                : null;

            if (bsToast) {
                bsToast.show();
            }

            // Remove after hidden (Bootstrap event) or after timeout fallback
            toastEl.addEventListener('hidden.bs.toast', () => {
                try { toastEl.remove(); } catch (_) { /* ignore */ }
            });

            if (!bsToast) {
                // Ensure removal even without Bootstrap (delay + small buffer)
                setTimeout(() => {
                    try { toastEl.remove(); } catch (_) { /* ignore */ }
                }, delay + 100);
            }
        } catch (err) {
            // Fallback to console if DOM manipulation fails
            try { console.warn('CustomToast fallback:', message, err); } catch (_) { /* ignore */ }
        }
    }

    // Expose a minimal reusable API on globalThis under `CustomToast`.
    // Do NOT overwrite if user code already defined a compatible API.
    if (!globalThis.CustomToast) {
        globalThis.CustomToast = { show };
    } else if (typeof globalThis.CustomToast.show !== 'function') {
        globalThis.CustomToast.show = show;
    }

    // CommonJS environment export for server bundlers
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = globalThis.CustomToast;
    }

})();
