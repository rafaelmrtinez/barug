(function () {
    'use strict';

    function ensureContainer(containerId = 'mhrToastContainer') {
        let container = document.getElementById(containerId);
        if (!container) {
            container = document.createElement('div');
            container.id = containerId;
            container.className = 'position-fixed top-0 end-0 p-3';
            container.style.zIndex = '10800';
            document.body.appendChild(container);
        }
        return container;
    }

    function createToastElement(message, isSuccess) {
        const toastEl = document.createElement('div');
        toastEl.className = 'toast align-items-center text-bg-' + (isSuccess ? 'success' : 'danger') + ' border-0';
        toastEl.role = 'alert';
        toastEl.ariaLive = 'assertive';
        toastEl.ariaAtomic = 'true';

        const toastBody = document.createElement('div');
        toastBody.className = 'd-flex';
        const body = document.createElement('div');
        body.className = 'toast-body';
        body.textContent = message;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn-close btn-close-white me-2 m-auto';
        btn.setAttribute('data-bs-dismiss', 'toast');
        btn.ariaLabel = 'Close';

        toastBody.appendChild(body);
        toastBody.appendChild(btn);
        toastEl.appendChild(toastBody);
        return toastEl;
    }

    function show(message, isSuccess = false, { delay = 4000, containerId = 'mhrToastContainer' } = {}) {
        try {
            const container = ensureContainer(containerId);
            const toastEl = createToastElement(String(message), Boolean(isSuccess));
            container.appendChild(toastEl);

            const bsToast = globalThis.bootstrap ? new globalThis.bootstrap.Toast(toastEl, { delay }) : null;
            if (bsToast) bsToast.show();

            // remove after hidden
            toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
            // fallback remove after delay if Bootstrap not present
            if (!bsToast) setTimeout(() => toastEl.remove(), delay + 100);
        } catch (_err) {
            // final fallback to console if DOM manipulation fails
            try { console.warn('MHRToast fallback:', message); } catch (_e) { /* ignore */ }
        }
    }

    // Expose a minimal reusable API on globalThis under a single namespace
    if (!globalThis.MHRToast) {
        globalThis.MHRToast = { show };
    } else if (typeof globalThis.MHRToast.show !== 'function') {
        globalThis.MHRToast.show = show;
    }

})();
