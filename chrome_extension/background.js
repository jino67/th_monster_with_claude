/**
 * DTE Background Service Worker
 * Proxy pour les appels au backend local — le SW a les host_permissions et
 * n'est PAS soumis aux restrictions PNA de Chrome (contrairement au content script
 * qui s'exécute dans le contexte de deriv.com, une page publique HTTPS).
 */

'use strict';

const BACKEND = 'http://localhost:8000';

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {

  // ── Proxy fetch backend ────────────────────────────────────────────────────
  if (msg.type === 'FETCH_BACKEND') {
    fetch(`${BACKEND}${msg.path}`, { signal: AbortSignal.timeout(1500) })
      .then(r => r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`))
      .then(data => sendResponse({ ok: true, data }))
      .catch(err  => sendResponse({ ok: false, error: String(err) }));
    return true; // réponse asynchrone obligatoire
  }

  // ── Notification spike ─────────────────────────────────────────────────────
  if (msg.type === 'SPIKE_ALERT') {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: `⚡ DTE — Spike détecté sur ${msg.symbol}`,
      message: `Signal ${msg.action} — Spike imminent critique !`,
      priority: 2,
    });
    sendResponse({ received: true });
    return true;
  }

  return true;
});

// Keepalive — évite que le SW soit suspendu pendant les sessions de trading
chrome.alarms.create('dte-keepalive', { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'dte-keepalive') {
    fetch(`${BACKEND}/api/status`).catch(() => {});
  }
});
