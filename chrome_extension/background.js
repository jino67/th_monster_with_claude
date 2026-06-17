/**
 * DTE Background Service Worker
 * Gère les notifications et les alarmes de polling
 */

'use strict';

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'SPIKE_ALERT') {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: `⚡ DTE — Spike détecté sur ${msg.symbol}`,
      message: `Signal ${msg.action} — Spike imminent critique !`,
      priority: 2,
    });
    sendResponse({ received: true });
  }
  return true;
});

// Réveil périodique pour garder le SW actif
chrome.alarms.create('dte-keepalive', { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'dte-keepalive') {
    // ping le backend pour vérifier la connexion
    fetch('http://localhost:8000/api/status').catch(() => {});
  }
});
