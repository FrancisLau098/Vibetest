(() => {
  'use strict';

  // Starfield background on #bg canvas
  const canvas = document.getElementById('bg');
  const ctx = canvas.getContext('2d');

  const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
  let vw = 0, vh = 0, cw = 0, ch = 0;

  function resize() {
    vw = window.innerWidth;
    vh = window.innerHeight;
    cw = Math.floor(vw * dpr);
    ch = Math.floor(vh * dpr);
    canvas.width = cw;
    canvas.height = ch;
    canvas.style.width = vw + 'px';
    canvas.style.height = vh + 'px';
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);
  }
  resize();
  window.addEventListener('resize', resize);

  function rand(min, max) { return Math.random() * (max - min) + min; }

  // Build layered starfield (parallax)
  const layers = [
    { count: 80,  size: [1, 1.6], speed: [10, 18], color: 'rgba(154,223,255,0.55)' },
    { count: 60,  size: [1.2, 2.2], speed: [18, 30], color: 'rgba(255,243,170,0.55)' },
    { count: 40,  size: [1.6, 2.8], speed: [30, 48], color: 'rgba(177,140,255,0.55)' }
  ];

  const stars = [];
  for (const layer of layers) {
    for (let i = 0; i < layer.count; i++) {
      stars.push({
        x: rand(0, vw),
        y: rand(0, vh),
        r: rand(layer.size[0], layer.size[1]),
        spd: rand(layer.speed[0], layer.speed[1]),
        hue: layer.color,
        tw: rand(0.6, 1.0),
        t: rand(0, Math.PI * 2)
      });
    }
  }

  let last = performance.now();
  function draw(now) {
    const dt = Math.min(0.04, (now - last) / 1000);
    last = now;
    ctx.clearRect(0, 0, vw, vh);

    // subtle vignette
    const grd = ctx.createRadialGradient(vw/2, vh/2, Math.min(vw, vh)*0.1, vw/2, vh/2, Math.max(vw, vh));
    grd.addColorStop(0, 'rgba(6,12,22,0)');
    grd.addColorStop(1, 'rgba(3,6,14,0.6)');
    ctx.fillStyle = grd;
    ctx.fillRect(0, 0, vw, vh);

    // stars drift from top-right to bottom-left
    for (const s of stars) {
      s.x -= s.spd * dt * 0.6;
      s.y += s.spd * dt * 0.4;
      s.t += dt * 4;
      let alpha = 0.7 + Math.sin(s.t) * 0.3;
      if (s.x < -10) s.x = vw + 10;
      if (s.y > vh + 10) s.y = -10;

      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fillStyle = s.hue.replace('0.55', (0.35 + alpha * 0.35).toFixed(2));
      ctx.shadowBlur = 8;
      ctx.shadowColor = '#9adfff';
      ctx.fill();
      ctx.shadowBlur = 0;
    }

    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);

  // Sparkles on pointer
  const stage = document.querySelector('.stage');
  function sparkle(x, y) {
    const el = document.createElement('div');
    el.className = 'sparkle';
    el.style.left = x + 'px';
    el.style.top = y + 'px';
    stage.appendChild(el);
    setTimeout(() => el.remove(), 900);
  }
  let lastSparkle = 0;
  stage.addEventListener('mousemove', (e) => {
    const now = performance.now();
    if (now - lastSparkle > 40) {
      sparkle(e.clientX, e.clientY);
      lastSparkle = now;
    }
  });
  stage.addEventListener('click', (e) => sparkle(e.clientX, e.clientY));

  // Retro counter fake increment
  const hits = document.getElementById('hits');
  function pad(n, len) { return String(n).padStart(len, '0'); }
  if (hits) {
    let val = parseInt(hits.textContent || '0', 10) || 0;
    setInterval(() => {
      val += Math.floor(rand(1, 4));
      hits.textContent = pad(val, (hits.textContent || '').length || 6);
    }, 2500);
  }

  // Login interactions
  const form = document.getElementById('loginForm');
  const overlay = document.getElementById('overlay');
  const accessText = document.getElementById('accessText');
  if (form && overlay && accessText) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      overlay.classList.add('show');
      accessText.textContent = 'VERIFYING…';
      setTimeout(() => {
        accessText.textContent = 'ACCESS GRANTED';
        // subtle flash sparkles
        for (let i = 0; i < 14; i++) {
          const x = vw * 0.5 + Math.cos(i / 14 * Math.PI * 2) * 160 + rand(-20, 20);
          const y = vh * 0.5 + Math.sin(i / 14 * Math.PI * 2) * 80 + rand(-12, 12);
          sparkle(x, y);
        }
      }, 900);
      setTimeout(() => {
        overlay.classList.remove('show');
      }, 2400);
    });
  }

  // Lucky draw (gacha) surprises
  const gachaBtn = document.getElementById('gacha');
  const banner = document.querySelector('.banner h1');
  const surprises = {
    confetti: () => {
      // emoji confetti burst
      const emojis = ['✨','💫','🌟','🪐','🚀','⭐'];
      for (let i = 0; i < 28; i++) {
        const span = document.createElement('span');
        span.textContent = emojis[Math.floor(Math.random() * emojis.length)];
        span.style.position = 'absolute';
        span.style.left = (vw / 2) + 'px';
        span.style.top = (vh / 2 - 40) + 'px';
        span.style.fontSize = (18 + Math.random() * 18) + 'px';
        span.style.transform = 'translate(-50%,-50%)';
        span.style.transition = 'transform 900ms cubic-bezier(.2,.8,.2,1), opacity 900ms ease';
        stage.appendChild(span);
        const angle = Math.random() * Math.PI * 2;
        const dist = 160 + Math.random() * 160;
        requestAnimationFrame(() => {
          span.style.transform = `translate(${Math.cos(angle)*dist}px, ${Math.sin(angle)*dist}px)`;
          span.style.opacity = '0';
        });
        setTimeout(() => span.remove(), 1000);
      }
    },
    neonFlash: () => {
      // neon frame flash
      const el = document.createElement('div');
      el.style.position = 'absolute';
      el.style.inset = '0';
      el.style.boxShadow = 'inset 0 0 120px rgba(27,215,255,0.6), 0 0 80px rgba(27,215,255,0.6)';
      el.style.pointerEvents = 'none';
      el.style.transition = 'opacity 600ms ease';
      el.style.opacity = '1';
      stage.appendChild(el);
      setTimeout(() => el.style.opacity = '0', 40);
      setTimeout(() => el.remove(), 700);
    },
    sticker: () => {
      // random retro sticker
      const stickers = ['🛰️','💾','📟','📡','🧪','🎛️'];
      const el = document.createElement('div');
      el.textContent = stickers[Math.floor(Math.random()*stickers.length)];
      el.style.position = 'absolute';
      el.style.left = Math.round(Math.random() * (vw - 80) + 40) + 'px';
      el.style.top = Math.round(Math.random() * (vh - 80) + 40) + 'px';
      el.style.fontSize = (40 + Math.random()*24) + 'px';
      el.style.filter = 'drop-shadow(0 0 10px rgba(255,255,255,0.6))';
      el.style.transform = 'rotate(' + (Math.random()*30-15).toFixed(1) + 'deg)';
      el.style.cursor = 'pointer';
      stage.appendChild(el);
      el.addEventListener('click', () => el.remove());
      setTimeout(() => el.remove(), 12000);
    },
    bannerSwap: () => {
      // temporary banner swap
      if (!banner) return;
      const old = banner.textContent;
      banner.textContent = '★ 恭喜！你发现了隐藏彩蛋 · ULTRA RARE ★';
      setTimeout(() => { banner.textContent = old; }, 3600);
    }
  };
  if (gachaBtn) {
    gachaBtn.addEventListener('click', () => {
      const keys = Object.keys(surprises);
      const pick = keys[Math.floor(Math.random()*keys.length)];
      surprises[pick]();
    });
  }
})();

