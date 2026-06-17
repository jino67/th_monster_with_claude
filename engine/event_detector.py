"""
Modèle C — Event Detector (Spike/Range Break)
Détecte les spikes sur Crash/Boom via analyse de prix MT5
Loi exponentielle calibrée sur données réelles (Bible v1.0 Section 6.3)
"""
import math
import pandas as pd
import numpy as np
from typing import Optional

# Statistiques des spikes calibrées depuis les données historiques (Bible v1.0)
# avg_interval : intervalle moyen en ticks entre deux spikes
# avg_amp      : amplitude moyenne du spike en points/pips
# direction    : +1 spike haussier (BOOM), -1 spike baissier (CRASH)
# detection_threshold : saut de prix minimum pour détecter un spike (en points)
SPIKE_STATS = {
    'Crash 500 Index':  {'avg_interval': 747,  'avg_amp': 4.88,  'direction': -1, 'threshold_pts': 0.8},
    'Crash 1000 Index': {'avg_interval': 5000, 'avg_amp': 6.33,  'direction': -1, 'threshold_pts': 0.5},
    'Boom 500 Index':   {'avg_interval': 449,  'avg_amp': 6.48,  'direction': +1, 'threshold_pts': 0.8},
    'Boom 1000 Index':  {'avg_interval': 697,  'avg_amp': 14.72, 'direction': +1, 'threshold_pts': 1.2},
}

# Limites max des streaks M1 (pour alertes sur actifs directionnels)
MAX_STREAKS = {
    'Crash 500 Index':  {'max_up': 54,  'max_down': 4},
    'Crash 1000 Index': {'max_up': 131, 'max_down': 3},
    'Boom 500 Index':   {'max_up': 3,   'max_down': 50},
    'Boom 1000 Index':  {'max_up': 3,   'max_down': 94},
}


class EventDetector:
    """Modèle C — Détection des événements spéciaux (spikes, range breaks)."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.stats = SPIKE_STATS.get(symbol, {})
        self.ticks_since_last_spike = 0
        self.spike_count_session = 0
        self.last_spike_amplitude = 0.0
        self._has_spike_tracking = bool(self.stats)

    def cumulative_spike_probability(self, n_ticks: int) -> float:
        """P(spike ≤ N ticks) depuis dernier spike — loi exponentielle."""
        if not self.stats:
            return 0.0
        lam = self.stats['avg_interval']
        return (1 - math.exp(-n_ticks / lam)) * 100.0

    def detect_spike_from_candles(self, m1: pd.DataFrame) -> bool:
        """
        Détecte un spike récent depuis les bougies M1.
        Un spike = bougie avec range >> ATR moyen dans la direction attendue.
        """
        if m1 is None or len(m1) < 10 or not self.stats:
            return False
        last = m1.iloc[-1]
        avg_range = (m1['high'] - m1['low']).tail(20).mean()
        candle_range = last['high'] - last['low']
        body = last['close'] - last['open']
        threshold = self.stats['threshold_pts']
        direction = self.stats['direction']
        # Spike CRASH = grand range + body négatif
        if direction == -1:
            return candle_range > avg_range * 3 and body < -threshold
        # Spike BOOM = grand range + body positif
        return candle_range > avg_range * 3 and body > threshold

    def update_from_candles(self, m1: pd.DataFrame) -> dict:
        """Met à jour le compteur de ticks et retourne l'état courant."""
        spike_detected = self.detect_spike_from_candles(m1)
        ticks_equiv = max(1, len(m1)) if m1 is not None else 1
        self.ticks_since_last_spike += ticks_equiv
        if spike_detected:
            self.spike_count_session += 1
            if m1 is not None and len(m1) > 0:
                last = m1.iloc[-1]
                self.last_spike_amplitude = last['high'] - last['low']
            self.ticks_since_last_spike = 0

        prob = self.cumulative_spike_probability(self.ticks_since_last_spike)
        return self._build_result(spike_detected, prob)

    def _build_result(self, spike_detected: bool, prob: float) -> dict:
        if prob >= 80:
            alert = 'CRITIQUE'
        elif prob >= 60:
            alert = 'HAUTE'
        elif prob >= 40:
            alert = 'MOYENNE'
        else:
            alert = 'FAIBLE'

        # Score = imminence du prochain événement pour les Crash/Boom
        # Pour les autres actifs, score neutre = 50
        score = min(90.0, prob) if self._has_spike_tracking else 50.0

        return {
            'score': round(score, 1),
            'spike_detected': spike_detected,
            'ticks_since_spike': self.ticks_since_last_spike,
            'prob_spike_imminent': round(prob, 1),
            'alert_level': alert,
            'spike_count_session': self.spike_count_session,
            'has_spike_tracking': self._has_spike_tracking,
        }

    def compute(self, m1: pd.DataFrame, m5: pd.DataFrame = None, m15: pd.DataFrame = None) -> dict:
        """Point d'entrée principal du modèle C."""
        return self.update_from_candles(m1)
