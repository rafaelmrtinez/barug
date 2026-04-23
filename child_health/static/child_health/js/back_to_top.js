document.addEventListener('DOMContentLoaded', function(){
    const btn = document.getElementById('child-back-to-top');
    if(!btn) return;
    function onScroll(){ if(window.scrollY > 200) btn.classList.add('visible'); else btn.classList.remove('visible'); }
    window.addEventListener('scroll', onScroll, {passive:true});
    btn.addEventListener('click', function(){ window.scrollTo({top:0, behavior:'smooth'}); });
    onScroll();
});
