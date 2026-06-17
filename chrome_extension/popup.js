/**
 * DTE Popup JS — logique du popup de l'extension
 */

'use strict';

const BACKEND = 'http://localhost:8000';
let currentSymbol = 'Volatility 100 Index';
let pollTimer = null;

// ── Utils ─────────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const setText = (id, val) => { const el = $(id); if (el) el.textContent = val; };
const setClass = (id, cls) => { const el = $(id); if (el) el.className = cls; };

// ── Fetch état backend ────────────────────────────────────────────────────────
async function fetchState() {
  try {
    const res = await fetch(`${BACKEND}/api/full_state`, { signal: AbortSignal.timeout(1500) });
    if (!res.ok) throw new Error('backend offline');
    const state = await res.json();
    renderState(state);
    setConnected(true);
  } catch {
    setConnected(false);
  }
}

// ── Rendu ─────────────────────────────────────────────────────────────────────
function renderState(state) {
  const sym  = currentSymbol;
  const sig  = (state.signals || {})[sym] || null;

  // Mode actif
  const mode = state.mode || 'SIGNAL_ONLY';
  document.querySelectorAll('.mode-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === mode);
  });

  // Stats session
  const ss = state.session_stats || {};
  setText('st-trades', ss.trades ?? 0);
  setText('st-wr', ss.win_rate ? ss.win_rate.toFixed(1) + '%' : '—%');
  const pnlEl = $('st-pnl');
  if (pnlEl) {
    const pnl = ss.pnl ?? 0;
    pnlEl.textContent = (pnl >= 0 ? '+' : '') + pnl.toFixed(2);
    pnlEl.className = 'stat-val ' + (pnl >= 0 ? 'pos' : 'neg');
  }

  setText('last-update', new Date().toLocaleTimeString());

  if (!sig) return;

  // Score
  setText('score', sig.score?.toFixed(1) ?? '--');

  // Badge action
  const ab = $('action-box');
  if (ab) {
    ab.className = 'action-box';
    const a = sig.action || 'WAIT';
    if (a === 'BUY')       { ab.className += ' buy';  ab.textContent = '▲ LONG'; }
    else if (a === 'SELL') { ab.className += ' sell'; ab.textContent = '▼ SHORT'; }
    else                   { ab.className += ' wait'; ab.textContent = '— ATTENDRE'; }
  }

  // Scores modèles
  const sc = sig.scores || {};
  setText('sc-a', sc.A?.toFixed(1) ?? '--');
  setText('sc-b', sc.B?.toFixed(1) ?? '--');
  setText('sc-c', sc.C?.toFixed(1) ?? '--');
  setText('sc-d', sc.D?.toFixed(1) ?? '--');
  setText('sc-e', sc.E?.toFixed(1) ?? '--');

  // Streaks
  const streaks = sig.details?.streak || {};
  renderStreak('str-m1',  streaks.M1);
  renderStreak('str-m5',  streaks.M5);
  renderStreak('str-m15', streaks.M15);

  // Spike alert
  const sp = $('spike-popup');
  if (sp) {
    if (sig.spike_alert) {
      sp.style.display = 'block';
      sp.textContent = `⚡ SPIKE ${sig.spike_alert_level} sur ${sym} !`;
    } else {
      sp.style.display = 'none';
    }
  }
}

function renderStreak(id, val) {
  const el = $(id);
  if (!el) return;
  const v = val ?? 0;
  el.textContent = (v > 0 ? '+' : '') + v;
  el.className = v > 0 ? 'up' : v < 0 ? 'down' : '';
}

function setConnected(ok) {
  const el = $('conn-status');
  if (!el) return;
  el.textContent = ok ? '● LIVE' : '○ Offline';
  el.className = 'status-pill' + (ok ? ' online' : '');
}

// ── Changement de symbole ─────────────────────────────────────────────────────
$('sym-select').addEventListener('change', async (e) => {
  currentSymbol = e.target.value;
  await fetch(`${BACKEND}/api/symbol`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol: currentSymbol }),
  }).catch(() => {});
  fetchState();
});

// ── Changement de mode ────────────────────────────────────────────────────────
document.querySelectorAll('.mode-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const mode = btn.dataset.mode;
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    await fetch(`${BACKEND}/api/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    }).catch(() => {});
  });
});

// ── Restaurer le symbole sauvegardé ──────────────────────────────────────────
chrome.storage.local.get(['dte_symbol'], (r) => {
  if (r.dte_symbol) {
    currentSymbol = r.dte_symbol;
    const sel = $('sym-select');
    if (sel) sel.value = currentSymbol;
  }
  fetchState();
  pollTimer = setInterval(fetchState, 2000);
});

// Sauvegarder le symbole à chaque changement
$('sym-select').addEventListener('change', (e) => {
  chrome.storage.local.set({ dte_symbol: e.target.value });
});
