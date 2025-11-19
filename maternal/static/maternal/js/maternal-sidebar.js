document.addEventListener('DOMContentLoaded', function(){
  var toggle = document.getElementById('sidebar-toggle');
  var sidebar = document.querySelector('.maternal-sidebar');
  var backdrop = document.createElement('div');
  backdrop.className = 'maternal-sidebar-backdrop';
  document.body.appendChild(backdrop);

  function openSidebar(){
    sidebar.classList.add('open');
    backdrop.classList.add('open');
    document.body.style.overflow = 'hidden';
    if(toggle){ toggle.classList.add('open'); const ic = toggle.querySelector('.sidebar-toggle-icon'); if(ic) ic.classList.add('open'); }
  }
  function closeSidebar(){
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
  const links = document.querySelectorAll('.maternal-sidebar .nav-link');
  links.forEach(function(a){
    a.addEventListener('click', function(e){
      // allow normal behavior for external links
      if(this.getAttribute('href') && this.getAttribute('href').startsWith('#')){
        e.preventDefault();
        const targetId = this.getAttribute('href').substring(1);
        const targetEl = document.getElementById(targetId);
        if(targetEl){
          targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        // close the sidebar if on small screens
        if(globalThis.innerWidth < 768){ closeSidebar(); }
      }
    });
  });

  // Close sidebar on resize > mobile
  globalThis.addEventListener('resize', function(){
    if(globalThis.innerWidth >= 768){
      sidebar.classList.remove('open');
      backdrop.classList.remove('open');
      document.body.style.overflow = '';
    }
  });
});
