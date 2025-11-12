(function(){
  'use strict';

  function onShowHandler(event){
    try{
      const trigger = event && event.relatedTarget;
      if (!trigger) return;
      const mhrId = trigger.getAttribute('data-mhr-id') || '';
      const target = event.target && event.target.id;
      if (target === 'postpartumFollowupMidwifeModal'){
        const el = document.getElementById('midwife_maternal_record_id');
        if (el) el.value = mhrId;
      } else if (target === 'postpartumVisitBHWModal'){
        const el2 = document.getElementById('bhw_maternal_record_id');
        if (el2) el2.value = mhrId;
      }
    }catch (_e){ /* ignore */ }
  }

  function init(){
    if (typeof document === 'undefined') return;
    const mf = document.getElementById('postpartumFollowupMidwifeModal');
    const bf = document.getElementById('postpartumVisitBHWModal');
    if (mf) mf.addEventListener('show.bs.modal', onShowHandler);
    if (bf) bf.addEventListener('show.bs.modal', onShowHandler);
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
