/**
 * DTE Content Script — Overlay injecté sur deriv.com
 * Se connecte au backend local (localhost:8000) via polling REST + WebSocket
 */

'use strict';

const DTE_BACKEND  = 'http://localhost:8000';
const POLL_MS      = 1500;   // intervalle de polling
const WS_URL       = 'ws://localhost:8000/ws';

let pollTimer      = null;
let wsConn         = null;
let panelVisible   = true;
let isDragging     = false;
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
  const sym = state.active_symbol || '—';
  const signals = state.signals || {};
  const sig = signals[sym] || null;

  document.getElementById('dte-symbol').textContent = sym;
  document.getElementById('dte-mode-badge').textContent = state.mode || '—';
  document.getElementById('dte-time-label').textContent = new Date().toLocaleTimeString();

  if (!sig) return;

  const score = sig.score ?? 0;
  const action = sig.action || 'WAIT';

  // Score
  document.getElementById('dte-score-value').textContent = score.toFixed(1);

  // Badge action
  const badge = document.getElementById('dte-action-badge');
  badge.className = 'dte-action-badge';
  if (action === 'BUY')  { badge.className += ' buy';  badge.textContent = '▲ SIGNAL LONG'; }
  else if (action === 'SELL') { badge.className += ' sell'; badge.textContent = '▼ SIGNAL SHORT'; }
  else { badge.className += ' wait'; badge.textContent = '— ATTENDRE'; }

  // Scores modèles
  const scores = sig.scores || {};
  document.getElementById('dm-a').textContent = (scores.A ?? '--');
  document.getElementById('dm-b').textContent = (scores.B ?? '--');
  document.getElementById('dm-c').textContent = (scores.C ?? '--');
  document.getElementById('dm-d').textContent = (scores.D ?? '--');
  const dmE = document.getElementById('dm-e');
  if (dmE) dmE.textContent = (scores.E ?? '--');

  // Barres
  setBar('bar-a', 'bar-a-val', scores.A);
  setBar('bar-b', 'bar-b-val', scores.B);
  setBar('bar-c', 'bar-c-val', scores.C);

  // Streaks
  const streaks = sig.details?.streak || {};
  setStreak('str-m1',  streaks.M1);
  setStreak('str-m5',  streaks.M5);
  setStreak('str-m15', streaks.M15);

  // Alerte spike
  const spikeEl = document.getElementById('dte-spike-alert');
  if (sig.spike_alert) {
    spikeEl.style.display = 'block';
    spikeEl.textContent = `⚡ SPIKE ${sig.spike_alert_level} !`;
    if (sig.spike_alert_level === 'CRITIQUE') triggerNotification(sym, action);
  } else {
    spikeEl.style.display = 'none';
  }
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

// ── Connexion backend ─────────────────────────────────────────────────────────
function setConnected(ok) {
  const dot  = document.getElementById('dte-status-dot');
  const text = document.getElementById('dte-status-text');
  if (!dot) return;
  dot.className = ok ? 'connected' : '';
  text.textContent = ok ? 'LIVE' : 'Offline';
}

async function pollBackend() {
  try {
    const resp = await fetch(`${DTE_BACKEND}/api/full_state`, { signal: AbortSignal.timeout(1200) });
    if (resp.ok) {
      const data = await resp.json();
      updatePanel(data);
      setConnected(true);
    } else {
      setConnected(false);
    }
  } catch {
    setConnected(false);
  }
}

function startWebSocket() {
  if (wsConn && wsConn.readyState < 2) return;
  try {
    wsConn = new WebSocket(WS_URL);
    wsConn.onmessage = (e) => { try { updatePanel(JSON.parse(e.data)); setConnected(true); } catch {} };
    wsConn.onclose = () => setTimeout(startWebSocket, 5000);
    wsConn.onerror = () => setConnected(false);
  } catch {
    setTimeout(startWebSocket, 5000);
  }
}

// ── Notifications Chrome ──────────────────────────────────────────────────────
function triggerNotification(sym, action) {
  chrome.runtime.sendMessage({
    type: 'SPIKE_ALERT',
    symbol: sym,
    action: action,
  });
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
    panel.style.left   = (e.clientX - dragOffX) + 'px';
    panel.style.top    = (e.clientY - dragOffY) + 'px';
    panel.style.right  = 'auto';
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

// ── Init ──────────────────────────────────────────────────────────────────────
function init() {
  buildPanel();
  pollBackend();
  pollTimer = setInterval(pollBackend, POLL_MS);
  startWebSocket();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
