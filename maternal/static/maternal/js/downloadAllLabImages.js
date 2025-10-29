(function () {
    'use strict';

    // Compute the latest maternal record id available on the page by scanning
    // `data-mhr-id` attributes and the records table first column. Returns string or null.
    function findLatestMhrFromDom() {
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
        if (!ids.length) return null;
        return String(Math.max.apply(null, ids));
    }

    async function downloadZipForMhr(mhrId) {
        if (!mhrId) throw new Error('Missing maternal record id');

        const url = `/maternal/api/v1/mhr/lab-images/zip/?mhr_id=${encodeURIComponent(mhrId)}`;
        const resp = await fetch(url, { method: 'GET', credentials: 'same-origin' });
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
                const mhrId = findLatestMhrFromDom();
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
