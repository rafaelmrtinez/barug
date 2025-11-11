/* dashboard-charts.js
   Reusable chart utilities for the barangay dashboards.
   Drop into your static files (e.g. static/js/dashboard-charts.js).
   Exposes global `ChartUtils` object.
*/
(function(global){
  const ChartUtils = {};

  function cssVar(name, fallback){
    const v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (v||'').trim() || fallback;
  }

  const DEFAULTS = {
    BRAND700: cssVar('--brand-700', '#6d2932'),
    BRAND500: cssVar('--brand-500', '#561c24'),
    BRAND300: cssVar('--brand-300', '#e8d8c4'),
    NEU300: cssVar('--neutral-300', '#d1d5db'),
    NEU500: cssVar('--neutral-500', '#6b7280'),
    BORDER: cssVar('--border', '#ece7e1'),
    SHADOW: cssVar('--shadow', '0 8px 24px rgba(15,23,42,.06)')
  };

  function formatNumber(value, opts = {}){
    if (opts.formatter && typeof opts.formatter.format === 'function'){
        return opts.formatter.format(value);
    }
    const locale = opts.locale || 'en-PH';
    const maxFrac = Number.isFinite(opts.maximumFractionDigits) ? opts.maximumFractionDigits : 0;
    try{
        return new Intl.NumberFormat(locale, { maximumFractionDigits: maxFrac }).format(Number(value) || 0);
    } catch(e){
        const v = Math.round((Number(value)||0)*(10**maxFrac))/(10**maxFrac);
        return v.toString().replace(/\B(?=(\d{3})+(?!\d))/g,",");
    }
  }

  function niceNum(range, round){
    const exp = Math.floor(Math.log10(range||1));
    const f = range / Math.pow(10, exp);
    let nf;
    if (round){
      if(f<1.5) nf=1; else if(f<3) nf=2; else if(f<7) nf=5; else nf=10;
    } else {
      if(f<=1) nf=1; else if(f<=2) nf=2; else if(f<=5) nf=5; else nf=10;
    }
    return nf * Math.pow(10, exp);
  }

  function niceScale(min,max,tickCount=5){
    min = Number(min||0); max = Number(max||1);
    let range = niceNum(max-min,false);
    const step = niceNum(range/(tickCount-1),true);
    const niceMin = Math.floor(min/step)*step;
    const niceMax = Math.ceil(max/step)*step;
    const ticks=[];
    for(let v=niceMin;v<=niceMax+1e-9;v+=step) ticks.push(Math.round(v*100)/100);
    return {niceMin,niceMax,step,ticks};
  }

  function drawNoData(ctx,W,H,NEU500,title='No data',subtitle=''){
    ctx.clearRect(0,0,W,H);
    ctx.save();
    ctx.font = '600 14px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif';
    ctx.fillStyle = NEU500;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(title,W/2,H/2-(subtitle?8:0));
    if(subtitle){
      ctx.font = '12px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif';
      ctx.fillStyle = 'rgba(0,0,0,0.55)';
      ctx.fillText(subtitle,W/2,H/2+12);
    }
    ctx.restore();
  }

  function observeResize(el,fn){
    if(!el) return;
    if(!el.__chartRO) el.__chartRO = new ResizeObserver(()=>fn());
    el.__chartRO.observe(el);
  }

  // ------------------ Line chart ------------------
  ChartUtils.renderLine = function(canvasOrId, labels, series, opts = {}){
      const canvas = (typeof canvasOrId === 'string') ? document.getElementById(canvasOrId) : canvasOrId;
      if(!canvas) return;
      const BRAND700 = opts.BRAND700 || DEFAULTS.BRAND700;
      const BRAND500 = opts.BRAND500 || DEFAULTS.BRAND500;
      const BRAND300 = opts.BRAND300 || DEFAULTS.BRAND300;
      const NEU300 = opts.NEU300 || DEFAULTS.NEU300;
      const NEU500 = opts.NEU500 || DEFAULTS.NEU500;
      const tickCount = opts.tickCount || 5;
      const hitRadius = opts.hitRadius || 10; // px, how close pointer must be to a point to show tooltip

      function draw(){
        const dpr = devicePixelRatio || 1;
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        const W = canvas.clientWidth || 600, H = canvas.clientHeight || 320;
        canvas.width = W * dpr; canvas.height = H * dpr;
        const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr);

        const m = { l:48, r:18, t:18, b:32 };
        const x0 = m.l, x1 = W - m.r, y0 = H - m.b, y1 = m.t;

        const data = (Array.isArray(series) ? series.slice() : []).map(v => Number(v)||0);
        const n = Math.max(1, data.length);

        const allZero = data.every(v => v === 0 || isNaN(v));
        if (allZero){
          drawNoData(ctx, W, H, NEU500, opts.noDataTitle || 'No requests', opts.noDataSubtitle || 'No data for the selected period');
          return { ctx, pts: [], W, H, x0, x1, y0, y1, scale: null };
        }

        const sc = (function(){ const maxv = Math.max(...data); return niceScale(0, Math.max(1, maxv), tickCount); })();
        const range = sc.niceMax - sc.niceMin;

        const pts = data.map((v,i) => {
          const x = (n===1) ? (x0 + (x1 - x0)/2) : x0 + (x1 - x0) * (i/(n-1));
          const y = y0 - ((v - sc.niceMin)/range) * (y0 - y1);
          return { x, y, v, label: labels[i] ?? '' };
        });

        // clear + grid
        ctx.clearRect(0,0,W,H);
        ctx.font = '12px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif';
        ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
        ctx.fillStyle = NEU500; ctx.strokeStyle = NEU300; ctx.lineWidth = 1;
        sc.ticks.forEach(t=>{
          const y = y0 - ((t - sc.niceMin)/range) * (y0 - y1);
          ctx.globalAlpha = 0.6; ctx.beginPath(); ctx.moveTo(x0,y); ctx.lineTo(x1,y); ctx.setLineDash([3,3]); ctx.stroke();
          ctx.setLineDash([]); ctx.globalAlpha = 1; ctx.fillText(String(t), x0 - 8, y);
        });

        // x labels (wrapped if needed)
        ctx.textAlign = 'center'; ctx.textBaseline = 'top'; ctx.fillStyle = NEU500;
        const maxW = (x1 - x0) / Math.max(1, n-1) * 0.9;
        labels.forEach((lbl,i) => {
          const x = (n===1) ? (x0 + (x1 - x0)/2) : x0 + (x1 - x0) * (i/(n-1));
          // simple wrap: if label width > maxW, truncate with ellipsis
          const text = String(lbl||'');
          if (ctx.measureText(text).width <= maxW) ctx.fillText(text, x, y0 + 8);
          else {
            // truncate
            let t = text;
            while(ctx.measureText(t + '…').width > maxW && t.length > 0) t = t.slice(0,-1);
            ctx.fillText(t + '…', x, y0 + 8);
          }
        });

        // gradient area under curve
        const grad = ctx.createLinearGradient(0, y1, 0, y0);
        grad.addColorStop(0, BRAND300); grad.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.beginPath(); ctx.moveTo(x0,y0);
        pts.forEach(p=> ctx.lineTo(p.x,p.y));
        ctx.lineTo(x1,y0); ctx.closePath();
        ctx.fillStyle = grad; ctx.fill();

        // smooth line (quadratic curve between points)
        ctx.strokeStyle = BRAND700; ctx.lineWidth = 2; ctx.beginPath();
        pts.forEach((p,i) => {
          if (i === 0) ctx.moveTo(p.x,p.y);
          else {
            const prev = pts[i-1];
            const cx = (prev.x + p.x) / 2;
            ctx.quadraticCurveTo(prev.x, prev.y, cx, p.y);
          }
        });
        ctx.stroke();

        // average dashed line (subtle)
        const avg = data.reduce((a,b)=>a+b,0) / Math.max(n,1);
        const yAvg = y0 - ((avg - sc.niceMin)/range) * (y0 - y1);
        ctx.save(); ctx.setLineDash([6,6]); ctx.strokeStyle = BRAND500; ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.moveTo(x0,yAvg); ctx.lineTo(x1,yAvg); ctx.stroke(); ctx.restore();

        // points (draw after line so they sit on top)
        ctx.fillStyle = BRAND700;
        pts.forEach(p => { ctx.beginPath(); ctx.arc(p.x,p.y,3.5,0,Math.PI*2); ctx.fill(); });

        return { ctx, pts, W, H, x0, x1, y0, y1, scale: sc };
      }

      // tooltip element (HTML) — shows only when hovered near a point
      let tip = canvas.__lineTip;
      if(!tip){
        tip = document.createElement('div');
        tip.style.cssText = [
          'position:absolute',
          'padding:6px 8px',
          'background:#fff',
          'border:1px solid '+DEFAULTS.BORDER,
          'color:#111',
          'font:10px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif',
          'border-radius:8px',
          'box-shadow:'+DEFAULTS.SHADOW,
          'pointer-events:none',
          'transform:translate(-50%,-140%)',
          'white-space:nowrap',
          'display:none',
          'z-index:9999'
        ].join(';');
        // place inside the canvas parent (chart-wrap)
        const parent = canvas.parentElement || document.body;
        parent.style.position = parent.style.position || 'relative';
        parent.appendChild(tip);
        canvas.__lineTip = tip;
      }

      let state = draw();

      function onMove(e){
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        if(!state || !state.pts || state.pts.length === 0){ tip.style.display = 'none'; canvas.style.cursor = 'default'; return; }

        // find nearest point by Euclidean distance
        let nearest = null;
        for(let i=0;i<state.pts.length;i++){
          const p = state.pts[i];
          const dx = mx - p.x, dy = my - p.y;
          const dist = Math.sqrt(dx*dx + dy*dy);
          if(nearest === null || dist < nearest.dist) nearest = { index:i, dist, p };
        }

        if(!nearest || nearest.dist > hitRadius){
          tip.style.display = 'none';
          canvas.style.cursor = 'default';
          return;
        }

        // show exact value for that point only
        const pt = nearest.p;
        const label = pt.label || labels[nearest.index] || '';
        const formatted = formatNumber(pt.v, opts.numberFormat || { maximumFractionDigits: 2 });
        tip.textContent = formatted;

        // position tooltip relative to parent
        const parentRect = (canvas.parentElement || document.body).getBoundingClientRect();
        tip.style.left = `${Math.round(rect.left + pt.x - parentRect.left)}px`;
        tip.style.top = `${Math.round(rect.top + pt.y - parentRect.top)}px`;
        tip.style.display = 'block';
        canvas.style.cursor = 'pointer';
      }

      function onLeave(){
        if(canvas.__lineTip) canvas.__lineTip.style.display = 'none';
        canvas.style.cursor = 'default';
      }

      // ensure single handlers
      canvas.removeEventListener('mousemove', canvas.__lineMove);
      canvas.removeEventListener('mouseleave', canvas.__lineLeave);
      canvas.__lineMove = onMove; canvas.__lineLeave = onLeave;
      canvas.addEventListener('mousemove', canvas.__lineMove);
      canvas.addEventListener('mouseleave', canvas.__lineLeave);

      // rerender on resize (updates state.pts)
      observeResize(canvas.parentElement, ()=>{ state = draw(); });

      return {
        redraw: ()=>{ state = draw(); },
        destroy: ()=>{
          canvas.removeEventListener('mousemove', canvas.__lineMove);
          canvas.removeEventListener('mouseleave', canvas.__lineLeave);
          if(canvas.__lineTip) { canvas.__lineTip.remove(); delete canvas.__lineTip; }
          if(canvas.__chartRO) canvas.__chartRO.disconnect();
        }
      };
    };


  // ------------------ Donut chart ------------------
  ChartUtils.renderDonut = function(canvasOrId, labels, data, colors, opts={}){
      const canvas = (typeof canvasOrId === 'string') ? document.getElementById(canvasOrId) : canvasOrId;
      if (!canvas) return;
      const BRAND700 = opts.BRAND700 || DEFAULTS.BRAND700;
      const BRAND500 = opts.BRAND500 || DEFAULTS.BRAND500;
      const BRAND300 = opts.BRAND300 || DEFAULTS.BRAND300;
      const NEU300 = opts.NEU300 || DEFAULTS.NEU300;
      const NEU500 = opts.NEU500 || DEFAULTS.NEU500;
      const legendEl = opts.legendEl ? (typeof opts.legendEl === 'string' ? document.getElementById(opts.legendEl) : opts.legendEl) : null;

      function draw(){
        const dpr = devicePixelRatio || 1;
        canvas.style.width = '100%'; canvas.style.height = '100%';
        const W = canvas.clientWidth || 600, H = canvas.clientHeight || 320;
        canvas.width = W * dpr; canvas.height = H * dpr;
        const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr);
        const cx = W/2, cy = H/2, R = Math.min(W,H)/2 - 10, cut = R * 0.62;
        const numeric = (Array.isArray(data) ? data.slice() : []).map(v => Number(v)||0);
        const total = numeric.reduce((a,b)=>a+b,0);

        if (total === 0 || numeric.every(v => v === 0)){
          drawNoData(ctx, W, H, NEU500, opts.noDataTitle || 'No data', opts.noDataSubtitle || 'No records to show');
          if (legendEl) legendEl.innerHTML = labels.map((t,i)=>`<span class="legend-dot" style="--dot:${colors[i%colors.length]}"></span><span class="legend-label" style="opacity:.6">${t}</span>`).join('');
          return { segments: [] , W, H, ctx };
        }

        const segments = [];
        let a0 = -Math.PI/2;
        numeric.forEach((v,i) => {
          const a1 = a0 + (v/total)*Math.PI*2;
          segments.push({ index:i, label: labels[i] ?? `Slice ${i+1}`, value: v, color: colors[i%colors.length], start: a0, end: a1 });
          a0 = a1;
        });

        ctx.clearRect(0,0,W,H);
        segments.forEach(s => { ctx.beginPath(); ctx.moveTo(cx,cy); ctx.arc(cx,cy,R,s.start,s.end); ctx.closePath(); ctx.fillStyle = s.color; ctx.fill(); });
        ctx.globalCompositeOperation = 'destination-out';
        ctx.beginPath(); ctx.arc(cx,cy,cut,0,Math.PI*2); ctx.fill();
        ctx.globalCompositeOperation = 'source-over';

        if (legendEl) legendEl.innerHTML = labels.map((t,i)=>`<span class="legend-dot" style="--dot:${colors[i%colors.length]}"></span><span class="legend-label">${t}</span>`).join('');

        return { segments, W, H, ctx, cx, cy, cut, R };
      }

      let state = draw();

      // tooltip
      let tip = canvas.__donutTooltip;
      if(!tip){ tip = document.createElement('div');
        tip.style.cssText = 'position:absolute;padding:6px 8px;background:#fff;border:1px solid '+DEFAULTS.BORDER+';color:#111;font:12px system-ui;border-radius:8px;box-shadow:'+DEFAULTS.SHADOW+';pointer-events:none;transform:translate(-50%,-120%);white-space:nowrap;display:none;z-index:9999;';
        canvas.parentElement.appendChild(tip); canvas.__donutTooltip = tip;
      }

      function normAngle(a){ while(a<=-Math.PI) a += 2*Math.PI; while(a>Math.PI) a -= 2*Math.PI; return a; }

      function onMove(e){
        const rect = canvas.getBoundingClientRect(), mx = e.clientX - rect.left, my = e.clientY - rect.top;
        const cx = state.cx || canvas.clientWidth/2, cy = state.cy || canvas.clientHeight/2;
        const dx = mx - cx, dy = my - cy, dist = Math.sqrt(dx*dx + dy*dy);
        if (!state.segments || dist < (state.cut || 0) || dist > (state.R || 1e9)){ tip.style.display='none'; canvas.style.cursor='default'; return; }
        let angle = Math.atan2(dy, dx), a = normAngle(angle);
        const found = state.segments.find(s => {
          const sStart = normAngle(s.start), sEnd = normAngle(s.end);
          if (sStart <= sEnd) return a >= sStart && a < sEnd;
          return a >= sStart || a < sEnd;
        });
        if (!found){ tip.style.display = 'none'; canvas.style.cursor='default'; return; }
        const pct = Math.round((found.value / state.segments.reduce((a,b)=>a+b.value,0)) * 1000)/10;
        tip.textContent = `${found.label} — ${found.value} (${pct}%)`;
        const parentRect = canvas.parentElement.getBoundingClientRect();
        tip.style.left = `${e.clientX - parentRect.left}px`; tip.style.top = `${e.clientY - parentRect.top - 12}px`; tip.style.display = 'block'; canvas.style.cursor = 'pointer';
      }
      function onLeave(){ if(tip) tip.style.display='none'; canvas.style.cursor='default'; }

      canvas.removeEventListener('mousemove', canvas.__donutMoveHandler);
      canvas.removeEventListener('mouseleave', canvas.__donutLeaveHandler);
      canvas.__donutMoveHandler = onMove; canvas.__donutLeaveHandler = onLeave;
      canvas.addEventListener('mousemove', canvas.__donutMoveHandler);
      canvas.addEventListener('mouseleave', canvas.__donutLeaveHandler);

      observeResize(canvas.parentElement, ()=>{ state = draw(); });

      return {
        redraw: ()=>{ state = draw(); },
        destroy: ()=>{ canvas.removeEventListener('mousemove', canvas.__donutMoveHandler); canvas.removeEventListener('mouseleave', canvas.__donutLeaveHandler); if (canvas.__donutTooltip) canvas.__donutTooltip.remove(); if (canvas.__chartRO) canvas.__chartRO.disconnect(); }
      };
    };


  // ------------------ Vertical Bar chart ------------------
  ChartUtils.renderBar = function(canvasOrId, labels, series, opts={}){
    const canvas = (typeof canvasOrId==='string')? document.getElementById(canvasOrId):canvasOrId;
    if(!canvas) return;
    const BRAND700 = opts.BRAND700 || DEFAULTS.BRAND700;
    const BRAND500 = opts.BRAND500 || DEFAULTS.BRAND500;
    const BRAND300 = opts.BRAND300 || DEFAULTS.BRAND300;
    const NEU300 = opts.NEU300 || DEFAULTS.NEU300;
    const NEU500 = opts.NEU500 || DEFAULTS.NEU500;

    function draw(){
      const dpr = devicePixelRatio || 1;
      canvas.style.width='100%'; canvas.style.height='100%';
      const W = canvas.clientWidth || 600, H = canvas.clientHeight || 320;
      canvas.width = W*dpr; canvas.height = H*dpr;
      const ctx = canvas.getContext('2d'); ctx.scale(dpr,dpr);

      const m = { l:44, r:18, t:28, b:44 };
      const x0 = m.l, x1 = W - m.r, y0 = H - m.b;
      let y1 = m.t; // <-- changed to let

      const n = Math.max(labels.length,1);
      const data = (Array.isArray(series)?series.slice():[]).map(v=>Number(v)||0);
      const maxV = Math.max(...data,0);
      const scale = niceScale(0,Math.max(1,maxV),5);
      const range = scale.niceMax - scale.niceMin;

      const allZero = data.every(v=>v===0);
      if(allZero){
        drawNoData(ctx,W,H,NEU500, opts.noDataTitle||'No collections', opts.noDataSubtitle||'No data for the selected period');
        return { W,H,ctx,x0,x1,y0,y1,labels,data };
      }

      ctx.clearRect(0,0,W,H);

      // --- title ---
      if(opts.title){
        ctx.font = `bold 14px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif`;
        ctx.textAlign='center'; ctx.textBaseline='top';
        ctx.fillStyle = NEU500;
        ctx.fillText(opts.title,W/2,6);
        y1 += 10;
      }

      // --- y-axis grid ---
      ctx.font='12px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif';
      ctx.textAlign='right'; ctx.textBaseline='middle'; ctx.fillStyle=NEU500; ctx.strokeStyle=NEU300;
      scale.ticks.forEach(t=>{
        const y = y0 - ((t - scale.niceMin)/range)*(y0 - y1);
        ctx.globalAlpha=0.6; ctx.beginPath(); ctx.moveTo(x0,y); ctx.lineTo(x1,y); ctx.setLineDash([3,3]); ctx.stroke();
        ctx.setLineDash([]); ctx.globalAlpha=1; ctx.fillText(String(t), x0-8, y);
      });

      // --- x-axis labels ---
      // --- x-axis labels with wrapping ---
        const labelFontSize = opts.labelFontSize || 12;
        ctx.font = `${labelFontSize}px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';

        const barSpace = (x1 - x0) / n;
        const barWidth = Math.max(12, barSpace * 0.6);
        const maxLabelWidth = barSpace * 0.9; // max width per bar

        labels.forEach((lbl, i) => {
        const cx = x0 + barSpace * (i + 0.5);

        // split label into multiple lines if too long
        const words = lbl.split(' ');
        const lines = [];
        let currentLine = words[0];
        for (let j = 1; j < words.length; j++) {
            const testLine = currentLine + ' ' + words[j];
            if (ctx.measureText(testLine).width > maxLabelWidth) {
            lines.push(currentLine);
            currentLine = words[j];
            } else {
            currentLine = testLine;
            }
        }
        lines.push(currentLine);

        // draw each line
        lines.forEach((line, idx) => {
            ctx.fillText(line, cx, y0 + 4 + idx * (labelFontSize + 2)); // 2px line spacing
        });
        });


      // --- bars ---
      const palette = opts.palette || [BRAND700,BRAND500,BRAND300,NEU300];
      for(let i=0;i<n;i++){
        const v = data[i]||0;
        const cx = x0 + barSpace*(i+0.5);
        const h = (v/scale.niceMax)*(y0 - y1);
        ctx.fillStyle = palette[i % palette.length];
        ctx.fillRect(cx-barWidth/2, y0-h, barWidth, h);
      }

      return { W,H,ctx,x0,x1,y0,y1,labels,data,barSpace,barWidth,palette,scale };
    }

    let state = draw();

    canvas.onmousemove = e=>{
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const s = state;
      if(!s || !s.labels) return;
      const n = s.labels.length;
      const hoveredIndex = s.data.findIndex((v,i)=>{
        const cx = s.x0 + s.barSpace*(i+0.5);
        const h = (v/s.scale.niceMax)*(s.y0 - s.y1);
        return mouseX>=cx-s.barWidth/2 && mouseX<=cx+s.barWidth/2 && mouseY>=s.y0-h && mouseY<=s.y0;
      });

      state = draw();
      const ctx = state.ctx;
      if(hoveredIndex!==-1){
        const v = state.data[hoveredIndex]||0;
        const cx = state.x0 + state.barSpace*(hoveredIndex+0.5);
        const h = (v/state.scale.niceMax)*(state.y0 - state.y1);
        ctx.font='10px sans-serif';
        ctx.textAlign='center'; ctx.textBaseline='bottom'; ctx.fillStyle='black';
        const nfOpts = opts.numberFormat||{};
        ctx.fillText(formatNumber(v,nfOpts), cx, state.y0-h-4);
      }
    };
    canvas.onmouseleave = ()=>{ state = draw(); };
    observeResize(canvas.parentElement, ()=>{ state = draw(); });

    return {
      redraw: ()=>{ state = draw(); },
      destroy: ()=>{ canvas.onmousemove=null; canvas.onmouseleave=null; if(canvas.__chartRO) canvas.__chartRO.disconnect(); }
    };
  };

  ChartUtils.renderDashboardFromJSON = function(payload, config={}){
    const dash = payload.dashboard_json || payload;

    if(document.getElementById('requestsTrend') && dash.requestsTrend){
      ChartUtils.renderLine('requestsTrend', dash.requestsTrend.labels||[], dash.requestsTrend.data||[], config.lineOpts||{});
      document.querySelector('.chart-skel-req')?.classList?.add('hidden');
    }
    if(document.getElementById('statusBreakdown') && dash.statusBreakdown){
      const palette = config.palette || [DEFAULTS.BRAND700,DEFAULTS.BRAND500,DEFAULTS.BRAND300,DEFAULTS.NEU300];
      ChartUtils.renderDonut('statusBreakdown', dash.statusBreakdown.labels||[], dash.statusBreakdown.data||[], palette, { legendEl:'statusLegend' });
      document.querySelector('.chart-skel-status')?.classList?.add('hidden');
    }

    if(document.getElementById('collectionsTrend') && dash.collectionsTrend){
      ChartUtils.renderLine('collectionsTrend', dash.collectionsTrend.labels||[], dash.collectionsTrend.data||[], config.lineOpts||{});
      document.querySelector('.chart-skel-req')?.classList?.add('hidden');
    }
    if(document.getElementById('collectionsPerMonth') && dash.collectionsPerMonth){
      const pal = config.palette || [DEFAULTS.BRAND700,DEFAULTS.BRAND500,DEFAULTS.BRAND300,DEFAULTS.NEU300];
      ChartUtils.renderBar('collectionsPerMonth', dash.collectionsPerMonth.labels||[], dash.collectionsPerMonth.data||[], { palette:pal });
      document.querySelector('.chart-skel-status')?.classList?.add('hidden');
    }

    if(document.getElementById('casesNature') && dash.casesNature){
      const pal = config.palette || [DEFAULTS.BRAND700,DEFAULTS.BRAND500,DEFAULTS.BRAND300,DEFAULTS.NEU300];
      ChartUtils.renderBar('casesNature', dash.casesNature.labels||[], dash.casesNature.data||[], { palette:pal, labelFontSize: 11, });
      // hide the cases skeleton (was incorrectly hiding .chart-skel-status)
      document.querySelector('.chart-skel-cases')?.classList?.add('hidden');
    }
  };

  // expose
  global.ChartUtils = ChartUtils;

})(window);
