(() => {
  'use strict';

  /* ── Particle Canvas ── */
  const canvas = document.getElementById('particles');
  const ctx = canvas.getContext('2d');
  let W, H, particles = [], mouse = { x: -1000, y: -1000 };

  function resize() {
    W = canvas.width = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);
  document.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });

  class Particle {
    constructor() { this.reset(); }
    reset() {
      this.x = Math.random() * W;
      this.y = Math.random() * H;
      this.vx = (Math.random() - 0.5) * 0.3;
      this.vy = (Math.random() - 0.5) * 0.3;
      this.r = Math.random() * 2 + 0.8;
      this.alpha = Math.random() * 0.5 + 0.2;
    }
    update() {
      this.x += this.vx;
      this.y += this.vy;
      const dx = mouse.x - this.x, dy = mouse.y - this.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 150) {
        this.x -= dx * 0.005;
        this.y -= dy * 0.005;
      }
      if (this.x < 0 || this.x > W || this.y < 0 || this.y > H) this.reset();
    }
    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
      const t = this.x / W;
      const r = Math.round(154 + (224 - 154) * t);
      const g = Math.round(171 + (120 - 171) * t);
      const b = Math.round(110 + (104 - 110) * t);
      ctx.fillStyle = `rgba(${r},${g},${b},${this.alpha})`;
      ctx.fill();
    }
  }

  const PCOUNT = Math.min(120, Math.floor(W * H / 8000));
  for (let i = 0; i < PCOUNT; i++) particles.push(new Particle());

  function drawLines() {
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 120) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(224,120,104,${0.12 * (1 - dist / 120)})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }
    }
  }

  function animateParticles() {
    ctx.clearRect(0, 0, W, H);
    particles.forEach(p => { p.update(); p.draw(); });
    drawLines();
    requestAnimationFrame(animateParticles);
  }
  animateParticles();

  /* ── Nav Scroll ── */
  const nav = document.getElementById('nav');
  window.addEventListener('scroll', () => {
    nav.classList.toggle('scrolled', window.scrollY > 40);
  });

  /* ── Mobile Nav Toggle ── */
  const navToggle = document.getElementById('navToggle');
  const navLinks = document.querySelector('.nav-links');
  navToggle.addEventListener('click', () => {
    navLinks.classList.toggle('open');
  });
  navLinks.querySelectorAll('a').forEach(a => {
    a.addEventListener('click', () => navLinks.classList.remove('open'));
  });

  /* ── Scroll Reveal ── */
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry, i) => {
      if (entry.isIntersecting) {
        setTimeout(() => entry.target.classList.add('revealed'), i * 60);
        revealObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });

  document.querySelectorAll('[data-reveal]').forEach(el => revealObserver.observe(el));

  /* ── Counter Animation ── */
  const counterObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const el = entry.target;
        const target = parseFloat(el.dataset.count);
        const isDecimal = el.dataset.decimal === 'true';
        const duration = 1500;
        const start = performance.now();
        function step(now) {
          const progress = Math.min((now - start) / duration, 1);
          const eased = 1 - Math.pow(1 - progress, 3);
          const current = eased * target;
          el.textContent = isDecimal ? current.toFixed(1) : Math.round(current);
          if (progress < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
        counterObserver.unobserve(el);
      }
    });
  }, { threshold: 0.5 });

  document.querySelectorAll('[data-count]').forEach(el => counterObserver.observe(el));

  /* ── Preview Chart (Mini RPM) ── */
  const previewCanvas = document.getElementById('previewCanvas');
  if (previewCanvas) {
    const pctx = previewCanvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    let pData = [];
    const PLEN = 80;
    let pFrame = 0;

    const prev = { rpm: 3200, target: 3200, t: 0 };

    function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

    function resizePreview() {
      const rect = previewCanvas.parentElement.getBoundingClientRect();
      previewCanvas.width = rect.width * dpr;
      previewCanvas.height = rect.height * dpr;
      pctx.scale(dpr, dpr);
    }
    resizePreview();
    window.addEventListener('resize', resizePreview);

    function updatePreview() {
      requestAnimationFrame(updatePreview);
      pFrame++;
      if (pFrame % 6 !== 0) return;

      prev.t++;
      if (prev.t % 40 === 0) {
        prev.target = clamp(1200 + Math.random() * 5500, 1000, 7000);
      }
      prev.rpm += (prev.target - prev.rpm) * 0.015 + (Math.random() - 0.5) * 30;
      prev.rpm = clamp(prev.rpm, 800, 7200);

      pData.push(prev.rpm);
      if (pData.length > PLEN) pData.shift();

      const w = previewCanvas.width / dpr;
      const h = previewCanvas.height / dpr;
      pctx.clearRect(0, 0, w, h);

      const min = Math.min(...pData) - 200;
      const max = Math.max(...pData) + 200;

      // Redline
      const redlineY = h - ((9500 - min) / (max - min)) * h;
      pctx.beginPath();
      pctx.moveTo(0, redlineY);
      pctx.lineTo(w, redlineY);
      pctx.strokeStyle = 'rgba(224,92,110,0.3)';
      pctx.lineWidth = 1;
      pctx.setLineDash([4, 4]);
      pctx.stroke();
      pctx.setLineDash([]);

      // Area
      pctx.beginPath();
      pctx.moveTo(0, h);
      pData.forEach((v, i) => {
        const x = (i / (PLEN - 1)) * w;
        const y = h - ((v - min) / (max - min)) * h;
        if (i === 0) pctx.lineTo(x, y);
        else pctx.lineTo(x, y);
      });
      pctx.lineTo(w, h);
      pctx.closePath();
      const grad = pctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, 'rgba(224,120,104,0.3)');
      grad.addColorStop(1, 'rgba(224,120,104,0.02)');
      pctx.fillStyle = grad;
      pctx.fill();

      // Line
      pctx.beginPath();
      pData.forEach((v, i) => {
        const x = (i / (PLEN - 1)) * w;
        const y = h - ((v - min) / (max - min)) * h;
        if (i === 0) pctx.moveTo(x, y);
        else pctx.lineTo(x, y);
      });
      pctx.strokeStyle = '#e07868';
      pctx.lineWidth = 2;
      pctx.stroke();

      // Derive all stats from RPM
      const rpm = Math.round(prev.rpm);
      const temp = clamp(60 + (rpm / 7000) * 35 + (Math.random() - 0.5) * 2, 55, 100);
      const egt = clamp(300 + (rpm / 7000) * 500 + (Math.random() - 0.5) * 10, 250, 850);
      const load = clamp((rpm / 7000) * 90 + (Math.random() - 0.5) * 3, 5, 95);

      document.getElementById('previewRpm').textContent = rpm.toLocaleString();
      document.getElementById('previewTemp').textContent = temp.toFixed(1) + '\u00B0C';
      document.getElementById('previewEgt').textContent = Math.round(egt) + '\u00B0C';
      document.getElementById('previewLoad').textContent = Math.round(load) + '%';
    }
    updatePreview();
  }
})();