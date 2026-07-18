(() => {
  'use strict';

  /* ═══ ENGINE ═══ */
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const jit = (v, r) => v + (Math.random() - 0.5) * r * 2;
  const REDLINE = 9500, MAX_HIST = 120;
  const TARG = { idle: { rpm: 950, load: 8, thr: 4 }, city: { rpm: 2800, load: 38, thr: 30 }, highway: { rpm: 4200, load: 62, thr: 55 }, aggressive: { rpm: 7800, load: 91, thr: 88 }, decel: { rpm: 1200, load: 5, thr: 1 } };
  const NXT = { idle: ['idle', 'city', 'city'], city: ['city', 'city', 'highway', 'aggressive', 'decel', 'idle'], highway: ['highway', 'highway', 'city', 'aggressive', 'decel'], aggressive: ['aggressive', 'highway', 'city', 'decel'], decel: ['decel', 'city', 'idle'] };
  const E = { mode: 'idle', mt: 0, rpm: 950, et: 68, egt: 120, load: 8, thr: 4, spd: 0, fl: 100, ct: 68, iat: 28 };
  const cond = { idle: 0, city: 0, highway: 0, aggressive: 0, decel: 0 };
  let hist = [], sStart = Date.now(), peakRpm = 0, minRpm = Infinity, peakTemp = 0, peakLoad = 0;
  let rate = 2000, loopId = null;
  const gear = s => s < 15 ? 1 : s < 30 ? 2 : s < 55 ? 3 : s < 80 ? 4 : s < 110 ? 5 : 6;

  /* ═══ CONTROLS ═══ */
  let paused = false, manualMode = null;

  function tick() {
    if (!manualMode) { E.mt--; if (E.mt <= 0) { const o = NXT[E.mode]; E.mode = o[~~(Math.random() * o.length)]; E.mt = ~~(Math.random() * 8) + 4; } }
    else { E.mode = manualMode; }
    const t = TARG[E.mode];
    E.rpm = clamp(lerp(E.rpm, jit(t.rpm, 60), 0.18), 600, REDLINE);
    E.load = clamp(lerp(E.load, jit(t.load, 2), 0.15), 0, 100);
    E.thr = clamp(lerp(E.thr, jit(t.thr, 2), 0.20), 0, 100);
    E.spd = clamp(lerp(E.spd, jit((E.rpm / REDLINE) * 160 * (t.load / 100) * 1.4, 3), 0.12), 0, 180);
    E.et = clamp(E.et + E.load * 0.012 + E.rpm * 0.00004 - (E.et - 22) * 0.025 + jit(0, 0.3), 60, 130);
    E.ct = clamp(E.et - jit(3, 1.5), 55, 125);
    E.egt = clamp(lerp(E.egt, jit(90 + E.load * 7.5 + (E.rpm / REDLINE) * 300, 15), 0.10), 80, 900);
    E.iat = clamp(E.iat + jit(0, 0.05), 20, 55);
    E.fl = clamp(E.fl - 0.0003 * (E.load / 100), 0, 100);
    cond[E.mode]++;
    return { ts: Date.now(), rpm: ~~E.rpm, et: +E.et.toFixed(1), egt: +E.egt.toFixed(1), load: +E.load.toFixed(1), thr: +E.thr.toFixed(1), spd: +E.spd.toFixed(1), gear: gear(E.spd), vib: +(clamp(.5 + (E.rpm / REDLINE) * 6 + jit(0, .4), 0, 10)).toFixed(2), oil: +(clamp(1.2 + (E.rpm / REDLINE) * 4.8 + jit(0, .2), 0, 7)).toFixed(2), fp: +(clamp(2.8 + jit(0, .15), 1, 5)).toFixed(2), bat: +(clamp(13.8 + jit(0, .12) - (E.load > 80 ? .4 : 0), 10, 15)).toFixed(2), afr: +(clamp(14.7 + (E.mode === 'aggressive' ? -.8 : 0) + jit(0, .3), 10, 20)).toFixed(2), iat: +E.iat.toFixed(1), map: +(clamp(30 + E.load * .65 + jit(0, 2), 15, 105)).toFixed(1), mode: E.mode, fl: +E.fl.toFixed(2), ct: +E.ct.toFixed(1) };
  }

  function calcHealth(s) {
    if (!s.length) return { e: 100, t: 100, f: 100, el: 100, m: 100, o: 100 };
    const l = s[s.length - 1], sl = s.slice(-30), al = sl.reduce((a, x) => a + x.load, 0) / sl.length, mx = Math.max(...sl.map(x => x.egt));
    const e = clamp(100 - (al > 85 ? (al - 85) * 2 : 0) - (l.rpm > 8500 ? 10 : 0), 0, 100);
    const t = clamp(100 - Math.max(0, l.et - 95) * 2 - Math.max(0, mx - 680) * .15, 0, 100);
    const f = clamp(100 - Math.abs(l.afr - 14.7) * 4 - (l.fp < 2.5 ? 12 : 0), 0, 100);
    const el = clamp(100 - (l.bat < 12 ? 20 : l.bat < 12.5 ? 8 : 0), 0, 100);
    const m = clamp(100 - (l.vib > 5 ? (l.vib - 5) * 6 : 0) - (l.oil < 2 ? 15 : 0), 0, 100);
    return { e: ~~e, t: ~~t, f: ~~f, el: ~~el, m: ~~m, o: ~~((e + t + f + el + m) / 5) };
  }

  function calcAlerts(s, h) {
    const a = [];
    if (s.et > 105) a.push('Engine temp critical');
    if (s.egt > 750) a.push('Exhaust temp high');
    if (s.rpm > REDLINE * .93) a.push('Approaching redline');
    if (s.bat < 12) a.push('Low battery');
    if (s.oil < 1.8) a.push('Low oil pressure');
    if (s.afr < 12.5) a.push('Rich mixture');
    if (s.afr > 16) a.push('Lean mixture');
    if (h.o >= 90 && !a.length) a.push('All systems nominal');
    return a;
  }

  /* ═══ CHARTS ═══ */
  let cRpm, cTemp, cLoad, cPie;

  function makeGradient(ctx, area, r, g, b, topA, botA) {
    if (!area) return `rgba(${r},${g},${b},${topA})`;
    const gr = ctx.createLinearGradient(0, area.top, 0, area.bottom);
    gr.addColorStop(0, `rgba(${r},${g},${b},${topA})`);
    gr.addColorStop(0.6, `rgba(${r},${g},${b},${topA * 0.4})`);
    gr.addColorStop(1, `rgba(${r},${g},${b},${botA})`);
    return gr;
  }

  function initCharts() {
    if (cRpm) { cRpm.destroy(); cRpm = null; }
    if (cTemp) { cTemp.destroy(); cTemp = null; }
    if (cLoad) { cLoad.destroy(); cLoad = null; }
    if (cPie) { cPie.destroy(); cPie = null; }
    Chart.defaults.font.family = "'JetBrains Mono', monospace";
    const isLight = document.documentElement.getAttribute('data-theme') === 'light';
    Chart.defaults.color = isLight ? '#7a80a0' : '#545b78';
    const gridColor = isLight ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.04)';
    const base = { responsive: true, maintainAspectRatio: false, animation: { duration: 0 }, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { ticks: { font: { size: 9 } }, grid: { color: gridColor, drawBorder: false } } } };

    cRpm = new Chart(document.getElementById('cRpm'), {
      type: 'line', data: { labels: [], datasets: [{ data: [], borderColor: '#ff6b35', backgroundColor: (ctx) => { return makeGradient(ctx.chart.ctx, ctx.chart.chartArea, 255, 107, 53, 0.35, 0.01); }, fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2 }] },
      options: { ...base, scales: { x: { display: false }, y: { min: 0, max: REDLINE + 500, ticks: { font: { size: 9 }, callback: v => `${(v / 1000) | 0}k` }, grid: { color: gridColor, drawBorder: false } } } }
    });

    cTemp = new Chart(document.getElementById('cTemp'), {
      type: 'line', data: { labels: [], datasets: [
        { label: 'Engine', data: [], borderColor: '#ffd166', backgroundColor: (ctx) => { return makeGradient(ctx.chart.ctx, ctx.chart.chartArea, 255, 209, 102, 0.25, 0.01); }, fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2 },
        { label: 'EGT', data: [], borderColor: '#ef476f', backgroundColor: (ctx) => { return makeGradient(ctx.chart.ctx, ctx.chart.chartArea, 239, 71, 111, 0.2, 0.01); }, fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2 },
        { label: 'Coolant', data: [], borderColor: '#00d4aa', tension: 0.4, pointRadius: 0, borderWidth: 1.5, borderDash: [5, 3] }
      ] }, options: { ...base, plugins: { legend: { display: true, position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, padding: 12, color: isLight ? '#7a80a0' : '#545b78', font: { size: 9 }, generateLabels: function(chart) { return chart.data.datasets.map(function(ds, i) { var meta = chart.getDatasetMeta(i); var hidden = meta.hidden; return { text: ds.label, fillStyle: hidden ? ds.borderColor : 'rgba(0,0,0,0)', strokeStyle: ds.borderColor, lineWidth: 1.5, lineDash: ds.borderDash || [], datasetIndex: i, fontColor: isLight ? '#7a80a0' : '#545b78' }; }); } }, onClick: function(e, legendItem, legend) { var idx = legendItem.datasetIndex; var meta = legend.chart.getDatasetMeta(idx); meta.hidden = meta.hidden === null ? true : null; legend.chart.update(); } } } }
    });

    cLoad = new Chart(document.getElementById('cLoad'), {
      type: 'line', data: { labels: [], datasets: [
        { label: 'Load', data: [], borderColor: '#a78bfa', backgroundColor: (ctx) => { return makeGradient(ctx.chart.ctx, ctx.chart.chartArea, 167, 139, 250, 0.3, 0.01); }, fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2 },
        { label: 'Throttle', data: [], borderColor: '#00d4aa', backgroundColor: (ctx) => { return makeGradient(ctx.chart.ctx, ctx.chart.chartArea, 0, 212, 170, 0.2, 0.01); }, fill: true, tension: 0.4, pointRadius: 0, borderWidth: 1.5 }
      ] }, options: { ...base, scales: { x: { display: false }, y: { min: 0, max: 100, ticks: { font: { size: 9 }, callback: v => `${v}%` }, grid: { color: gridColor, drawBorder: false } } }, plugins: { legend: { display: true, position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, padding: 12, color: isLight ? '#7a80a0' : '#545b78', font: { size: 9 }, generateLabels: function(chart) { return chart.data.datasets.map(function(ds, i) { var meta = chart.getDatasetMeta(i); var hidden = meta.hidden; return { text: ds.label, fillStyle: hidden ? ds.borderColor : 'rgba(0,0,0,0)', strokeStyle: ds.borderColor, lineWidth: 1.5, datasetIndex: i, fontColor: isLight ? '#7a80a0' : '#545b78' }; }); } }, onClick: function(e, legendItem, legend) { var idx = legendItem.datasetIndex; var meta = legend.chart.getDatasetMeta(idx); meta.hidden = meta.hidden === null ? true : null; legend.chart.update(); } } } }
    });

    cPie = new Chart(document.getElementById('cPie'), {
      type: 'doughnut', data: { labels: ['Idle', 'City', 'Hwy', 'Aggro', 'Decel'], datasets: [{ data: [1, 1, 1, 1, 1], backgroundColor: ['#363c5c', '#ff6b35', '#00d4aa', '#ef476f', '#ffd166'], borderWidth: 0, borderRadius: 3, spacing: 3 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '65%', animation: { duration: 0 }, plugins: { legend: { display: false }, tooltip: { backgroundColor: isLight ? '#ffffff' : '#1a2038', borderColor: isLight ? 'rgba(0,0,0,0.1)' : 'rgba(255,255,255,0.08)', borderWidth: 1, bodyColor: isLight ? '#1a1d2e' : '#eaecf4', bodyFont: { family: "'JetBrains Mono'", weight: 600 }, padding: 8, cornerRadius: 8 } } }
    });
  }

  /* ═══ TACHO TICKS ═══ */
  function drawTachoTicks() {
    const g = document.getElementById('tachoTicks');
    let html = '';
    for (let i = 0; i <= 10; i++) {
      const angle = -225 + (i / 10) * 270;
      const rad = angle * Math.PI / 180;
      const r1 = 75, r2 = i % 2 === 0 ? 68 : 71;
      const x1 = 100 + r1 * Math.cos(rad), y1 = 100 + r1 * Math.sin(rad);
      const x2 = 100 + r2 * Math.cos(rad), y2 = 100 + r2 * Math.sin(rad);
      html += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="rgba(255,255,255,0.3)" stroke-width="${i % 2 === 0 ? 1.5 : 0.8}"/>`;
      if (i % 2 === 0) {
        const r3 = 62;
        const x3 = 100 + r3 * Math.cos(rad), y3 = 100 + r3 * Math.sin(rad);
        html += `<text x="${x3}" y="${y3}" text-anchor="middle" dominant-baseline="central" fill="rgba(255,255,255,0.2)" font-size="7" font-family="JetBrains Mono">${(i * 1000 / 10 * 10)}</text>`;
      }
    }
    g.innerHTML = html;
  }

  /* ═══ UI ═══ */
  const $ = id => document.getElementById(id);
  const fmt = (n, d = 1) => n != null ? n.toFixed(d) : '—';
  const TACHO_CIRC = 534;
  const cv = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  function updUI(s, h) {
    const cText = cv('--text'), cCorl = cv('--coral'), cGold = cv('--gold'), cMint = cv('--mint');

    $('vBat').textContent = fmt(s.bat, 2) + 'V';
    $('vBatSub').textContent = s.bat < 12 ? 'Low voltage' : s.bat > 14.5 ? 'Overcharging' : 'Normal voltage';
    $('barBat').style.width = `${clamp(((s.bat - 10) / 5) * 100, 0, 100)}%`;
    $('vBat').style.color = s.bat < 12 ? cCorl : s.bat > 14.5 ? cGold : cText;

    $('vTemp').textContent = fmt(s.et) + '°';
    $('vTempSub').textContent = s.et > 100 ? 'Above safe' : 'Normal range';
    $('barTemp').style.width = `${clamp((s.et / 130) * 100, 0, 100)}%`;
    $('vTemp').style.color = s.et > 100 ? cCorl : cText;

    $('vEgt').textContent = fmt(s.egt, 0) + '°';
    $('vEgtSub').textContent = s.egt > 700 ? 'High EGT' : 'Safe range';
    $('barEgt').style.width = `${clamp((s.egt / 900) * 100, 0, 100)}%`;
    $('vEgt').style.color = s.egt > 700 ? cCorl : cText;

    $('vLoad').textContent = fmt(s.load) + '%';
    $('vLoadSub').textContent = s.load > 80 ? 'Heavy' : 'Moderate';
    $('barLoad').style.width = `${s.load}%`;
    $('vLoad').style.color = s.load > 80 ? cCorl : cText;

    $('vSpeed').textContent = fmt(s.spd, 0);
    $('vSpeedSub').textContent = `Gear ${s.gear}`;
    $('barSpeed').style.width = `${clamp((s.spd / 180) * 100, 0, 100)}%`;
    $('vSpeed').style.color = cText;

    $('vAfr').textContent = fmt(s.afr, 2);
    const afrStatus = Math.abs(s.afr - 14.7) < 0.5 ? 'Stoichiometric' : s.afr < 14.7 ? 'Rich' : 'Lean';
    $('vAfrSub').textContent = afrStatus;
    $('barAfr').style.width = `${clamp(((s.afr - 10) / 10) * 100, 0, 100)}%`;
    $('vAfr').style.color = Math.abs(s.afr - 14.7) < 0.5 ? cMint : cGold;

    // Tacho
    peakRpm = Math.max(peakRpm, s.rpm);
    minRpm = Math.min(minRpm === Infinity ? s.rpm : minRpm, s.rpm);
    peakTemp = Math.max(peakTemp, s.et);
    peakLoad = Math.max(peakLoad, s.load);

    $('tachoVal').textContent = s.rpm.toLocaleString();
    $('tachoVal').style.color = s.rpm > 8000 ? cCorl : s.rpm > 6000 ? cGold : cText;
    $('tachoPeak').textContent = peakRpm.toLocaleString();
    const pct = (s.rpm / REDLINE) * 100;
    $('tachoArc').setAttribute('stroke-dasharray', `${(pct / 100) * TACHO_CIRC} ${TACHO_CIRC}`);

    // RPM chart badge
    $('cbRpm').textContent = s.rpm.toLocaleString();
    $('cbRpm').className = 'cc-badge' + (s.rpm > 8000 ? ' c' : s.rpm > 6000 ? ' w' : '');
    $('cbTemp').textContent = fmt(s.et) + '°C';
    $('cbTemp').className = 'cc-badge' + (s.et > 100 ? ' c' : '');
    $('cbLoad').textContent = fmt(s.load) + '%';
    $('cbLoad').className = 'cc-badge' + (s.load > 80 ? ' w' : '');

    // Foot stats
    $('fPeakRpm').textContent = peakRpm.toLocaleString();
    $('fMinRpm').textContent = minRpm === Infinity ? '—' : minRpm.toLocaleString();
    $('fPeakTemp').textContent = peakTemp + '°C';
    $('fLiveEgt').textContent = s.egt.toFixed(0) + '°C';
    $('fPeakLoad').textContent = peakLoad.toFixed(1) + '%';
    const last20 = hist.slice(-20);
    $('fAvgLoad').textContent = (last20.length ? (last20.reduce((a, x) => a + x.load, 0) / last20.length).toFixed(1) : '0') + '%';

    // Health
    $('healthVal').textContent = h.o;
    $('healthVal').style.color = cText;
    setArc('healthArc', h.o);
    const g = h.o >= 90 ? 'A' : h.o >= 75 ? 'B' : h.o >= 55 ? 'C' : 'D';
    const gLabel = { A: 'Excellent', B: 'Good', C: 'Fair', D: 'Attention' }[g];
    $('healthGrade').textContent = `- ${gLabel}`;
    $('healthGrade').style.color = h.o >= 85 ? cv('--mint') : h.o >= 70 ? cv('--teal') : h.o >= 55 ? cv('--gold') : cv('--coral');
    const hc = h.o >= 85 ? cv('--mint') : h.o >= 70 ? cv('--teal') : h.o >= 55 ? cv('--gold') : cv('--coral');
    $('healthArc').setAttribute('stroke', hc);

    const cTeal = cv('--teal'), cSky = cv('--sky'), cFire = cv('--fire');
    [['hb1', 'hb1v', h.e], ['hb2', 'hb2v', h.t], ['hb3', 'hb3v', h.f], ['hb4', 'hb4v', h.el], ['hb5', 'hb5v', h.m]].forEach(([b, v, val]) => {
      $(v).textContent = val;
      const el = $(b);
      el.style.width = val + '%';
      el.style.background = val >= 85 ? `linear-gradient(90deg,${cMint},${cTeal})` : val >= 70 ? `linear-gradient(90deg,${cTeal},${cSky})` : val >= 50 ? `linear-gradient(90deg,${cGold},${cFire})` : `linear-gradient(90deg,${cCorl},${cFire})`;
      $(v).style.color = val >= 70 ? cText : cCorl;
    });

    // Alerts
    const alerts = calcAlerts(s, h);
    $('alerts').innerHTML = alerts.map(a => {
      const cls = a.startsWith('All') ? 'ok' : a.includes('critical') || a.includes('redline') ? 'c' : 'w';
      return `<div class="al ${cls}"><div class="al-dot"></div>${a}</div>`;
    }).join('');

    // Sensors
    const sw = (id, v, w) => { const e = $(id); e.textContent = v; e.className = w || ''; };
    sw('sBat', fmt(s.bat, 2) + ' V', s.bat < 12 ? 'crit' : s.bat < 12.5 ? 'warn' : 'ok');
    sw('sOil', fmt(s.oil, 2) + ' bar', s.oil < 1.8 ? 'crit' : s.oil < 2 ? 'warn' : 'ok');
    sw('sFuelP', fmt(s.fp, 2) + ' bar', 'ok');
    sw('sMap', fmt(s.map, 0) + ' kPa', 'ok');
    sw('sIntake', fmt(s.iat) + '°C', 'ok');
    sw('sCoolant', fmt(s.ct) + '°C', s.ct > 100 ? 'warn' : 'ok');
    sw('sVib', fmt(s.vib, 2) + ' g', s.vib > 5 ? 'warn' : 'ok');
    sw('sFuel', fmt(s.fl, 1) + '%', s.fl < 15 ? 'warn' : 'ok');
    sw('sThr', fmt(s.thr) + '%', 'ok');
    sw('sGear', 'G' + s.gear, 'ok');
    sw('sMode', s.mode, 'ok');
  }

  const HEALTH_CIRC = 314;
  function setArc(id, pct) { $(id).setAttribute('stroke-dasharray', `${(pct / 100) * HEALTH_CIRC} ${HEALTH_CIRC}`); }

  /* ═══ CHARTS UPDATE ═══ */
  function updCharts() {
    const l = hist.map((_, i) => i);
    cRpm.data.labels = l; cRpm.data.datasets[0].data = hist.map(s => s.rpm); cRpm.update('none');
    cTemp.data.labels = l; cTemp.data.datasets[0].data = hist.map(s => s.et); cTemp.data.datasets[1].data = hist.map(s => s.egt); cTemp.data.datasets[2].data = hist.map(s => s.ct); cTemp.update('none');
    cLoad.data.labels = l; cLoad.data.datasets[0].data = hist.map(s => s.load); cLoad.data.datasets[1].data = hist.map(s => s.thr); cLoad.update('none');
    const tot = Object.values(cond).reduce((a, b) => a + b, 0) || 1;
    cPie.data.datasets[0].data = ['idle', 'city', 'highway', 'aggressive', 'decel'].map(m => Math.round((cond[m] / tot) * 100));
    cPie.update('none');
  }

  /* ═══ CLOCK ═══ */
  function updClock() {
    const e = ~~((Date.now() - sStart) / 1000);
    $('clock').textContent = `${String(~~(e / 60)).padStart(2, '0')}:${String(e % 60).padStart(2, '0')}`;
  }

  /* ═══ LOOP ═══ */
  function startLoop() {
    if (loopId) clearInterval(loopId);
    loopId = setInterval(() => { const s = tick(); hist.push(s); if (hist.length > MAX_HIST) hist.shift(); updUI(s, calcHealth(hist)); updCharts(); updClock(); }, rate);
  }

  /* ═══ MODAL ═══ */
  let mStep = 0;
  let mPath = 'demo';
  window.setMPath = function(p) { mPath = p; };
  window.mNext = function () {
    mStep++;
    if (mStep >= 3) { mPath === 'live' ? goLive() : goDemo(); return; }
    renderM();
  };
  window.mPrev = function () { mStep = Math.max(0, mStep - 1); renderM(); };
  function renderM() {
    $('mSteps').style.display = mStep === 0 ? '' : 'none';
    $('mModes').style.display = mStep === 1 ? '' : 'none';
    $('mDl').style.display = mStep === 2 ? '' : 'none';
    $('mBack').style.display = mStep > 0 ? '' : 'none';
    $('mFine').style.display = mStep === 0 ? '' : 'none';
    $('mBtn').textContent = mStep === 0 ? 'Begin →' : 'Start Live →';
    $('mBtn').style.display = mStep === 1 ? 'none' : '';
  }

  const BRIDGE = 'http://localhost:8765';
  let useBridge = false;

  window.goDemo = function () {
    $('modal').style.display = 'none';
    $('dash').classList.remove('hidden');
    useBridge = false;
    sStart = Date.now();
    initCharts(); drawTachoTicks(); startLoop();
  };

  window.goLive = function () {
    $('modal').style.display = 'none';
    $('scanDialog').classList.remove('hidden');
    $('scanStatus').textContent = 'Connecting to ECU Pulse Bridge...';
    $('scanBar').style.width = '15%';

    const poll = setInterval(async () => {
      try {
        const r = await fetch(BRIDGE + '/status');
        if (!r.ok) throw new Error('not ready');
        const info = await r.json();

        $('scanBar').style.width = '60%';
        $('scanStatus').textContent = info.mode === 'scanning'
          ? 'Scanning COM ports for adapter...'
          : 'Adapter found. Initializing...';

        if (info.mode === 'scanning') return;

        clearInterval(poll);
        $('scanBar').style.width = '100%';
        $('scanStatus').textContent = info.mode === 'live'
          ? 'Adapter connected. Starting live data...'
          : 'No adapter found. Using bridge simulation...';

        setTimeout(() => {
          $('scanDialog').classList.add('hidden');
          $('dash').classList.remove('hidden');
          useBridge = true;
          sStart = Date.now();
          initCharts(); drawTachoTicks(); startBridgeLoop();
        }, 800);
      } catch (e) {
        clearInterval(poll);
        $('scanStatus').textContent = 'Bridge not found. Using local simulation...';
        $('scanBar').style.width = '100%';
        setTimeout(() => {
          $('scanDialog').classList.add('hidden');
          $('dash').classList.remove('hidden');
          useBridge = false;
          sStart = Date.now();
          initCharts(); drawTachoTicks(); startLoop();
          showToast('OBD2 not connected — shifting to simulation');
        }, 1200);
      }
    }, 500);
  };

  function startBridgeLoop() {
    if (loopId) clearInterval(loopId);
    loopId = setInterval(async () => {
      try {
        const r = await fetch(BRIDGE + '/data');
        if (!r.ok) throw new Error('not ready');
        const d = await r.json();
        const s = {
          ts: Date.now(),
          mode: d.mode || 'live',
          rpm: d.rpm || 0,
          spd: d.speed || 0,
          gear: d.gear || 1,
          et: d.engine_temp || 0,
          egt: d.exhaust_temp || 0,
          coolant: d.engine_temp || 0,
          intake: d.intake_temp || 0,
          load: d.engine_load || 0,
          throttle: d.throttle || 0,
          oil: d.oil_pressure || 0,
          fuel_psi: d.fuel_pressure || 0,
          bat: d.battery || 0,
          afr: d.afr || 0,
          vib: d.vibration || 0,
          fl: 100
        };
        hist.push(s);
        if (hist.length > MAX_HIST) hist.shift();
        updUI(s, calcHealth(hist));
        updCharts(); updClock();
      } catch (e) {
        useBridge = false;
        clearInterval(loopId);
        loopId = null;
        startLoop();
        showToast('Bridge disconnected — falling back to simulation');
      }
    }, rate);
  }

  /* ═══ TOAST ═══ */
  function showToast(msg) {
    const t = $('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 4000);
  }

  /* ═══ CONTROLS ═══ */
  window.toggleSide = function () { $('side').classList.toggle('open'); $('sideOverlay').classList.toggle('open'); };

  window.togglePause = function () {
    paused = !paused;
    if (paused) { clearInterval(loopId); loopId = null; $('pauseBtn').textContent = 'Resume'; $('pauseBtn').classList.add('active'); $('statusDot').classList.add('paused'); $('statusLabel').textContent = useBridge ? 'Live Paused' : 'Simulation Paused'; $('statusSub').textContent = 'Click resume to continue'; }
    else { useBridge ? startBridgeLoop() : startLoop(); $('pauseBtn').textContent = 'Pause'; $('pauseBtn').classList.remove('active'); $('statusDot').classList.remove('paused'); $('statusLabel').textContent = useBridge ? 'Live Active' : 'Simulation Active'; $('statusSub').textContent = useBridge ? 'Reading OBD2 data' : 'Physics engine running'; }
  };

  window.forceMode = function (m, el) {
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    if (el) el.classList.add('active');
    if (m === 'auto') { manualMode = null; $('statusDot').classList.remove('manual'); $('statusLabel').textContent = paused ? (useBridge ? 'Live Paused' : 'Simulation Paused') : (useBridge ? 'Live Active' : 'Simulation Active'); $('statusSub').textContent = paused ? 'Click resume to continue' : (useBridge ? 'Reading OBD2 data' : 'Physics engine running'); }
    else { manualMode = m; E.mode = m; E.mt = 999; $('statusDot').classList.add('manual'); $('statusLabel').textContent = 'Manual Mode'; $('statusSub').textContent = `Locked to ${m}`; }
  };

  window.setActiveSpd = function (btn) {
    document.querySelectorAll('.spd-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const sel = $('selRate');
    if (sel) sel.value = btn.dataset.rate;
  };

  window.syncSpdBtns = function (v) {
    document.querySelectorAll('.spd-btn').forEach(b => { b.classList.toggle('active', b.dataset.rate === v); });
  };

  window.setRate = function (v) { rate = +v; if (loopId) { clearInterval(loopId); loopId = null; useBridge ? startBridgeLoop() : startLoop(); } };

  window.resetStats = function () {
    hist = []; peakRpm = 0; minRpm = Infinity; peakTemp = 0; peakLoad = 0;
    Object.keys(cond).forEach(k => cond[k] = 0);
    sStart = Date.now();
  };

  window.copySnapshot = function () {
    if (!hist.length) return;
    const s = hist[hist.length - 1];
    const txt = `ECU Snapshot @ ${new Date(s.ts).toLocaleTimeString()}\nMode: ${s.mode} | RPM: ${s.rpm} | Speed: ${s.spd.toFixed(0)} km/h | Gear: ${s.gear}\nTemp: ${s.et}°C | EGT: ${s.egt}°C | Load: ${s.load}%\nBattery: ${s.bat}V | Oil: ${s.oil} bar | AFR: ${s.afr}`;
    navigator.clipboard.writeText(txt).then(() => {
      const btn = document.querySelector('.side-btn-ghost');
      btn.textContent = 'Copied!';
      setTimeout(() => btn.textContent = 'Copy Snapshot', 1500);
    });
  };

  window.toggleTheme = function () {
    const html = document.documentElement;
    const isLight = html.getAttribute('data-theme') === 'light';
    html.setAttribute('data-theme', isLight ? '' : 'light');
    localStorage.setItem('ecu-theme', isLight ? 'dark' : 'light');
    $('iconSun').style.display = isLight ? 'none' : '';
    $('iconMoon').style.display = isLight ? '' : 'none';
  };

  // Restore theme
  (function () {
    const saved = localStorage.getItem('ecu-theme');
    if (saved === 'light') { document.documentElement.setAttribute('data-theme', 'light'); $('iconSun').style.display = ''; $('iconMoon').style.display = 'none'; }
  })();
  window.importCsv = function () {
    const input = document.createElement('input');
    input.type = 'file'; input.accept = '.csv';
    input.onchange = function (e) {
      const file = e.target.files[0]; if (!file) return;
      const reader = new FileReader();
      reader.onload = function (ev) {
        const text = ev.target.result.replace(/\r/g, '');
        const lines = text.trim().split('\n').filter(l => l.trim());
        if (lines.length < 2) return;
        const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
        const rows = lines.slice(1).map(l => {
          const vals = l.split(',');
          const obj = {};
          headers.forEach((h, i) => obj[h] = vals[i] !== undefined ? vals[i].trim() : '');
          return obj;
        });
        const map = (r, ...keys) => { for (const k of keys) { if (r[k] !== undefined && r[k] !== '') return +r[k]; } return 0; };
        if (loopId) { clearInterval(loopId); loopId = null; }
        paused = false; $('pauseBtn').textContent = 'Pause'; $('pauseBtn').classList.remove('active');
        $('statusDot').classList.remove('paused'); $('statusLabel').textContent = 'CSV Playback'; $('statusSub').textContent = `${rows.length} rows loaded`;
        hist = []; Object.keys(cond).forEach(k => cond[k] = 0);
        peakRpm = 0; minRpm = Infinity; peakTemp = 0; peakLoad = 0;
        sStart = Date.now();
        let idx = 0;
        initCharts(); drawTachoTicks();
        loopId = setInterval(() => {
          if (idx >= rows.length) {
            clearInterval(loopId); loopId = null;
            $('statusLabel').textContent = 'Playback Complete';
            $('statusSub').textContent = `${rows.length} rows played`;
            return;
          }
          const r = rows[idx];
          const mode = (r.mode || 'idle').toLowerCase();
          if (cond[mode] !== undefined) cond[mode]++;
          let tsVal = Date.now();
          if (r.timestamp) { const d = new Date(r.timestamp); if (!isNaN(d.getTime())) tsVal = d.getTime(); }
          else if (r.ts) { const n = +r.ts; tsVal = n > 1e10 ? n : Date.now(); }
          const s = {
            ts: tsVal, mode: mode,
            rpm: map(r, 'rpm'), et: map(r, 'engine_temp', 'et') || 60, egt: map(r, 'exhaust_gas_temp', 'egt') || 200,
            ct: map(r, 'coolant_temp', 'ct') || 57, iat: map(r, 'intake_air_temp', 'iat') || 27, load: map(r, 'engine_load', 'load'),
            thr: map(r, 'throttle', 'thr'), oil: map(r, 'oil_pressure', 'oil') || 2, fp: map(r, 'fuel_pressure', 'fp') || 2.8,
            bat: map(r, 'battery_voltage', 'bat') || 13.8, afr: map(r, 'air_fuel_ratio', 'afr') || 14.7, map: map(r, 'manifold_pressure', 'map') || 35,
            vib: map(r, 'vibration', 'vib') || 1, fl: map(r, 'fuel_level', 'fl') || 100, spd: map(r, 'speed', 'spd'),
            gear: map(r, 'gear') || 1
          };
          hist.push(s);
          if (hist.length > MAX_HIST) hist.shift();
          updUI(s, calcHealth(hist));
          updCharts();
          updClock();
          $('statusSub').textContent = `Row ${idx + 1} / ${rows.length}`;
          idx++;
        }, rate);
      };
      reader.readAsText(file);
    };
    input.click();
  };
  window.exportCsv = function () {
    if (!hist.length) return;
    const h = ['timestamp', 'mode', 'rpm', 'speed', 'gear', 'engine_temp', 'exhaust_gas_temp', 'coolant_temp', 'intake_air_temp', 'engine_load', 'throttle', 'oil_pressure', 'fuel_pressure', 'battery_voltage', 'air_fuel_ratio', 'manifold_pressure', 'vibration', 'fuel_level'];
    const csv = [h.join(','), ...hist.map(s => {
      const ts = new Date(s.ts);
      const pad = n => String(n).padStart(2, '0');
      const stamp = `${ts.getFullYear()}-${pad(ts.getMonth()+1)}-${pad(ts.getDate())} ${pad(ts.getHours())}:${pad(ts.getMinutes())}:${pad(ts.getSeconds())}`;
      return [stamp, s.mode, s.rpm, s.spd, s.gear, s.et, s.egt, s.ct, s.iat, s.load, s.thr, s.oil, s.fp, s.bat, s.afr, s.map, s.vib, s.fl].join(',');
    })].join('\n');
    const b = new Blob([csv], { type: 'text/csv' }), u = URL.createObjectURL(b), a = document.createElement('a');
    a.href = u; a.download = `ecu_${new Date().toISOString().slice(0, 19).replace(/[:.]/g, '-')}.csv`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(u);
  };
})();