/**
 * DTE Content Script — Overlay injecté sur deriv.com
 * Les appels au backend local passent par le background service worker (proxy)
 * pour éviter les restrictions Chrome Private Network Access (PNA, Chrome 123+).
 */

'use strict';

const POLL_MS = 1500;

let pollTimer   = null;
let panelVisible = true;
let isDragging  = false;
let dragOffX = 0, dragOffY = 0;

// ── Création du panneau ───────────────────────────────────────────────────────
function buildPanel() {
  if (document.getElementById('dte-panel')) return;

  const panel = document.createElement('div');
  panel.id = 'dte-panel';
  panel.innerHTML = `
    <div id="dte-header">
      <span id="dte-logo">⬡ DTE v1.0</span>
      <span>
        <span id="dte-status-dot"></span>
        <span id="dte-status-text">Connecting…</span>
      </span>
    </div>
    <div id="dte-body">
      <div id="dte-symbol">—</div>
      <div id="dte-score-box">
        <div id="dte-score-value">--</div>
        <div id="dte-score-label">SCORE COMPOSITE / 100</div>
      </div>
      <div id="dte-action-badge" class="wait">ATTENDRE</div>
      <div id="dte-spike-alert">⚡ SPIKE IMMINENT !</div>
      <div class="dte-models-grid">
        <div class="dte-model-card"><div class="dte-model-name">A · Streaks</div><div class="dte-model-score" id="dm-a">--</div></div>
        <div class="dte-model-card"><div class="dte-model-name">B · Volatilité</div><div class="dte-model-score" id="dm-b">--</div></div>
        <div class="dte-model-card"><div class="dte-model-name">C · Événement</div><div class="dte-model-score" id="dm-c">--</div></div>
        <div class="dte-model-card"><div class="dte-model-name">D · Monte Carlo</div><div class="dte-model-score" id="dm-d">--</div></div>
        <div class="dte-model-card"><div class="dte-model-name">E · Legacy</div><div class="dte-model-score" id="dm-e">--</div></div>
      </div>
      <div class="dte-bar-row">
        <div class="dte-bar-label"><span>Score A</span><span id="bar-a-val">--</span></div>
        <div class="dte-bar-track"><div class="dte-bar-fill" id="bar-a" style="width:0%"></div></div>
      </div>
      <div class="dte-bar-row">
        <div class="dte-bar-label"><span>Score B</span><span id="bar-b-val">--</span></div>
        <div class="dte-bar-track"><div class="dte-bar-fill" id="bar-b" style="width:0%;background:#7c4dff"></div></div>
      </div>
      <div class="dte-bar-row">
        <div class="dte-bar-label"><span>Score C</span><span id="bar-c-val">--</span></div>
        <div class="dte-bar-track"><div class="dte-bar-fill" id="bar-c" style="width:0%;background:#ff8800"></div></div>
      </div>
      <div id="dte-streaks">
        M1: <span id="str-m1">--</span> &nbsp;
        M5: <span id="str-m5">--</span> &nbsp;
        M15: <span id="str-m15">--</span>
      </div>
    </div>
    <div id="dte-footer">
      <span id="dte-mode-badge">SIGNAL_ONLY</span>
      <span id="dte-time-label">--:--:--</span>
      <button id="dte-toggle-btn">Masquer</button>
    </div>
  `;
  document.body.appendChild(panel);
  initDrag(panel);
  document.getElementById('dte-toggle-btn').addEventListener('click', togglePanel);
}

// ── Mise à jour de l'UI ───────────────────────────────────────────────────────
function updatePanel(state) {
  const sym    = state.active_symbol || '—';
  const signals = state.signals || {};
  const sig    = signals[sym] || null;

  document.getElementById('dte-symbol').textContent    = sym;
  document.getElementById('dte-mode-badge').textContent = state.mode || '—';
  document.getElementById('dte-time-label').textContent = new Date().toLocaleTimeString();

  if (!sig) return;

  const score  = sig.score ?? 0;
  const action = sig.action || 'WAIT';

  document.getElementById('dte-score-value').textContent = score.toFixed(1);

  const badge = document.getElementById('dte-action-badge');
  badge.className = 'dte-action-badge';
  if (action === 'BUY')       { badge.className += ' buy';  badge.textContent = '▲ SIGNAL LONG'; }
  else if (action === 'SELL') { badge.className += ' sell'; badge.textContent = '▼ SIGNAL SHORT'; }
  else                        { badge.className += ' wait'; badge.textContent = '— ATTENDRE'; }

  const scores = sig.scores || {};
  document.getElementById('dm-a').textContent = (scores.A ?? '--');
  document.getElementById('dm-b').textContent = (scores.B ?? '--');
  document.getElementById('dm-c').textContent = (scores.C ?? '--');
  document.getElementById('dm-d').textContent = (scores.D ?? '--');
  const dmE = document.getElementById('dm-e');
  if (dmE) dmE.textContent = (scores.E ?? '--');

  setBar('bar-a', 'bar-a-val', scores.A);
  setBar('bar-b', 'bar-b-val', scores.B);
  setBar('bar-c', 'bar-c-val', scores.C);

  const streaks = sig.details?.streak || {};
  setStreak('str-m1',  streaks.M1);
  setStreak('str-m5',  streaks.M5);
  setStreak('str-m15', streaks.M15);

  const spikeEl = document.getElementById('dte-spike-alert');
  if (sig.spike_alert) {
    spikeEl.style.display = 'block';
    spikeEl.textContent = `⚡ SPIKE ${sig.spike_alert_level} !`;
    if (sig.spike_alert_level === 'CRITIQUE') triggerNotification(sym, action);
  } else {
    spikeEl.style.display = 'none';
  }

  // Projection chartographique
  Projector.update(state);
}

function setBar(barId, valId, value) {
  const v = parseFloat(value) || 0;
  document.getElementById(barId).style.width = Math.min(100, v) + '%';
  document.getElementById(valId).textContent = v.toFixed(1);
}

function setStreak(elId, val) {
  const el = document.getElementById(elId);
  if (!el) return;
  const v = val ?? 0;
  el.textContent = (v > 0 ? '+' : '') + v;
  el.className = v > 0 ? 'streak-up' : v < 0 ? 'streak-down' : '';
}

// ── Connexion backend — via background SW (bypass PNA) ───────────────────────
function setConnected(ok) {
  const dot  = document.getElementById('dte-status-dot');
  const text = document.getElementById('dte-status-text');
  if (!dot) return;
  dot.className    = ok ? 'connected' : '';
  text.textContent = ok ? 'LIVE' : 'Offline';
}

async function pollBackend() {
  try {
    // Le fetch passe par le background service worker qui a les host_permissions
    // et n'est pas soumis aux restrictions Private Network Access.
    const resp = await chrome.runtime.sendMessage({
      type: 'FETCH_BACKEND',
      path: '/api/full_state',
    });
    if (resp?.ok) {
      updatePanel(resp.data);
      setConnected(true);
    } else {
      setConnected(false);
    }
  } catch {
    setConnected(false);
  }
}

// ── Notifications Chrome ──────────────────────────────────────────────────────
function triggerNotification(sym, action) {
  chrome.runtime.sendMessage({ type: 'SPIKE_ALERT', symbol: sym, action });
}

// ── Drag & Drop du panneau ────────────────────────────────────────────────────
function initDrag(panel) {
  const header = document.getElementById('dte-header');
  header.addEventListener('mousedown', (e) => {
    isDragging = true;
    const rect = panel.getBoundingClientRect();
    dragOffX = e.clientX - rect.left;
    dragOffY = e.clientY - rect.top;
  });
  document.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    panel.style.left  = (e.clientX - dragOffX) + 'px';
    panel.style.top   = (e.clientY - dragOffY) + 'px';
    panel.style.right = 'auto';
  });
  document.addEventListener('mouseup', () => { isDragging = false; });
}

function togglePanel() {
  panelVisible = !panelVisible;
  const body = document.getElementById('dte-body');
  const btn  = document.getElementById('dte-toggle-btn');
  body.style.display = panelVisible ? 'block' : 'none';
  btn.textContent    = panelVisible ? 'Masquer' : 'Afficher';
}

// ── Projection de bougies sur le graphique ────────────────────────────────────
// Dessine des bougies projetées et les lignes SL/TP en overlay transparent
// sur le canvas principal du graphique Deriv (SmartCharts/TradingView).
// L'overlay est positionné en fixed au-dessus du canvas, pointer-events:none.

const SYMBOL_POINT = {
  'Volatility 100 Index':      0.01,
  'Volatility 100 (1s) Index': 0.01,
  'Crash 500 Index':           0.001,
  'Crash 1000 Index':          0.0001,
  'Boom 500 Index':            0.001,
  'Boom 1000 Index':           0.0001,
  'Step Index':                0.01,
  'Range Break 100 Index':     0.01,
};

const Projector = (() => {
  let overlay  = null;  // canvas overlay
  let chartEl  = null;  // canvas du graphique Deriv
  let mutObs   = null;  // MutationObserver d'attente init
  let resObs   = null;  // ResizeObserver pour sync taille
  let lastSeed = -1;
  let cachedProj = null;
  const N_PROJ = 10;    // nombre de bougies projetées

  // Trouve le plus grand canvas présent → graphique principal
  function findMainCanvas() {
    return [...document.querySelectorAll('canvas')]
      .filter(c => c.width > 300 && c.height > 150)
      .sort((a, b) => b.width * b.height - a.width * a.height)[0] ?? null;
  }

  function createOverlay() {
    const ov = document.createElement('canvas');
    ov.id = 'dte-proj-overlay';
    ov.style.cssText = 'position:fixed;pointer-events:none;z-index:9990;';
    document.body.appendChild(ov);
    return ov;
  }

  // Aligne le canvas overlay sur le canvas du graphique
  function sync() {
    if (!overlay || !chartEl?.isConnected) return;
    const r = chartEl.getBoundingClientRect();
    overlay.style.left   = r.left   + 'px';
    overlay.style.top    = r.top    + 'px';
    overlay.style.width  = r.width  + 'px';
    overlay.style.height = r.height + 'px';
    overlay.width  = Math.round(r.width)  || 1;
    overlay.height = Math.round(r.height) || 1;
  }

  // Lit les labels numériques du côté droit du canvas → calibre prix→pixel Y
  // Retourne une fonction priceToY(price) → Y relatif au canvas, ou null si échec.
  function readPriceAxis() {
    if (!chartEl) return null;
    const cr = chartEl.getBoundingClientRect();
    if (!cr.width) return null;
    const xMin = cr.right - cr.width * 0.18; // zone axe prix (18% droite)

    const pts = [];
    const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = tw.nextNode())) {
      const raw = (node.nodeValue ?? '').trim();
      // Format prix : 3-10 chiffres, décimales optionnelles
      if (!/^\d{2,10}(\.\d{1,8})?$/.test(raw)) continue;
      const p = parseFloat(raw);
      if (!p || p <= 0) continue;
      const el = node.parentElement;
      if (!el) continue;
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      const mx = (r.left  + r.right)  / 2;
      const my = (r.top   + r.bottom) / 2;
      if (mx < xMin)              continue; // pas dans la zone axe
      if (my <= cr.top + 8 || my >= cr.bottom - 8) continue; // hors graphique
      pts.push({ p, y: my - cr.top });
    }

    if (pts.length < 2) return null;

    // Déduplique par prix
    const seen = new Map();
    pts.forEach(x => { if (!seen.has(x.p)) seen.set(x.p, x.y); });
    const arr = [...seen.entries()]
      .map(([p, y]) => ({ p, y }))
      .sort((a, b) => b.p - a.p); // descending price

    if (arr.length < 2) return null;
    const hi = arr[0];
    const lo = arr[arr.length - 1];
    if (hi.p === lo.p || lo.y <= hi.y) return null; // axe invalide

    const dp = hi.p - lo.p;
    const dy = lo.y - hi.y;
    return price => hi.y + (hi.p - price) / dp * dy;
  }

  // Générateur pseudo-aléatoire déterministe (LCG) — même seed = mêmes bougies
  function lcg(seed) {
    let s = (seed >>> 0) || 1;
    return () => { s = (Math.imul(1664525, s) + 1013904223) >>> 0; return s / 0xffffffff; };
  }

  // Génère N bougies projetées à partir de startPrice dans la direction direction
  function generateProjection(startPrice, direction, atr) {
    // Seed stable pendant 5 minutes pour éviter les candles qui dansent
    const bucket  = Math.floor(Date.now() / 300000);
    const seed = Math.abs(((bucket * 999983) ^ (startPrice * 100 | 0)) >>> 0);
    if (seed === lastSeed && cachedProj) return cachedProj;
    lastSeed = seed;

    const rng  = lcg(seed);
    const bias = direction === 'BUY' ? 0.55 : direction === 'SELL' ? -0.55 : 0;
    let px = startPrice;
    const out = [];
    for (let i = 0; i < N_PROJ; i++) {
      const move = (bias + (rng() - 0.5) * 1.2) * atr * 0.65;
      const wick = rng() * atr * 0.25;
      const open = px, close = px + move;
      out.push({ open, close, high: Math.max(open, close) + wick, low: Math.min(open, close) - wick });
      px = close;
    }
    cachedProj = out;
    return out;
  }

  // Trace une ligne horizontale sur le canvas avec label (SL/TP)
  function drawHLine(ctx, y, x0, x1, color, label) {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.3;
    ctx.setLineDash([7, 4]);
    ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke();
    ctx.setLineDash([]);
    if (label) {
      ctx.font = 'bold 10px monospace';
      const tw = ctx.measureText(label).width;
      ctx.fillStyle = 'rgba(0,0,0,0.6)';
      ctx.fillRect(x1 - tw - 6, y - 12, tw + 4, 13);
      ctx.fillStyle = color;
      ctx.fillText(label, x1 - tw - 4, y - 1);
    }
    ctx.restore();
  }

  function draw(state) {
    if (!overlay) return;
    const ctx = overlay.getContext('2d');
    const W = overlay.width, H = overlay.height;
    ctx.clearRect(0, 0, W, H);
    if (!W || !H) return;

    const sym = state.active_symbol;
    const sig = state.signals?.[sym];
    if (!sym || !sig) return;

    // Calibrage prix → Y pixel depuis les labels de l'axe prix du graphique
    const priceToY = readPriceAxis();
    if (!priceToY) return; // impossible de calibrer — on dessine rien

    const action = sig.action;

    // Position ouverte sur ce symbole → prix courant, SL, TP
    const pos       = (state.positions ?? []).find(p => p.symbol === sym);
    const curPrice  = pos?.price_current ?? sig.current_price ?? 0;
    const sl        = pos?.sl ?? 0;
    const tp        = pos?.tp ?? 0;

    if (curPrice <= 0) return;

    // ── Ligne prix courant ────────────────────────────────────────────────────
    const yCur = priceToY(curPrice);
    if (yCur > 5 && yCur < H - 5) {
      ctx.save();
      ctx.strokeStyle = 'rgba(255,255,255,0.35)';
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 6]);
      ctx.beginPath(); ctx.moveTo(0, yCur); ctx.lineTo(W, yCur); ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();
    }

    // ── Ligne SL ─────────────────────────────────────────────────────────────
    if (sl > 0) {
      const ySL = priceToY(sl);
      if (ySL > 5 && ySL < H - 5) drawHLine(ctx, ySL, 0, W, 'rgba(255,75,55,0.85)', 'SL');
    }

    // ── Ligne TP ─────────────────────────────────────────────────────────────
    if (tp > 0) {
      const yTP = priceToY(tp);
      if (yTP > 5 && yTP < H - 5) drawHLine(ctx, yTP, 0, W, 'rgba(50,215,120,0.85)', 'TP');
    }

    if (action === 'WAIT') return; // pas de bougies projetées en WAIT

    // ── Bougies projetées ─────────────────────────────────────────────────────
    const pt  = sig.point_size ?? SYMBOL_POINT[sym] ?? 0.01;
    const atr = sig.atr_price  ?? (5 * pt);
    const candles = generateProjection(curPrice, action, atr);

    const FRAC  = 0.22;                    // 22% droite du canvas
    const x0    = W * (1 - FRAC);
    const slotW = W * FRAC / N_PROJ;
    const bdW   = slotW * 0.58;

    // Trait séparateur "maintenant | futur"
    ctx.save();
    ctx.strokeStyle = 'rgba(255,230,60,0.28)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 6]);
    ctx.beginPath(); ctx.moveTo(x0, 20); ctx.lineTo(x0, H - 20); ctx.stroke();
    ctx.setLineDash([]);

    // Etiquette direction
    const lbl = action === 'BUY' ? '▲ DTE proj.' : '▼ DTE proj.';
    ctx.font = 'bold 9px monospace';
    ctx.fillStyle = action === 'BUY' ? 'rgba(0,220,120,0.70)' : 'rgba(255,80,60,0.70)';
    ctx.fillText(lbl, x0 + 3, 15);
    ctx.restore();

    candles.forEach((c, i) => {
      const cx   = x0 + (i + 0.5) * slotW;
      const bull = c.close >= c.open;
      const col  = bull ? 'rgba(0,210,115,0.55)' : 'rgba(255,68,55,0.55)';

      const yH = priceToY(c.high);
      const yL = priceToY(c.low);
      const yO = priceToY(c.open);
      const yC = priceToY(c.close);

      // Skip si hors canvas
      if (Math.min(yH, yL, yO, yC) > H || Math.max(yH, yL, yO, yC) < 0) return;

      const yTop = Math.min(yO, yC);
      const yBot = Math.max(yO, yC);

      ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 1;

      // Mèche
      ctx.beginPath(); ctx.moveTo(cx, Math.max(0, yH)); ctx.lineTo(cx, Math.min(H, yL)); ctx.stroke();
      // Corps
      ctx.fillRect(cx - bdW / 2, yTop, bdW, Math.max(1, yBot - yTop));
    });
  }

  function attach(canvas) {
    if (overlay) overlay.remove();
    if (resObs) resObs.disconnect();

    overlay = createOverlay();
    chartEl = canvas;
    sync();

    resObs = new ResizeObserver(sync);
    resObs.observe(canvas);
    window.addEventListener('resize', sync, { passive: true });
    window.addEventListener('scroll', sync, { passive: true });
  }

  return {
    init() {
      const c = findMainCanvas();
      if (c) { attach(c); return; }
      // Attend que le graphique Deriv soit chargé dans le DOM
      mutObs = new MutationObserver(() => {
        const c2 = findMainCanvas();
        if (c2) { mutObs.disconnect(); mutObs = null; attach(c2); }
      });
      mutObs.observe(document.body, { childList: true, subtree: true });
    },

    update(state) {
      // Si le canvas a disparu (navigation), on tente de le retrouver
      if (!chartEl?.isConnected) {
        const c = findMainCanvas();
        if (c) attach(c); else return;
      }
      sync();
      draw(state);
    },
  };
})();

// ── Init ──────────────────────────────────────────────────────────────────────
function init() {
  buildPanel();
  Projector.init();
  pollBackend();
  pollTimer = setInterval(pollBackend, POLL_MS);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
