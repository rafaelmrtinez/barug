document.addEventListener('DOMContentLoaded', function(){
  const toggle = document.getElementById('child-sidebar-toggle');
  const sidebar = document.querySelector('.child-sidebar');
  const backdrop = document.createElement('div');
  backdrop.className = 'child-sidebar-backdrop';
  document.body.appendChild(backdrop);

  function openSidebar(){
    if(!sidebar) return;
    sidebar.classList.add('open');
    backdrop.classList.add('open');
    document.body.style.overflow = 'hidden';
    if(toggle){ toggle.classList.add('open'); const ic = toggle.querySelector('.sidebar-toggle-icon'); if(ic) ic.classList.add('open'); }
  }
  function closeSidebar(){
    if(!sidebar) return;
    sidebar.classList.remove('open');
    backdrop.classList.remove('open');
    document.body.style.overflow = '';
    if(toggle){ toggle.classList.remove('open'); const ic = toggle.querySelector('.sidebar-toggle-icon'); if(ic) ic.classList.remove('open'); }
  }

  if(toggle && sidebar){
    toggle.addEventListener('click', function(e){
      e.preventDefault();
      if(sidebar.classList.contains('open')) closeSidebar(); else openSidebar();
    });
  }

  backdrop.addEventListener('click', function(){ closeSidebar(); });

  // Smooth scroll for sidebar anchor links; close on mobile after click
  const links = document.querySelectorAll('.child-sidebar .nav-link');
  links.forEach(function(a){
    a.addEventListener('click', function(e){
      if(this.getAttribute('href') && this.getAttribute('href').startsWith('#')){
        e.preventDefault();
        const targetId = this.getAttribute('href').substring(1);
        const targetEl = document.getElementById(targetId);
        if(targetEl){ targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
        if(globalThis.innerWidth < 768){ closeSidebar(); }
      }
    });
  });

  globalThis.addEventListener('resize', function(){
    if(globalThis.innerWidth >= 768){ closeSidebar(); }
  });
});
