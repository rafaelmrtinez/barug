(function(){
'use strict';

function getCookie(name) {
    const v = document.cookie.match('(^|;)\s*' + name + '\s*=\s*([^;]+)');
    return v ? v.pop() : '';
}

async function postMarkComplete(evt) {
    evt.preventDefault();
    const btn = evt.currentTarget;
    const form = document.getElementById('prenatal-form');
    if (!form) return;

    // collect mhr id
    const mhrId = form.dataset.mhrId || null;
    if (!mhrId) {
        console && console.warn && console.warn('prenatal mark complete: missing mhr id');
        return;
    }

    // collect CSRF
    const csrfInput = form.querySelector('input[name="csrfmiddlewaretoken"]');
    const csrfToken = csrfInput ? csrfInput.value : getCookie('csrftoken');

    // disable all related buttons (submit/reset) and show spinner on clicked button
    const buttons = Array.from(form.querySelectorAll('button[type="submit"], button[type="reset"], button[name="mark_complete"], input[type="submit"], input[type="reset"]'));
    const origStates = buttons.map(b => ({ el: b, disabled: b.disabled, tag: b.tagName.toLowerCase(), html: b.tagName.toLowerCase() === 'button' ? b.innerHTML : b.value }));

    try {
        // replace button text with spinner
        if (btn && btn.tagName && btn.tagName.toLowerCase() === 'button') {
            btn.innerHTML = '<span class="spinner-grow spinner-grow-sm" role="status" aria-hidden="true"></span> Completing...';
        }
        buttons.forEach(b => { try { b.disabled = true; } catch (__) {} });

        const endpoint = '/maternal/api/v1/mhr/visit/complete/';
        const payload = { mhr_id: mhrId };

        const resp = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {}),
            },
            credentials: 'same-origin',
            body: JSON.stringify(payload),
        });

        let data = null;
        try { data = await resp.json(); } catch (_) { data = null; }

        if (!resp.ok || (data && data.success === false)) {
            const msg = (data && data.message) ? data.message : 'Failed to mark visit complete.';
            try { alert(msg); } catch (_) { console.error(msg); }
            return;
        }

        // success — reload or redirect if provided
        if (data && data.redirect) { globalThis.location.href = data.redirect; return; }
        globalThis.location.reload();
    } catch (err) {
        console.error('prenatal mark complete error', err);
        try { alert('An unexpected error occurred while marking complete.'); } catch (_) {}
    } finally {
        // restore
        try {
            for (const s of origStates) {
                try { s.el.disabled = !!s.disabled; } catch (_) {}
                try {
                    if (s.tag === 'button') s.el.innerHTML = s.html;
                    else s.el.value = s.html;
                } catch (_) {}
            }
        } catch (_) {}
    }
}

function init() {
    const form = document.getElementById('prenatal-form');
    if (!form) return;
    // attach to any button[name=mark_complete]
    const markBtn = form.querySelector('button[name="mark_complete"]');
    if (markBtn) markBtn.addEventListener('click', postMarkComplete);
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();

})();
