// static/js/modal.js
(function(){
  if(!window.bootstrap){
    console.warn('BarugModal: Bootstrap not detected. Ensure {% bootstrap_javascript %} or bootstrap.bundle is loaded.');
  }
})();

const BarugModal = (() => {
  const _instances = new Map();

  function _injectDefaultModal(modalId){
    const html = `
      <div class="modal fade barug-modal" id="${modalId}" tabindex="-1" aria-labelledby="${modalId}-label" aria-hidden="true" data-bs-backdrop="static" data-bs-keyboard="false">
        <div class="modal-dialog">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title fw-bold" id="${modalId}-label">Dialog</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body" id="${modalId}-body"><p class="mb-0 text-muted">Content</p></div>
            <div class="modal-footer d-flex gap-2">
              <button type="button" class="barug-btn barug-btn-ghost" data-role="secondary" data-bs-dismiss="modal">Cancel</button>
              <button type="button" class="barug-btn barug-btn-primary" data-role="primary">OK</button>
            </div>
          </div>
        </div>
      </div>`;
    const wrap = document.createElement('div');
    wrap.innerHTML = html;
    document.body.appendChild(wrap.firstElementChild);
  }

  function _ensureInstance(modalId){
    let el = document.getElementById(modalId);
    if(!el){
      _injectDefaultModal(modalId);
      el = document.getElementById(modalId);
      if(!el) throw new Error(`Modal #${modalId} not found`);
    }
    let inst = _instances.get(modalId);
    if(!inst){
      if(!window.bootstrap || !window.bootstrap.Modal){
        throw new Error('Bootstrap Modal is not available on window.bootstrap.Modal');
      }
      inst = new bootstrap.Modal(el, { backdrop:'static', keyboard:false });
      _instances.set(modalId, inst);
    }
    return { el, inst };
  }

  function _wireButtons(el, {onPrimary, onSecondary}={}){
    const primaryBtn = el.querySelector('[data-role="primary"]');
    const secondaryBtn = el.querySelector('[data-role="secondary"]');
    primaryBtn && primaryBtn.replaceWith(primaryBtn.cloneNode(true));
    secondaryBtn && secondaryBtn.replaceWith(secondaryBtn.cloneNode(true));
    const p = el.querySelector('[data-role="primary"]');
    const s = el.querySelector('[data-role="secondary"]');
    if(p && typeof onPrimary === 'function') p.addEventListener('click', onPrimary);
    if(s && typeof onSecondary === 'function') s.addEventListener('click', onSecondary);
  }

  function _setTitle(el, title){ const h = el.querySelector('.modal-title'); if(h) h.textContent = title ?? ''; }
  function _setBodyHtml(el, html){ const b = el.querySelector('.modal-body'); if(b) b.innerHTML = html ?? ''; }

  function _setLoading(el, isLoading=true){
    const footer = el.querySelector('.modal-footer');
    const primary = footer?.querySelector('[data-role="primary"]');
    const allBtns = footer?.querySelectorAll('button');
    if(isLoading){
      allBtns?.forEach(b => b.setAttribute('disabled','disabled'));
      if(primary){
        primary.dataset.orig = primary.innerHTML;
        primary.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status"></span>Working...`;
      }
    }else{
      allBtns?.forEach(b => b.removeAttribute('disabled'));
      if(primary && primary.dataset.orig){
        primary.innerHTML = primary.dataset.orig;
        delete primary.dataset.orig;
      }
    }
  }

  function open(modalId, opts={}){
    const { el, inst } = _ensureInstance(modalId);
    const { title, bodyHtml, onPrimary, onSecondary } = opts;
    if(title !== undefined) _setTitle(el, title);
    if(bodyHtml !== undefined) _setBodyHtml(el, bodyHtml);
    _wireButtons(el, { onPrimary, onSecondary });
    inst.show();
    return { close: () => inst.hide(), setLoading: v => _setLoading(el, v) };
  }

  function close(modalId){ _ensureInstance(modalId).inst.hide(); }

  function alert(modalId, { title="Notice", bodyHtml="" }={}){
    return new Promise(resolve => {
      const { el, inst } = _ensureInstance(modalId);
      _setTitle(el, title); _setBodyHtml(el, bodyHtml);
      const secondary = el.querySelector('[data-role="secondary"]'); secondary && secondary.classList.add('d-none');
      const primary = el.querySelector('[data-role="primary"]');
      if(primary){ primary.textContent = "OK"; primary.onclick = () => { inst.hide(); resolve(true); }; }
      el.addEventListener('hidden.bs.modal', function onHide(){ el.removeEventListener('hidden.bs.modal', onHide); resolve(true); });
      inst.show();
    });
  }

  function confirm(modalId, { title="Confirm", bodyHtml="Proceed?" }={}){
    return new Promise(resolve => {
      const { el, inst } = _ensureInstance(modalId);
      _setTitle(el, title); _setBodyHtml(el, bodyHtml);
      const s = el.querySelector('[data-role="secondary"]'); const p = el.querySelector('[data-role="primary"]');
      if(s){ s.classList.remove('d-none'); s.textContent = "Cancel"; s.onclick = () => { inst.hide(); resolve(false); }; }
      if(p){ p.textContent = "Confirm"; p.onclick = () => { inst.hide(); resolve(true); }; }
      inst.show();
    });
  }

  function form(modalId, { title="Submit", bodyHtml="", onSubmit }={}){
    return new Promise(resolve => {
      const { el, inst } = _ensureInstance(modalId);
      _setTitle(el, title); _setBodyHtml(el, bodyHtml);
      const p = el.querySelector('[data-role="primary"]'); const s = el.querySelector('[data-role="secondary"]');
      s && (s.textContent = "Cancel", s.onclick = () => { inst.hide(); resolve({ ok:false, reason:"cancel" }); });
      p && (p.textContent = "Save");
      p && (p.onclick = async () => {
        const form = el.querySelector('form'); if(!form){ inst.hide(); return resolve({ ok:false, reason:"no-form" }); }
        const fd = new FormData(form); const data = Object.fromEntries(fd.entries());
        form.querySelectorAll('.uppercase').forEach(inp => { if(inp.name && data[inp.name]) data[inp.name] = String(data[inp.name]).toUpperCase(); });
        _setLoading(el, true);
        try{
          const res = onSubmit ? await onSubmit(data, { setLoading: v => _setLoading(el, v) }) : { ok:true };
          _setLoading(el, false);
          if(res?.ok){ inst.hide(); resolve(res); }
          else if(res?.error){
            const alert = document.createElement('div'); alert.className = 'alert alert-danger'; alert.textContent = res.error;
            el.querySelector('.modal-body').prepend(alert);
          }
        }catch(e){
          _setLoading(el, false);
          const alert = document.createElement('div'); alert.className = 'alert alert-danger'; alert.textContent = (e?.message || 'Something went wrong');
          el.querySelector('.modal-body').prepend(alert);
        }
      });
      inst.show();
    });
  }

  return { open, alert, confirm, form, close, setLoading: (id, v)=>_setLoading(document.getElementById(id), v) };
})();

window.BarugModal = BarugModal;
