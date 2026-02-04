/* =========================================================
 * Form Builder – FULL updated JS (drop-in)
 * - Robust config read (includes form_code)
 * - KP-17: repudiation capture (auto-fills "Requested By")
 * - KP-23: "who filed?" capture
 * - KP-9-P2: Officer’s Return helpers
 *   • Served-To & Respondent fields restricted to RESPONDENTS only
 *   • Local typeahead for respondents (no cross-mixing with complainants)
 *   • Auto-prefill first respondents into lines & signatures
 *   • Narrative + proxy visibility driven by mode (1–4)
 * - Save/Submit flow with CSRF
 * ======================================================= */

/* ===== Read config from the HTML ===== */
function fbGetConfig() {
  const el = document.getElementById("fb-config");
  if (!el) return {};
  try { return JSON.parse(el.textContent || "{}"); }
  catch (_) { return {}; }
}
const FB = fbGetConfig();

/* ===== Helpers: KP detection ===== */
function normCode() { return String(FB.form_code || "").trim().toUpperCase(); }
function isKP17() { return Number(FB.form_id) === 17 || normCode() === "KP-17"; }
function isKP23() { return Number(FB.form_id) === 23 || normCode() === "KP-23"; }
function isKP9() { return Number(FB.form_id) === 9 || normCode() === "KP-9"; }
function isKP9P2() {
  const n = normCode().replace(/\s+/g, "");
  return n === "KP-9-P2" || n === "KP-9P2";
}

/* ===== CSRF ===== */
function getCookie(name){
  const m = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return m ? decodeURIComponent(m[2]) : null;
}
const CSRF = getCookie('csrftoken');

/* ===== Safe URL getter ===== */
function safeUrl(k){
  const u = FB?.urls?.[k];
  if (!u) throw new Error(`Missing URL config: ${k}`);
  return u;
}

const qs = s => document.querySelector(s);
const formEl    = qs("#formFields");
const saveBtn   = qs("#saveBtn");
const submitBtn = qs("#submitBtn");

const toastOkEl   = qs("#toastOk");
const toastWarnEl = qs("#toastWarn");
const toastOk   = toastOkEl ? new bootstrap.Toast(toastOkEl, { delay: 2200 }) : null;
const toastWarn = toastWarnEl ? new bootstrap.Toast(toastWarnEl, { delay: 3000 }) : null;

function showOk(msg){ if (toastOkEl) { qs("#toastOk .msg").textContent = msg || "Saved."; toastOk.show(); } }
function showWarn(msg){ if (toastWarnEl) { qs("#toastWarn .msg").textContent = msg || "Something went wrong."; toastWarn.show(); } }

/* ===== Visible-only validation helpers ===== */
function isVisiblyRequired(ctrl){
  const wrap = ctrl.closest('.kp-field');
  const offscreen = wrap?.classList.contains('kp-offscreen');
  const hidden = (!ctrl.offsetParent && getComputedStyle(ctrl).display === 'none') ||
                 (wrap && getComputedStyle(wrap).display === 'none');
  return !offscreen && !hidden && ctrl.hasAttribute('required');
}
function checkVisibleValidity(form){
  let firstInvalid = null;
  for (const el of form.querySelectorAll('[data-field-id]')){
    if (!isVisiblyRequired(el)) continue;
    const was = el.required;
    el.required = true;
    const ok = el.checkValidity();
    el.required = was;
    if (!ok && !firstInvalid) firstInvalid = el;
  }
  if (firstInvalid){
    form.classList.add('was-validated');
    firstInvalid.focus({ preventScroll:false });
    return false;
  }
  return true;
}

/* ===== Collectors ===== */
function collectAnswers(){
  const obj = {};
  formEl.querySelectorAll("[data-field-id]").forEach(i=>{
    const fid = i.getAttribute("data-field-id");
    if (i.type === "checkbox"){
      obj[fid] = !!i.checked;
    } else {
      obj[fid] = i.value;
    }
  });
  return obj;
}
function collectAnswersByCode(){
  const obj = {};
  formEl.querySelectorAll(".kp-field [data-field-id]").forEach(i=>{
    const code = (i.dataset.code || '').toLowerCase();
    if (!code) return;
    obj[code] = (i.type === "checkbox") ? !!i.checked : i.value;
  });
  return obj;
}

/* ===== Busy toggles ===== */
function setBusy(btn, busy){
  btn?.querySelector(".when-idle")?.classList.toggle("d-none", busy);
  btn?.querySelector(".when-busy")?.classList.toggle("d-none", !busy);
  if (btn) btn.disabled = !!busy;
}
function setBusyEl(btn, busy){
  btn?.querySelector(".when-idle")?.classList.toggle("d-none", busy);
  btn?.querySelector(".when-busy")?.classList.toggle("d-none", !busy);
  if (btn) btn.disabled = !!busy;
}

/* ===== Save / Submit ===== */
async function doSave(){
  if (!checkVisibleValidity(formEl)){
    showWarn("Please complete required fields.");
    throw new Error("Invalid form");
  }
  try{
    setBusy(saveBtn, true);
    const fd = new FormData(formEl);
    fd.set("answers", JSON.stringify(collectAnswers()));
    fd.set("answers_by_code", JSON.stringify(collectAnswersByCode()));
    const res = await fetch(safeUrl('save_answers'), { method:"POST", headers:{"X-CSRFToken":CSRF}, body:fd });
    if(!res.ok) throw new Error("HTTP " + res.status);
    const j = await res.json();
    if (j.ok){
      if (!formEl.elements.submission_id){
        const hid = document.createElement("input");
        hid.type="hidden"; hid.name="submission_id"; hid.value=j.submission_id;
        formEl.appendChild(hid);
      }
      // showOk("Draft saved.");
      return j;
    }
    throw new Error("Save failed.");
  }catch(err){
    showWarn(err.message || "Save failed.");
    throw err;
  }finally{
    setBusy(saveBtn, false);
  }
}
saveBtn?.addEventListener("click", async (e)=>{ e.preventDefault(); await doSave(); });

/* ===== Return helpers ===== */
(function rememberReferrer(){
  const u = new URL(location.href);
  if (!u.searchParams.get("return_to") && document.referrer){
    try{
      const r = new URL(document.referrer);
      if (r.origin === location.origin && !sessionStorage.getItem("formbuilder.returnTo")){
        sessionStorage.setItem("formbuilder.returnTo", r.href);
      }
    }catch(_){}
  }
})();
function resolveReturnTo(){
  const u = new URL(location.href);
  const rt = u.searchParams.get("return_to");
  if (rt){
    try{
      const cand = new URL(rt, location.origin);
      if (cand.origin === location.origin) return cand.href;
    }catch(_){
      if (rt.startsWith("/")) return rt;
    }
  }
  const stored = sessionStorage.getItem("formbuilder.returnTo");
  if (stored) return stored;
  if (document.referrer){
    try{
      const r = new URL(document.referrer);
      if (r.origin === location.origin) return r.href;
    }catch(_){}
  }
  return safeUrl('case_detail');
}
function caseDetailUrlFor(id){
  try{
    const u = new URL(safeUrl('case_detail'), location.origin);
    const parts = u.pathname.split("/");
    const i = parts.findIndex(p => p === "cases");
    if (i >= 0 && parts[i+1]){
      parts[i+1] = String(id);
      u.pathname = parts.join("/");
      return u.href;
    }
  }catch(_){}
  return `/lupon_mem/cases/${id}/`;
}
function showRedirectOverlay(){
  const overlay = document.getElementById('redirectOverlay');
  if (overlay) overlay.style.display = 'flex';
}
function gotoAfterSubmit(j){
  showRedirectOverlay();
  setTimeout(() => {
    if (j && j.redirect){ location.href = j.redirect; return; }
    const c = formEl.elements.case_id && parseInt(formEl.elements.case_id.value, 10);
    if (c && Number.isFinite(c)){ location.href = caseDetailUrlFor(c); return; }
    location.href = resolveReturnTo();
  }, 500);
}

/* ===== Confirm flow ===== */
const cmEl = document.getElementById("confirmSubmitModal");
const confirmModal = cmEl ? new bootstrap.Modal(cmEl) : null;
const confirmBtn   = document.getElementById("confirmSubmitBtn");

document.getElementById("submitBtn")?.addEventListener("click", (e)=>{
  e.preventDefault();
  confirmModal?.show();
});

/* ===== KP-17 UI logic (auto-fill Requested By + person_id) ===== */
(function InitKP17(){
  if (!isKP17()) return;
  const box = document.getElementById("kp17RepudiationCapture");
  if (!box) return;

  box.style.removeProperty('display');
  box.classList.remove('kp-offscreen');
  box.style.display = 'block';
  
  // For minimal UI, ensure it's always visible
  if (FB.flags?.kp17_ui_minimal) {
    box.style.display = 'block';
  }

  const radioC = document.getElementById("repC");
  const radioR = document.getElementById("repR");
  const select = document.getElementById("repudiating_person_id");

  const COMPLAINANTS = (FB.parties?.complainants || []);
  const RESPONDENTS  = (FB.parties?.respondents  || []);

  function byCodeInput(code){
    return document.querySelector(
      `[data-code="${code}"] input, [data-code="${code}"] textarea, [data-code="${code}"] select,` +
      ` input[data-code="${code}"], textarea[data-code="${code}"], select[data-code="${code}"]`
    );
  }
  function findByLabelFuzzy(substr){
    const labels = Array.from(document.querySelectorAll('label.form-label'));
    const hit = labels.find(l => (l.textContent || '').toLowerCase().includes(substr));
    const wrap = hit?.closest('.kp-field');
    return wrap?.querySelector('input,textarea,select') ||
           hit?.parentElement?.querySelector?.('input,textarea,select') || null;
  }

  const requestedByEl =
      byCodeInput("requested_by")
   || byCodeInput("requested_by_who_filed")
   || byCodeInput("who_filed")
   || byCodeInput("requested_by_name")
   || findByLabelFuzzy('requested by')
   || findByLabelFuzzy('who filed');

  let requestedByIdEl = document.getElementById("requested_by_person_id");
  if (!requestedByIdEl){
    requestedByIdEl = document.createElement("input");
    requestedByIdEl.type = "hidden";
    requestedByIdEl.id = "requested_by_person_id";
    requestedByIdEl.name = "requested_by_person_id";
    document.getElementById("formFields")?.appendChild(requestedByIdEl);
  }

  function write(el, val){
    if (!el) return;
    el.value = val ?? "";
    el.dispatchEvent(new Event("input", { bubbles:true }));
    el.dispatchEvent(new Event("change", { bubbles:true }));
  }

  function fillOptions(list){
    select.innerHTML = "";
    list.forEach(p=>{
      const opt = document.createElement("option");
      opt.value = String(p.person_id ?? p.id ?? "");
      opt.textContent = String(p.name ?? "").trim();
      select.appendChild(opt);
    });
    if (!select.options.length){
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "— no people available —";
      select.appendChild(opt);
    }
  }

  function syncRequestedBy(){
    const opt = select.options[select.selectedIndex];
    const name = (opt?.textContent || "").trim();
    const pid  = parseInt(select.value || "", 10);
    if (requestedByEl) write(requestedByEl, name);
    if (requestedByIdEl) requestedByIdEl.value = Number.isFinite(pid) ? String(pid) : "";
  }

  function onPartyChange(){
    if (radioC.checked) fillOptions(COMPLAINANTS);
    else if (radioR.checked) fillOptions(RESPONDENTS);
    if (select.options.length) select.selectedIndex = 0;
    syncRequestedBy();
  }

  radioC.addEventListener("change", onPartyChange);
  radioR.addEventListener("change", onPartyChange);
  select.addEventListener("change", syncRequestedBy);

  document.getElementById("repC")?.setAttribute("required","required");
  document.getElementById("repR")?.setAttribute("required","required");

  if (COMPLAINANTS.length){
    radioC.checked = true;
    fillOptions(COMPLAINANTS);
  } else {
    radioR.checked = true;
    fillOptions(RESPONDENTS);
  }
  if (select.options.length) select.selectedIndex = 0;
  syncRequestedBy();
})();

/* ===== KP-23 UI logic (capture who filed) ===== */
(function InitKP23(){
  if (!isKP23()) return;
  const box = document.getElementById("kp23FilerCapture");
  if (!box) return;

  box.style.removeProperty('display');
  box.classList.remove('kp-offscreen');
  box.style.display = 'block';

  const radioC = document.getElementById("kp23C");
  const radioR = document.getElementById("kp23R");
  const select = document.getElementById("kp23_filed_by_person_id");

  const COMPLAINANTS = (FB.parties?.complainants || []);
  const RESPONDENTS  = (FB.parties?.respondents  || []);

  function byCodeInput(code){
    return document.querySelector(
      `[data-code="${code}"] input, [data-code="${code}"] textarea, [data-code="${code}"] select,` +
      ` input[data-code="${code}"], textarea[data-code="${code}"], select[data-code="${code}"]`
    );
  }
  function findByLabelFuzzy(substr){
    const labels = Array.from(document.querySelectorAll('label.form-label'));
    const hit = labels.find(l => (l.textContent || '').toLowerCase().includes(substr));
    const wrap = hit?.closest('.kp-field');
    return wrap?.querySelector('input,textarea,select') ||
           hit?.parentElement?.querySelector?.('input,textarea,select') || null;
  }

  const filedByDisplayEl =
      byCodeInput("kp23_filed_by")
   || byCodeInput("filed_by")
   || byCodeInput("requested_by")
   || findByLabelFuzzy('filed by')
   || findByLabelFuzzy('requested by');

  let hiddenPid = document.getElementById("kp23_filed_by_person_hidden");
  if (!hiddenPid){
    hiddenPid = document.createElement("input");
    hiddenPid.type = "hidden";
    hiddenPid.id = "kp23_filed_by_person_hidden";
    hiddenPid.name = "kp23_filed_by_person_hidden";
    document.getElementById("formFields")?.appendChild(hiddenPid);
  }

  function write(el, val){
    if (!el) return;
    el.value = val ?? "";
    el.dispatchEvent(new Event("input", { bubbles:true }));
    el.dispatchEvent(new Event("change", { bubbles:true }));
  }

  function fillOptions(list){
    select.innerHTML = "";
    list.forEach(p=>{
      const opt = document.createElement("option");
      opt.value = String(p.person_id ?? p.id ?? "");
      opt.textContent = String(p.name ?? "").trim();
      select.appendChild(opt);
    });
    if (!select.options.length){
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "— no people available —";
      select.appendChild(opt);
    }
  }

  function syncFiledBy(){
    const opt = select.options[select.selectedIndex];
    const name = (opt?.textContent || "").trim();
    const pid  = parseInt(select.value || "", 10);
    if (filedByDisplayEl) write(filedByDisplayEl, name);
    hiddenPid.value = Number.isFinite(pid) ? String(pid) : "";
  }

  function onPartyChange(){
    if (radioC.checked) fillOptions(COMPLAINANTS);
    else if (radioR.checked) fillOptions(RESPONDENTS);
    if (select.options.length) select.selectedIndex = 0;
    syncFiledBy();
  }

  radioC.addEventListener("change", onPartyChange);
  radioR.addEventListener("change", onPartyChange);
  select.addEventListener("change", syncFiledBy);

  radioC?.setAttribute("required","required");
  radioR?.setAttribute("required","required");

  if (COMPLAINANTS.length){
    radioC.checked = true;
    fillOptions(COMPLAINANTS);
  } else {
    radioR.checked = true;
    fillOptions(RESPONDENTS);
  }
  if (select.options.length) select.selectedIndex = 0;
  syncFiledBy();
})();

/* ===== Perform submit ===== */
let _submitting = false;
async function performSubmit(){
  if (_submitting) return;
  _submitting = true;
  try{
    setBusy(submitBtn, true);
    setBusyEl(confirmBtn, true);

    if (!formEl.elements.submission_id){
      if (!checkVisibleValidity(formEl)){
        showWarn("Please complete required fields.");
        return;
      }
      await doSave();
    } else if (!checkVisibleValidity(formEl)){
      showWarn("Please complete required fields.");
      return;
    }

    const payload = {
      submission_id: parseInt(formEl.elements.submission_id.value),
      case_id: parseInt(formEl.elements.case_id.value)
    };

    if (isKP17()){
      const party = (document.getElementById("repC")?.checked ? "COMPLAINANT"
                   : document.getElementById("repR")?.checked ? "RESPONDENT" : "");
      const personIdRaw = document.getElementById("repudiating_person_id")?.value || "";
      const personId = personIdRaw ? parseInt(personIdRaw, 10) : NaN;

      if (!party){ showWarn("For KP-17, please choose who is repudiating."); return; }
      if (!Number.isFinite(personId)){ showWarn("For KP-17, please select the repudiating person."); return; }

      payload.repudiating_party = party;
      payload.repudiating_person_id = personId;

      const rbPid = document.getElementById("requested_by_person_id")?.value;
      if (rbPid) payload.requested_by_person_id = parseInt(rbPid, 10);
    }

    if (isKP23()){
      const party = (document.getElementById("kp23C")?.checked ? "COMPLAINANT"
                   : document.getElementById("kp23R")?.checked ? "RESPONDENT" : "");
      const personIdRaw = document.getElementById("kp23_filed_by_person_id")?.value || "";
      const personId = personIdRaw ? parseInt(personIdRaw, 10) : NaN;

      if (!party){ showWarn("For KP-23, please choose who filed."); return; }
      if (!Number.isFinite(personId)){ showWarn("For KP-23, please select the filer."); return; }

      payload.filed_by_party = party;
      payload.filed_by_person_id = personId;
    }

    const res = await fetch(safeUrl('submit_form'), {
      method: "POST",
      headers: { "Content-Type":"application/json", "X-CSRFToken": CSRF },
      body: JSON.stringify(payload)
    });
    if (!res.ok){
      let msg = "Submit failed.";
      try{ const t = await res.text(); const j = JSON.parse(t); if(j && j.error) msg = j.error; }catch(_){}
      throw new Error(msg + " (HTTP " + res.status + ")");
    }

    const j = await res.json();
    if (j.ok){
      try { window.open(j.download_url, "_blank"); }
      catch(_) { location.href = j.download_url; return; }
      setTimeout(()=>{ gotoAfterSubmit(j); }, 400);
    } else {
      showWarn(j.error || "Submit failed.");
    }
  }catch(err){
    showWarn(err.message || "Submit failed.");
  }finally{
    setBusy(submitBtn, false);
    setBusyEl(confirmBtn, false);
    confirmModal?.hide();
    _submitting = false;
  }
}
confirmBtn?.addEventListener("click", (e)=>{ e.preventDefault(); performSubmit(); });

/* ===== KP-10 derivations (unchanged) ===== */
(function kp10Derivations(){
  const dateEl = document.querySelector(
    '[data-code="appearance_date"] input, [data-code="appearance_date"] textarea, [data-code="appearance_date"] select, input[data-code="appearance_date"], textarea[data-code="appearance_date"]'
  );
  if (!dateEl) return;

  function byCode(code){
    return document.querySelector(
      `[data-code="${code}"] input, [data-code="${code}"] textarea, [data-code="${code}"] select, input[data-code="${code}"], textarea[data-code="${code}"], select[data-code="${code}"]`
    );
  }

  const dayTargets   = ["day_of","appearance_day"].map(byCode);
  const yearEls      = ["current_year","current_year_2","current_year_3"].map(byCode);
  const todayEl      = byCode("date_today");
  const notifEl      = byCode("date_notified");
  const nDayEl       = byCode("notified_day_of");
  const monthTargets = ["appearance_month","current_month","month_today","notified_month"].map(byCode);

  const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  const iso = d => d.toISOString().slice(0,10);

  function deriveFromAppearance(){
    const v = (dateEl.value || "").trim();
    if (!v) return;
    const parts = v.split("-").map(Number);
    if (parts.length === 3 && parts.every(Number.isFinite)){
      const [Y, M, D] = parts;
      dayTargets.forEach(el => { if (el && !el.value) el.value = String(D); });
      monthTargets.forEach(el => { if (el && !el.value) el.value = MONTHS[M-1]; });
      yearEls.forEach(el => { if (el && !el.value) el.value = String(Y); });
    }
  }

  function fillTodayDefaults(){
    const now = new Date();
    if (todayEl && !todayEl.value) todayEl.value = iso(now);
    if (notifEl && !notifEl.value) notifEl.value = iso(now);
    if (nDayEl  && !nDayEl.value)  nDayEl  .value = String(now.getDate());
    yearEls.forEach(el => { if (el && !el.value) el.value = String(now.getFullYear()); });
    monthTargets.forEach(el => { if (el && !el.value) el.value = MONTHS[now.getMonth()]; });
  }

  fillTodayDefaults();
  deriveFromAppearance();
  dateEl.addEventListener("change", deriveFromAppearance);

  if (FB.flags?.kp10_ui_minimal){
    const wrapDate = document.querySelector('[data-code="appearance_date"]');
    if (wrapDate){
      let lbl = wrapDate.querySelector("label.form-label");
      if (!lbl){
        const prev = wrapDate.previousElementSibling;
        if (prev?.matches('label.form-label')) lbl = prev;
      }
      if (lbl){ lbl.textContent = "Hearing Details"; lbl.classList.add("label-req"); }
    }
  }
})();

/* ===== Utility: close typeahead on ESC ===== */
function bindCloseOnEscape(input, closeFn){
  if (!input || !closeFn) return;
  input.addEventListener('keydown', e=>{
    if (e.key === 'Escape'){ closeFn(); input.blur(); }
  });
}

/* ===== Typeaheads for KP-10, 11, 13, 15 (unchanged) ===== */
(function enhanceKP10(){
  if (!FB.flags?.kp10_ui_minimal) return;
  const wrap = document.querySelector('[data-code="addr_to"]');
  const addr = document.querySelector('[data-code="addr_to"] input, [data-code="addr_to"] textarea, input[data-code="addr_to"], textarea[data-code="addr_to"]');
  if(!wrap || !addr) return;
  wrap.classList.add("typeahead-wrap");
  const dd = document.createElement("div"); dd.className = "typeahead-dropdown"; wrap.appendChild(dd);
  let timer=null, items=[];
  function openDD(){ dd.style.display="block"; }
  function closeDD(){ dd.style.display="none"; dd.innerHTML=""; items=[]; }
  function render(list){
    if(!list.length){ dd.innerHTML='<div class="typeahead-empty">No matches</div>'; openDD(); return; }
    dd.innerHTML = list.map((r,i)=>`<button type="button" class="typeahead-item" data-i="${i}">${r.name}</button>`).join("");
    openDD();
  }
  function fetchSuggest(q){
    fetch(safeUrl('staff_suggest') + "?q="+encodeURIComponent(q), {headers:{'X-Requested-With':'fetch'}})
      .then(r=>r.json()).then(j=>{ items=j.results||[]; render(items); }).catch(()=>closeDD());
  }
  function choose(i){ const row=items[i]; if(!row) return; addr.value=row.name; closeDD(); }
  addr.addEventListener("input", ()=>{
    const q=addr.value.trim(); if(q.length<2){ closeDD(); return; }
    clearTimeout(timer); timer=setTimeout(()=>fetchSuggest(q),180);
  });
  dd.addEventListener("click", e=>{
    const b=e.target.closest(".typeahead-item"); if(!b) return; choose(parseInt(b.dataset.i,10));
  });
  document.addEventListener("click", e=>{ if(!dd.contains(e.target) && e.target!==addr) closeDD(); });
  bindCloseOnEscape(addr, closeDD);
})();
(function enhanceKP11(){
  if (!FB.flags?.kp11_ui_minimal) return;
  const wrap = document.querySelector('[data-code="pangkat_member_name"]');
  const input = document.querySelector('[data-code="pangkat_member_name"] input, [data-code="pangkat_member_name"] textarea, input[data-code="pangkat_member_name"], textarea[data-code="pangkat_member_name"]');
  if(!wrap || !input) return;
  wrap.classList.add("typeahead-wrap");
  const dd = document.createElement("div"); dd.className = "typeahead-dropdown"; wrap.appendChild(dd);
  let timer=null, items=[];
  function openDD(){ dd.style.display="block"; }
  function closeDD(){ dd.style.display="none"; dd.innerHTML=""; items=[]; }
  function render(list){
    if(!list.length){ dd.innerHTML='<div class="typeahead-empty">No matches</div>'; openDD(); return; }
    dd.innerHTML = list.map((r,i)=>`<button type="button" class="typeahead-item" data-i="${i}">${r.name}</button>`).join("");
    openDD();
  }
  function fetchSuggest(q){
    fetch(safeUrl('staff_suggest') + "?q="+encodeURIComponent(q), {headers:{'X-Requested-With':'fetch'}})
      .then(r=>r.json()).then(j=>{ items=j.results||[]; render(items); }).catch(()=>closeDD());
  }
  function choose(i){ const row=items[i]; if(!row) return; input.value=row.name; closeDD(); }
  input.addEventListener("input", ()=>{
    const q=input.value.trim(); if(q.length<2){ closeDD(); return; }
    clearTimeout(timer); timer=setTimeout(()=>fetchSuggest(q),180);
  });
  dd.addEventListener("click", e=>{
    const b=e.target.closest(".typeahead-item"); if(!b) return; choose(parseInt(b.dataset.i,10));
  });
  document.addEventListener("click", e=>{ if(!dd.contains(e.target) && e.target!==input) closeDD(); });
  bindCloseOnEscape(input, closeDD);
})();

/* KP-13 */
(function(){
  function enhance(code, url){
    const wrap=document.querySelector(`[data-code="${code}"]`);
    const input=document.querySelector(`[data-code="${code}"] input, [data-code="${code}"] textarea, input[data-code="${code}"], textarea[data-code="${code}"]`);
    if(!wrap||!input) return;
    wrap.classList.add("typeahead-wrap");
    const dd=document.createElement("div"); dd.className="typeahead-dropdown"; wrap.appendChild(dd);
    let t=null, items=[];
    function open(){ dd.style.display="block"; }
    function close(){ dd.style.display="none"; dd.innerHTML=""; items=[]; }
    function render(list){
      if(!list.length){ dd.innerHTML='<div class="typeahead-empty">No matches</div>'; open(); return; }
      dd.innerHTML=list.map((r,i)=>`<button type="button" class="typeahead-item" data-i="${i}">${r.name}</button>`).join("");
      open();
    }
    function fetchQ(q){
      fetch(url + encodeURIComponent(q), {headers:{'X-Requested-With':'fetch'}})
        .then(r=>r.json()).then(j=>{items=j.results||[]; render(items);}).catch(()=>close());
    }
    function choose(i){ const row=items[i]; if(!row) return; input.value=row.name; close(); }
    input.addEventListener("input", ()=>{
      const q=input.value.trim(); if(q.length<2){ close(); return; }
      clearTimeout(t); t=setTimeout(()=>fetchQ(q),180);
    });
    dd.addEventListener("click", e=>{
      const b=e.target.closest(".typeahead-item"); if(!b) return; choose(parseInt(b.dataset.i,10));
    });
    document.addEventListener("click", e=>{ if(!dd.contains(e.target) && e.target!==input) close(); });
    bindCloseOnEscape(input, close);
  }
  enhance("subpoena_to", safeUrl('person_suggest') + "?q=");
  enhance("subpoena_witness", safeUrl('person_suggest') + "?q=");
})();

/* KP-15 */
(function(){
  function enhanceStaff(code){
    const wrap=document.querySelector(`[data-code="${code}"]`);
    const input=document.querySelector(`[data-code="${code}"] input, [data-code="${code}"] textarea, input[data-code="${code}"], textarea[data-code="${code}"]`);
    if(!wrap||!input) return;
    wrap.classList.add("typeahead-wrap");
    const dd=document.createElement("div"); dd.className="typeahead-dropdown"; wrap.appendChild(dd);
    let t=null, items=[];
    function open(){ dd.style.display="block"; }
    function close(){ dd.style.display="none"; dd.innerHTML=""; items=[]; }
    function render(list){
      if(!list.length){ dd.innerHTML='<div class="typeahead-empty">No matches</div>'; open(); return; }
      dd.innerHTML=list.map((r,i)=>`<button type="button" class="typeahead-item" data-i="${i}">${r.name}</button>`).join("");
      open();
    }
    function fetchQ(q){
      fetch(safeUrl('staff_suggest') + "?q="+encodeURIComponent(q), {headers:{'X-Requested-With':'fetch'}})
        .then(r=>r.json()).then(j=>{items=j.results||[]; render(items);}).catch(()=>close());
    }
    function choose(i){ const row=items[i]; if(!row) return; input.value=row.name; close(); }
    input.addEventListener("input", ()=>{
      const q=input.value.trim(); if(q.length<2){ close(); return; }
      clearTimeout(t); t=setTimeout(()=>fetchQ(q),180);
    });
    dd.addEventListener("click", e=>{
      const b=e.target.closest(".typeahead-item"); if(!b) return; choose(parseInt(b.dataset.i,10));
    });
    document.addEventListener("click", e=>{ if(!dd.contains(e.target) && e.target!==input) close(); });
    bindCloseOnEscape(input, close);
  }
  enhanceStaff("member");
  enhanceStaff("member_two");
})();

/* MED ATT: picks -> autofill (unchanged) */
(function(){
  const btnAdd   = document.getElementById("btnAddStaff");
  const btnClear = document.getElementById("btnClearStaff");
  const chipsBox = document.getElementById("attChips");
  const hidden   = document.getElementById("med_att_staff_json");

  const modalEl   = document.getElementById("staffPicker");
  const modal     = modalEl ? new bootstrap.Modal(modalEl) : null;
  const searchBox = document.getElementById("staffSearch");
  const results   = document.getElementById("staffResults");

  if(!btnAdd || !chipsBox) return;

  const STORAGE_KEY = `med_attendees_case_${FB.case_id}_form_${FB.form_id}`;
  const WORDS = ["one","two","three","four","five","six","seven","eight","nine","ten"];

  function byCode(code){
    return document.querySelector(
      `[data-code="${code}"] input, [data-code="${code}"] textarea, [data-code="${code}"] select, input[data-code="${code}"], textarea[data-code="${code}"], select[data-code="${code}"]`
    );
  }
  function findAttendeeSlot(i){
    const w = WORDS[i];
    return byCode(`person_${w}`) || byCode(`attendee_${i+1}`) || byCode(`attendee_${w}`);
  }
  function findPositionSlot(i){
    const w = WORDS[i];
    if (i === 0) return byCode("position_one") || byCode("pos_one") || byCode("position_1");
    return byCode(`pos_${w}`) || byCode(`position_${w}`) || byCode(`position_${i+1}`);
  }
  function findContactSlot(i){
    const w = WORDS[i];
    return byCode(`contact_${w}`) || byCode(`mobile_${w}`) || byCode(`contact_${i+1}`) || byCode(i===0?"contact":"");
  }
  function write(el, val){
    if (!el) return;
    el.value = val ?? "";
    el.dispatchEvent(new Event("input", { bubbles:true }));
    el.dispatchEvent(new Event("change", { bubbles:true }));
  }
  function escapeHtml(s){ return (s||"").replace(/[&<>"']/g, m => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[m])); }

  let picks = [];
  try { picks = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "[]"); } catch(_){}
  renderChips(); pushToForm();

  function persist(){ try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(picks)); } catch(_){} }

  function renderChips(){
    chipsBox.innerHTML = "";
    picks.forEach((p,i)=>{
      const span = document.createElement("span");
      span.className = "att-chip";
      span.innerHTML = `<i class="bi bi-person"></i><span>${escapeHtml(p.name)}</span>
                        <button class="x" title="Remove" data-i="${i}">&times;</button>`;
      span.querySelector(".x").onclick = ev => {
        picks.splice(+ev.currentTarget.dataset.i,1);
        persist(); renderChips(); pushToForm();
      };
      chipsBox.appendChild(span);
    });
    if (hidden) hidden.value = JSON.stringify(picks);
  }

  function clearAllSlots(){
    for(let i=0;i<10;i++){
      write(findAttendeeSlot(i), "");
      write(findPositionSlot(i), "");
      write(findContactSlot(i), "");
    }
  }
  function pushToForm(){
    clearAllSlots();
    picks.forEach((p,i)=>{
      write(findAttendeeSlot(i), p.name || "");
      write(findPositionSlot(i), (p.role || p.position || "") );
      write(findContactSlot(i),  (p.mobile || p.phone || p.contact || "") );
    });
  }

  btnAdd.addEventListener("click", ()=>{
    if(!modal) return;
    results.innerHTML = "";
    searchBox.value = "";
    modal.show();
    setTimeout(()=>searchBox.focus(), 80);
  });
  if (btnClear) btnClear.addEventListener("click", ()=>{ picks=[]; persist(); renderChips(); pushToForm(); });

  let t=null;
  if (searchBox){
    searchBox.addEventListener("input", ()=>{
      const q = searchBox.value.trim();
      if (t) clearTimeout(t);
      if (q.length < 2){ results.innerHTML=""; return; }
      t = setTimeout(async ()=>{
        results.innerHTML = '<div class="list-group-item text-muted">Searching…</div>';
        try{
          const r = await fetch(safeUrl('staff_suggest_all') + "?q=" + encodeURIComponent(q), {headers:{'X-Requested-With':'fetch'}});
          const j = await r.json();
          const rows = j.results || [];
          results.innerHTML = rows.length ? rows.map(x=>{
            const sid = x.id ?? x.staff_id ?? x.person_id ?? "";
            const payload = btoa(unescape(encodeURIComponent(JSON.stringify(x))));
            return `<button type="button" class="list-group-item list-group-item-action" data-sid="${String(sid)}" data-json="${payload}">${escapeHtml(x.name || "")}</button>`;
          }).join("") : '<div class="list-group-item text-muted">No matches</div>';
        }catch(_){
          results.innerHTML = '<div class="list-group-item text-danger">Search failed</div>';
        }
      }, 200);
    });
  }

  results?.addEventListener("click", async (e)=>{
    const btn = e.target.closest("button.list-group-item"); if (!btn) return;
    let base = {};
    try { base = JSON.parse(decodeURIComponent(escape(atob(btn.getAttribute("data-json") || "e30=")))); } catch(_){}
    const sid = btn.getAttribute("data-sid") || base.id || base.staff_id || "";

    const row = {
      staff_id: sid,
      person_id: base.person_id || null,
      name: (base.name || "").trim(),
      role: (base.role || base.position || "").trim(),
      mobile: (base.mobile || base.phone || base.contact || "").trim()
    };

    if ((!row.role || !row.mobile) && sid){
      try{
        const lr = await fetch(`/lupon_mem/staff/lookup?staff_id=${encodeURIComponent(sid)}`);
        if (lr.ok){
          const lj = await lr.json();
          if (lj.ok && lj.result){
            row.name   = (lj.result.name   ?? row.name  ).trim();
            row.role   = (lj.result.role   ?? row.role  ).trim();
            row.mobile = (lj.result.mobile ?? row.mobile).trim();
            row.person_id = lj.result.person_id ?? row.person_id;
          }
        }
      }catch(_){}
    }

    if (picks.some(p => (p.staff_id||"") === (row.staff_id||"") && p.name === row.name)){
      if (modal) modal.hide();
      return;
    }
    picks.push(row);
    persist(); renderChips(); pushToForm();
    if (modal) modal.hide();
  });
})();

/* ===== KP-9: All fields filled, ready to submit ===== */
(function initKP9(){
  if (!isKP9()) return;
  
  // Hide all form fields since everything is pre-filled
  const allFields = document.querySelectorAll('.kp-field');
  allFields.forEach(field => {
    field.classList.add('kp-offscreen');
  });
  
  // Show a message that everything is ready
  const cardBody = document.querySelector('.card-body');
  if (cardBody) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'mb-3 p-3 rounded-3';
    messageDiv.style.background = '#680404ff';
    messageDiv.style.color = '#fff';
    messageDiv.innerHTML = `
      <div class="d-flex align-items-center gap-2">
        <i class="bi bi-check-circle" style="font-size:1.1rem;"></i>
        <strong>All fields are already filled out</strong>
      </div>
      <div class="mt-1" style="opacity:.95">
        For <strong>KP Form No. 9</strong>, all required information has been automatically populated. 
        Click <strong>Submit &amp; Generate PDF</strong> to generate the summons for the respondent.
      </div>
    `;
    
    // Insert after any existing helper banners
    const existingBanners = cardBody.querySelectorAll('.mb-3.p-3.rounded-3');
    if (existingBanners.length > 0) {
      existingBanners[existingBanners.length - 1].after(messageDiv);
    } else {
      cardBody.insertBefore(messageDiv, cardBody.firstChild);
    }
  }
})();

/* ===== KP-9-P2: respondents-only binding + narrative/visibility ===== */
/* ===== KP-9-P2: respondents-only binding + narrative/visibility + single-line fill ===== */
(function enhanceKP9P2(){
  if (!isKP9P2()) return;

  const RESPONDENTS = Array.isArray(FB.parties?.respondents) ? FB.parties.respondents : [];

  function byCode(code){
    return document.querySelector(
      `[data-code="${code}"] input, [data-code="${code}"] textarea, [data-code="${code}"] select,` +
      ` input[data-code="${code}"], textarea[data-code="${code}"], select[data-code="${code}"]`
    );
  }
  function wrapFor(code){ return document.querySelector(`[data-code="${code}"]`); }
  function write(el, val){
    if (!el) return;
    if (el.type === 'checkbox') el.checked = !!val;
    else el.value = val ?? "";
    el.dispatchEvent(new Event("input", { bubbles:true }));
    el.dispatchEvent(new Event("change", { bubbles:true }));
  }
  function setIfEmpty(code, val){
    const el = byCode(code);
    if (el && !String(el.value || "").trim()) write(el, val);
  }
  function showWrap(codeOrEl, show){
    const node = typeof codeOrEl === "string" ? wrapFor(codeOrEl) : codeOrEl;
    if (!node) return;
    node.style.display = show ? "" : "none";
  }

  /* ---------- Respondents-only typeahead (local) ---------- */
  function bindRespondentTA(code){
    const wrap = wrapFor(code);
    const input = byCode(code);
    if (!wrap || !input) return;

    wrap.classList.add("typeahead-wrap");
    const dd = document.createElement("div");
    dd.className = "typeahead-dropdown";
    wrap.appendChild(dd);

    let items = [];
    function open(){ dd.style.display = "block"; }
    function close(){ dd.style.display = "none"; dd.innerHTML = ""; items=[]; }
    function render(list){
      if (!list.length){ dd.innerHTML = '<div class="typeahead-empty">No matches</div>'; open(); return; }
      dd.innerHTML = list.map((r,i)=>`<button type="button" class="typeahead-item" data-i="${i}">${r.name}</button>`).join("");
      open();
    }
    function filter(q){
      q = q.toLowerCase();
      return RESPONDENTS.filter(r => (r.name || "").toLowerCase().includes(q));
    }
    function choose(i){
      const r = items[i]; if (!r) return;
      input.value = r.name;
      close();
      input.dispatchEvent(new Event("change",{bubbles:true}));
    }

    input.addEventListener("input", ()=>{
      const q = input.value.trim();
      if (q.length < 1){ close(); return; }
      items = filter(q);
      render(items);
    });
    dd.addEventListener("click", e=>{
      const b = e.target.closest(".typeahead-item"); if (!b) return;
      choose(parseInt(b.dataset.i,10));
    });
    document.addEventListener("click", e=>{ if(!dd.contains(e.target) && e.target!==input) close(); });
    bindCloseOnEscape(input, close);
  }

  /* ---------- Remote TAs for proxies/officer ---------- */
  function bindRemoteTA(code, url){
    const wrap  = wrapFor(code);
    const input = byCode(code);
    if (!wrap || !input) return;
    wrap.classList.add("typeahead-wrap");
    const dd = document.createElement("div"); dd.className="typeahead-dropdown"; wrap.appendChild(dd);
    let t=null, items=[];
    function open(){ dd.style.display="block"; }
    function close(){ dd.style.display="none"; dd.innerHTML=""; items=[]; }
    function render(list){
      if(!list.length){ dd.innerHTML='<div class="typeahead-empty">No matches</div>'; open(); return; }
      dd.innerHTML = list.map((r,i)=>`<button type="button" class="typeahead-item" data-i="${i}">${r.name}</button>`).join("");
      open();
    }
    function fetchQ(q){
      fetch(url + encodeURIComponent(q), {headers:{'X-Requested-With':'fetch'}})
        .then(r=>r.json()).then(j=>{items=j.results||[]; render(items);}).catch(()=>close());
    }
    function choose(i){ const row=items[i]; if(!row) return; input.value=row.name; close(); input.dispatchEvent(new Event("change",{bubbles:true})); }
    input.addEventListener("input", ()=>{
      const q=input.value.trim(); if(q.length<2){ close(); return; }
      clearTimeout(t); t=setTimeout(()=>fetchQ(q),180);
    });
    dd.addEventListener("click", e=>{
      const b=e.target.closest(".typeahead-item"); if(!b) return; choose(parseInt(b.dataset.i,10));
    });
    document.addEventListener("click", e=>{ if(!dd.contains(e.target) && e.target!==input) close(); });
    bindCloseOnEscape(input, close);
  }

  /* Bind TAs */
  ["served_to","served_to_2","served_to_3","served_to_4",
   "respondent_name_line1","respondent_name_line2","respondent_name_line3",
   "respondent_name","respondents"].forEach(bindRespondentTA);

  bindRemoteTA("proxy_name_one", safeUrl('person_suggest') + "?q=");
  bindRemoteTA("proxy_name_two", safeUrl('person_suggest') + "?q=");
  ["offcr_name","officer_name","process_server"].forEach(code=>{
    bindRemoteTA(code, safeUrl('staff_suggest') + "?q=");
  });

  /* ---------- Prefill from respondents ---------- */
  if (RESPONDENTS.length){
    setIfEmpty("served_to", RESPONDENTS[0].name || "");
    setIfEmpty("respondent_name_line1", RESPONDENTS[0]?.name || "");
    setIfEmpty("respondent_name_line2", RESPONDENTS[1]?.name || "");
    setIfEmpty("respondent_name_line3", RESPONDENTS[2]?.name || "");
    setIfEmpty("received_sig_line1",   RESPONDENTS[0]?.name || "");
    setIfEmpty("received_sig_line2",   RESPONDENTS[1]?.name || "");
  }

  /* ---------- Mode of Service: visibility + narrative + SINGLE-LINE FILL ---------- */
  const narrativeEl = byCode("respondent_offcr_ret") || byCode("officer_return_narrative") || byCode("narrative");
  const modeNumEl   = byCode("service_mode") || byCode("mode") || byCode("mode_of_service") || byCode("service_mode_no");
  const servedToEl  = byCode("served_to");

  // Map: which field should carry the name per mode; others must be blank.
  const MODE_TO_FIELD = {
    "1": "respondent_names_one",
    "2": "respondent_names_two",
    "3": "respondent_names_three",
    "4": "served_to_2"
  };
  const CLEAR_FIELDS = ["respondent_names_one","respondent_names_two","respondent_names_three","served_to_2"];

  function putOnlyInSelectedLine(mode, name){
    // Clear everyone first
    CLEAR_FIELDS.forEach(code => write(byCode(code), ""));
    // Then write to the single mapped field
    const targetCode = MODE_TO_FIELD[String(mode)] || "";
    if (targetCode) write(byCode(targetCode), name || "");
  }

  function composeNarr(mode){
    const servedTo   = (servedToEl?.value || "").trim();
    const proxyDw    = byCode("proxy_name_one")?.value?.trim();
    const proxyOff   = byCode("proxy_name_two")?.value?.trim();
    switch(String(mode)){
      case "1": return "";
      case "2": return "";
      case "3": return proxyDw || "";
      case "4": return proxyOff || "";
      default: return "";
    }
  }

  const rads = Array.from(document.querySelectorAll('input[name="kp9p2_mode"]'));

  function onMode(){
    const sel = rads.find(r=>r.checked)?.value || "";
    if (modeNumEl) write(modeNumEl, sel);

    // Toggle visible proxy input
    showWrap("proxy_name_one", sel==="3");
    showWrap("proxy_name_two", sel==="4");

    // Narrative text
    if (narrativeEl) write(narrativeEl, composeNarr(sel));

    // SINGLE-LINE filling logic
    const name = (servedToEl?.value || "").trim();
    putOnlyInSelectedLine(sel, name);
    
    // ALWAYS sync served_to_3 with served_to (respondent name) for ALL modes
    const servedTo3El = byCode("served_to_3");
    if (servedTo3El) write(servedTo3El, name);
    
    // Mode 3 or 4: sync proxy name to served_to_4
    const servedTo4El = byCode("served_to_4");
    if (sel === "3") {
      const proxy1 = byCode("proxy_name_one")?.value?.trim() || "";
      if (servedTo4El) write(servedTo4El, proxy1);
    } else if (sel === "4") {
      const proxy2 = byCode("proxy_name_two")?.value?.trim() || "";
      if (servedTo4El) write(servedTo4El, proxy2);
    } else {
      if (servedTo4El) write(servedTo4El, "");
    }
    
    // Always sync date_signed_two with date_signed_one
    const dateSigned1El = byCode("date_signed_one");
    const dateSigned2El = byCode("date_signed_two");
    if (dateSigned1El && dateSigned2El) {
      write(dateSigned2El, dateSigned1El.value);
    }
  }

  // Re-run when any dependent field changes
  ["served_to","proxy_name_one","proxy_name_two","date_signed_one"].forEach(code=>{
    const el = byCode(code); if (!el) return;
    el.addEventListener("input", onMode);
    el.addEventListener("change", onMode);
  });
  
  // Also sync served_to_3 whenever served_to changes
  if (servedToEl) {
    servedToEl.addEventListener("input", ()=>{
      const servedTo3El = byCode("served_to_3");
      if (servedTo3El) write(servedTo3El, servedToEl.value.trim());
    });
  }
  rads.forEach(r=>r.addEventListener("change", onMode));

  // Initial compute
  onMode();
})();

/* ===== KP-15: Show up to award_description, make others readonly ===== */
(function initKP15(){
  if (!FB.flags?.kp15_ui_minimal) return;
  
  // Make all fields readonly except award_description
  const allFields = document.querySelectorAll('.kp-field [data-field-id]');
  allFields.forEach(field => {
    const code = (field.dataset.code || '').toLowerCase();
    if (code !== 'award_description') {
      field.readOnly = true;
      field.style.backgroundColor = '#f8f9fa';
      if (field.type === 'checkbox') {
        field.disabled = true;
      }
    }
  });
})();

