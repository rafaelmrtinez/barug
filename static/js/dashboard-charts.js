/* dashboard-charts.js
   Reusable chart utilities for the barangay dashboards.
   Drop into your static files (e.g. static/js/dashboard-charts.js).
   Exposes global `ChartUtils` object.
*/
(function(global){
  const ChartUtils = {};

  // Read CSS variables with fallback
  function cssVar(name, fallback){
    const v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (v||'').trim() || fallback;
  }

  // Defaults from your theme
  const DEFAULTS = {
    BRAND700: cssVar('--brand-700', '#6d2932'),
    BRAND500: cssVar('--brand-500', '#561c24'),
    BRAND300: cssVar('--brand-300', '#e8d8c4'),
    NEU300: cssVar('--neutral-300', '#d1d5db'),
    NEU500: cssVar('--neutral-500', '#6b7280'),
    BORDER: cssVar('--border', '#ece7e1'),
    SHADOW: cssVar('--shadow', '0 8px 24px rgba(15,23,42,.06)')
  };

  // --- Utility math / nice scale (shared) ---
  function niceNum(range, round){
    const exp = Math.floor(Math.log10(range || 1));
    const f = range / Math.pow(10, exp);
    let nf;
    if (round){
      if (f < 1.5) nf = 1; else if (f < 3) nf = 2; else if (f < 7) nf = 5; else nf = 10;
    } else {
      if (f <= 1) nf = 1; else if (f <= 2) nf = 2; else if (f <= 5) nf = 5; else nf = 10;
    }
    return nf * Math.pow(10, exp);
  }
  function niceScale(min, max, tickCount=5){
    min = Number(min||0);
    max = Number(max||1);
    let range = niceNum(max-min, false);
    const step = niceNum(range/(tickCount-1), true);
    const niceMin = Math.floor(min/step)*step;
    const niceMax = Math.ceil(max/step)*step;
    const ticks = [];
    for (let v = niceMin; v <= niceMax + 1e-9; v += step) ticks.push(Math.round(v*100)/100);
    return {niceMin, niceMax, step, ticks};
  }

  // draw centered no-data message
  function drawNoData(ctx, W, H, NEU500, title='No data', subtitle=''){
    ctx.clearRect(0,0,W,H);
    ctx.save();
    ctx.font = '600 14px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif';
    ctx.fillStyle = NEU500;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(title, W/2, H/2 - (subtitle ? 8 : 0));
    if (subtitle){
      ctx.font = '12px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif';
      ctx.fillStyle = 'rgba(0,0,0,0.55)';
      ctx.fillText(subtitle, W/2, H/2 + 12);
    }
    ctx.restore();
  }

  // Resize observer helper
  function observeResize(el, fn){
    if (!el) return;
    if (!el.__chartRO) el.__chartRO = new ResizeObserver(()=>fn());
    el.__chartRO.observe(el);
  }

  // --- Line chart (with smooth curve + tooltip showing interpolated value) ---
  ChartUtils.renderLine = function(canvasOrId, labels, series, opts = {}){
    const canvas = (typeof canvasOrId === 'string') ? document.getElementById(canvasOrId) : canvasOrId;
    if(!canvas) return;
    const BRAND700 = opts.BRAND700 || DEFAULTS.BRAND700;
    const BRAND500 = opts.BRAND500 || DEFAULTS.BRAND500;
    const BRAND300 = opts.BRAND300 || DEFAULTS.BRAND300;
    const NEU300 = opts.NEU300 || DEFAULTS.NEU300;
    const NEU500 = opts.NEU500 || DEFAULTS.NEU500;
    const tickCount = opts.tickCount || 5;

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

      const allZero = data.every(v => v === 0);
      if (allZero){
        drawNoData(ctx, W, H, NEU500, opts.noDataTitle || 'No requests', opts.noDataSubtitle || 'No data for the selected period');
        return;
      }

      const sc = (function(){ const maxv = Math.max(...data); return niceScale(0, Math.max(1, maxv), tickCount); })();
      const range = sc.niceMax - sc.niceMin;

      const pts = data.map((v,i) => {
        const x = x0 + (x1 - x0) * (i/(n-1));
        const y = y0 - ((v - sc.niceMin)/range) * (y0 - y1);
        return { x, y, v };
      });

      // clear + grid
      ctx.clearRect(0,0,W,H);
      ctx.font = '12px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif';
      ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      ctx.fillStyle = NEU500; ctx.strokeStyle = NEU300; ctx.lineWidth = 1;
      sc.ticks.forEach(t => {
        const y = y0 - ((t - sc.niceMin)/range) * (y0 - y1);
        ctx.globalAlpha = 0.6; ctx.beginPath(); ctx.moveTo(x0,y); ctx.lineTo(x1,y); ctx.setLineDash([3,3]); ctx.stroke();
        ctx.setLineDash([]); ctx.globalAlpha = 1; ctx.fillText(String(t), x0 - 8, y);
      });

      // x labels
      ctx.textAlign = 'center'; ctx.textBaseline = 'top'; ctx.fillStyle = NEU500;
      labels.forEach((lbl,i) => {
        const x = x0 + (x1 - x0) * (i/(n-1));
        if (n <= 10 || i % Math.ceil(n/7) === 0) ctx.fillText(lbl, x, y0 + 8);
      });

      // gradient area
      const grad = ctx.createLinearGradient(0, y1, 0, y0);
      grad.addColorStop(0, BRAND300); grad.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.beginPath(); ctx.moveTo(x0,y0); pts.forEach(p=>ctx.lineTo(p.x,p.y)); ctx.lineTo(x1,y0); ctx.closePath();
      ctx.fillStyle = grad; ctx.fill();

      // smooth line
      ctx.strokeStyle = BRAND700; ctx.lineWidth = 2;
      ctx.beginPath();
      pts.forEach((p,i) => {
        if (i === 0) ctx.moveTo(p.x,p.y);
        else {
          const prev = pts[i-1];
          const cx = (prev.x + p.x) / 2;
          ctx.quadraticCurveTo(prev.x, prev.y, cx, p.y);
        }
      });
      ctx.stroke();

      // average dashed line
      const avg = data.reduce((a,b)=>a+b,0)/Math.max(n,1);
      const yAvg = y0 - ((avg - sc.niceMin)/range) * (y0 - y1);
      ctx.save(); ctx.setLineDash([6,6]); ctx.strokeStyle = BRAND500; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(x0,yAvg); ctx.lineTo(x1,yAvg); ctx.stroke(); ctx.restore();

      // points
      ctx.fillStyle = BRAND700; pts.forEach(p => { ctx.beginPath(); ctx.arc(p.x,p.y,2.5,0,Math.PI*2); ctx.fill(); });

      // return context for tooltip use
      return { ctx, pts, W, H };
    }

    // tooltip element
    let tip = canvas.__lineTip;
    if(!tip){ tip = document.createElement('div');
      tip.style.cssText = 'position:absolute;padding:6px 8px;background:#fff;border:1px solid '+DEFAULTS.BORDER+';color:#111;font:12px system-ui;border-radius:8px;box-shadow:'+DEFAULTS.SHADOW+';pointer-events:none;transform:translate(-50%,-140%);white-space:nowrap;display:none;z-index:9999;';
      canvas.parentElement.appendChild(tip); canvas.__lineTip = tip;
    }

    let state = draw();

    function onMove(e){
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const pts = state.pts;
      let best = null;
      for (let i = 0; i < pts.length - 1; i++){
        const A = pts[i], B = pts[i+1];
        const vx = B.x - A.x, vy = B.y - A.y, wx = mx - A.x, wy = my - A.y;
        const vv = vx*vx + vy*vy;
        const t = vv === 0 ? 0 : Math.max(0, Math.min(1, (wx*vx + wy*vy) / vv));
        const cx = A.x + vx*t, cy = A.y + vy*t;
        const dist = Math.sqrt((mx - cx)**2 + (my - cy)**2);
        if (!best || dist < best.dist) best = { segIndex: i, t, cx, cy, dist };
      }
      if (!best || best.dist > 12){ tip.style.display = 'none'; canvas.style.cursor = 'default'; return; }
      const i = best.segIndex, t = best.t, valA = state.pts[i].v, valB = state.pts[i+1].v;
      const interpValue = (1-t)*valA + t*valB;
      const labelText = (t < 0.5) ? labels[i] : labels[i+1];
      tip.textContent = `${labelText} • ${Math.round(interpValue*10)/10}`;
      tip.style.left = `${best.cx}px`; tip.style.top = `${best.cy - 12}px`; tip.style.display = 'block';
      canvas.style.cursor = 'pointer';
    }
    function onLeave(){ if(canvas.__lineTip) canvas.__lineTip.style.display = 'none'; canvas.style.cursor = 'default'; }

    canvas.removeEventListener('mousemove', canvas.__lineMove);
    canvas.removeEventListener('mouseleave', canvas.__lineLeave);
    canvas.__lineMove = onMove; canvas.__lineLeave = onLeave;
    canvas.addEventListener('mousemove', canvas.__lineMove);
    canvas.addEventListener('mouseleave', canvas.__lineLeave);

    // rerender on resize
    observeResize(canvas.parentElement, ()=> { state = draw(); });

    // return a small control API
    return {
      redraw: () => { state = draw(); },
      destroy: () => {
        canvas.removeEventListener('mousemove', canvas.__lineMove);
        canvas.removeEventListener('mouseleave', canvas.__lineLeave);
        if (canvas.__lineTip) canvas.__lineTip.remove();
        if (canvas.__chartRO) canvas.__chartRO.disconnect();
      }
    };
  };

  // --- Donut / pie chart with center cutout + legend + tooltip ---
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
      redraw: () => { state = draw(); },
      destroy: () => {
        canvas.removeEventListener('mousemove', canvas.__donutMoveHandler);
        canvas.removeEventListener('mouseleave', canvas.__donutLeaveHandler);
        if (canvas.__donutTooltip) canvas.__donutTooltip.remove();
        if (canvas.__chartRO) canvas.__chartRO.disconnect();
      }
    };
  };

  // --- Vertical bar chart (monthly) ---
  ChartUtils.renderBar = function(canvasOrId, labels, series, opts = {}){
    const canvas = (typeof canvasOrId === 'string') ? document.getElementById(canvasOrId) : canvasOrId;
    if (!canvas) return;
    const BRAND700 = opts.BRAND700 || DEFAULTS.BRAND700;
    const BRAND500 = opts.BRAND500 || DEFAULTS.BRAND500;
    const BRAND300 = opts.BRAND300 || DEFAULTS.BRAND300;
    const NEU300 = opts.NEU300 || DEFAULTS.NEU300;
    const NEU500 = opts.NEU500 || DEFAULTS.NEU500;

    function draw(){
      const dpr = devicePixelRatio || 1;
      canvas.style.width = '100%'; canvas.style.height = '100%';
      const W = canvas.clientWidth || 600, H = canvas.clientHeight || 320;
      canvas.width = W * dpr; canvas.height = H * dpr;
      const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr);

      const m = { l:44, r:18, t:28, b:44 };
      const x0 = m.l, x1 = W - m.r, y0 = H - m.b, y1 = m.t;
      const n = Math.max(labels.length, 1);
      const data = (Array.isArray(series) ? series.slice() : []).map(v=>Number(v)||0);
      const maxV = Math.max(...data, 0);
      const scale = niceScale(0, Math.max(1, maxV), 5);
      const range = scale.niceMax - scale.niceMin;

      const allZero = data.every(v => v === 0);
      if (allZero){
        drawNoData(ctx, W, H, NEU500, opts.noDataTitle || 'No collections', opts.noDataSubtitle || 'No data for the selected period');
        return { W, H, ctx, x0, x1, y0, y1, labels, data };
      }

      ctx.clearRect(0,0,W,H);
      ctx.font = '12px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif';
      ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; ctx.fillStyle = NEU500; ctx.strokeStyle = NEU300;
      scale.ticks.forEach(t => {
        const y = y0 - ((t - scale.niceMin)/range)*(y0 - y1);
        ctx.globalAlpha=0.6; ctx.beginPath(); ctx.moveTo(x0,y); ctx.lineTo(x1,y); ctx.setLineDash([3,3]); ctx.stroke();
        ctx.setLineDash([]); ctx.globalAlpha=1; ctx.fillText(String(t), x0-8, y);
      });

      ctx.textAlign = 'center'; ctx.textBaseline = 'top';
      const barSpace = (x1 - x0) / n;
      const barWidth = Math.max(12, barSpace * 0.6);
      labels.forEach((lbl, i) => {
        const cx = x0 + barSpace * (i + 0.5);
        ctx.fillText(lbl, cx, y0 + 8);
      });

      const palette = opts.palette || [BRAND700, BRAND500, BRAND300, NEU300];
      for (let i = 0; i < n; i++){
        const v = data[i] || 0;
        const cx = x0 + barSpace * (i + 0.5);
        const h = (v / scale.niceMax) * (y0 - y1);
        ctx.fillStyle = palette[i % palette.length];
        ctx.fillRect(cx - barWidth/2, y0 - h, barWidth, h);
      }

      return { W, H, ctx, x0, x1, y0, y1, labels, data, barSpace, barWidth, palette, scale };
    }

    let state = draw();

    // hover handler showing value above bar
    canvas.onmousemove = e => {
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const s = state;
      if (!s || !s.labels) return;
      const n = s.labels.length;
      const hoveredIndex = s.data.findIndex((v, i) => {
        const cx = s.x0 + s.barSpace * (i + 0.5);
        const h = (v / s.scale.niceMax) * (s.y0 - s.y1);
        return mouseX >= cx - s.barWidth/2 && mouseX <= cx + s.barWidth/2 && mouseY >= s.y0 - h && mouseY <= s.y0;
      });
      // redraw base
      state = draw();
      const ctx = state.ctx;
      if (hoveredIndex !== -1){
        const v = state.data[hoveredIndex] || 0;
        const cx = state.x0 + state.barSpace * (hoveredIndex + 0.5);
        const h = (v / state.scale.niceMax) * (state.y0 - state.y1);
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'; ctx.fillStyle = 'black';
        ctx.fillText(String(v), cx, state.y0 - h - 4);
      }
    };
    canvas.onmouseleave = ()=> { state = draw(); };

    observeResize(canvas.parentElement, ()=>{ state = draw(); });

    return {
      redraw: () => { state = draw(); },
      destroy: () => { canvas.onmousemove = null; canvas.onmouseleave = null; if (canvas.__chartRO) canvas.__chartRO.disconnect(); }
    };
  };

  // Helper: auto-render from a data object that matches your dashboard_json structure
  ChartUtils.renderDashboardFromJSON = function(payload, config = {}){
    // payload may be either { requestsTrend: {...}, statusBreakdown: {...} } or nested as dashboard_json
    const dash = payload.dashboard_json || payload;

    // clerk defaults
    if (document.getElementById('requestsTrend') && dash.requestsTrend){
      ChartUtils.renderLine('requestsTrend', dash.requestsTrend.labels || [], dash.requestsTrend.data || [], config.lineOpts || {});
      // hide skeleton if present
      document.querySelector('.chart-skel-req')?.classList?.add('hidden');
    }
    if (document.getElementById('statusBreakdown') && dash.statusBreakdown){
      const palette = config.palette || [DEFAULTS.BRAND700, DEFAULTS.BRAND500, DEFAULTS.BRAND300, DEFAULTS.NEU300];
      ChartUtils.renderDonut('statusBreakdown', dash.statusBreakdown.labels || [], dash.statusBreakdown.data || [], palette, { legendEl: 'statusLegend' });
      document.querySelector('.chart-skel-status')?.classList?.add('hidden');
    }

    // treasurer defaults
    if (document.getElementById('collectionsTrend') && dash.collectionsTrend){
      ChartUtils.renderLine('collectionsTrend', dash.collectionsTrend.labels || [], dash.collectionsTrend.data || [], config.lineOpts || {});
      document.querySelector('.chart-skel-req')?.classList?.add('hidden');
    }
    if (document.getElementById('collectionsPerMonth') && dash.collectionsPerMonth){
      const pal = config.palette || [DEFAULTS.BRAND700, DEFAULTS.BRAND500, DEFAULTS.BRAND300, DEFAULTS.NEU300];
      ChartUtils.renderBar('collectionsPerMonth', dash.collectionsPerMonth.labels || [], dash.collectionsPerMonth.data || [], { palette: pal });
      document.querySelector('.chart-skel-status')?.classList?.add('hidden');
    }
  };

  // expose
  global.ChartUtils = ChartUtils;

})(window);
