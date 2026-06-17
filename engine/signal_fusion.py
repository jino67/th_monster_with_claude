"""
Signal Fusion — Score composite des 5 modèles
Score = 0.30*A + 0.20*B + 0.20*C + 0.15*D + 0.15*E
  A = Streak Analyser (probabilités conditionnelles empiriques)
  B = Volatility Cycle Detector (ATR phases)
  C = Event Detector (spikes Crash/Boom)
  D = Monte Carlo Engine
  E = Legacy Adapter (anciens indicateurs : Price Action SMC, EMA, Regime)

Règles absolues : score < 40 → WAIT | < 3 modes alignés → mise réduite
(Bible v1.0 Section 12 & Formule 6 — étendu avec Modèle E)
"""
from __future__ import annotations
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional

from engine.streak_analyser import StreakAnalyser
from engine.volatility_detector import VolatilityCycleDetector
from engine.event_detector import EventDetector
from engine.monte_carlo import MonteCarloEngine
from engine.legacy_adapter import LegacyAdapter

# Pondérations des 5 modèles (somme = 1.00)
MODEL_WEIGHTS = {'A': 0.30, 'B': 0.20, 'C': 0.20, 'D': 0.15, 'E': 0.15}

# Règles absolues
MIN_SCORE_TO_TRADE = 40.0
MIN_ALIGNMENT = 3


@dataclass
class CompositeSignal:
    symbol: str
    action: str                # 'BUY' | 'SELL' | 'WAIT'
    score: float               # [0-100]
    direction: int             # +1 | -1 | 0
    confidence: str            # 'HIGH' | 'MEDIUM' | 'LOW'
    alignment: int             # nombre de modèles alignés (sur 5)
    score_A: float = 0.0
    score_B: float = 0.0
    score_C: float = 0.0
    score_D: float = 0.0
    score_E: float = 0.0       # Legacy adapter score
    details: dict = field(default_factory=dict)
    reduce_size: bool = False   # True si alignment < MIN_ALIGNMENT
    spike_alert: bool = False
    spike_alert_level: str = ''


class SignalFusion:
    """Fusionne les 5 modèles en un signal composite opérationnel."""

    def __init__(self, symbol: str, n_mc_simulations: int = 500, use_legacy: bool = True):
        self.symbol = symbol
        self.model_a = StreakAnalyser(symbol)
        self.model_b = VolatilityCycleDetector(symbol)
        self.model_c = EventDetector(symbol)
        self.model_d = MonteCarloEngine(symbol, n_simulations=n_mc_simulations)
        self.model_e = LegacyAdapter(symbol) if use_legacy else None

    def compute(
        self,
        m1: pd.DataFrame,
        m5: pd.DataFrame,
        m15: pd.DataFrame,
        h1: pd.DataFrame = None,
    ) -> CompositeSignal:
        # ── Calcul des 4 modèles stat ─────────────────────────────────────────
        res_a = self.model_a.compute(m1, m5, m15)
        res_b = self.model_b.compute(m1, m5, m15)
        res_c = self.model_c.compute(m1, m5, m15)
        res_d = self.model_d.compute(m1, m5, m15)

        sa = res_a['score']
        sb = res_b['score']
        sc = res_c['score']
        sd = res_d['score']

        # ── Modèle E — Legacy (Price Action, Regime, Indicateurs techniques) ──
        se = 50.0  # neutre par défaut
        res_e = {'score': 50.0, 'direction': 0, 'details': {}}
        if self.model_e is not None:
            try:
                res_e = self.model_e.compute(m1, m5, m15, h1)
                se = res_e['score']
            except Exception:
                pass  # Le modèle E ne bloque jamais le système

        # ── Score composite pondéré ───────────────────────────────────────────
        raw = (sa * MODEL_WEIGHTS['A'] + sb * MODEL_WEIGHTS['B'] +
               sc * MODEL_WEIGHTS['C'] + sd * MODEL_WEIGHTS['D'] +
               se * MODEL_WEIGHTS['E'])

        # Direction principale = consensus A + E (stat + technique)
        dir_a = res_a.get('direction', 0)
        dir_e = res_e.get('direction', 0)
        if dir_a != 0 and dir_e != 0:
            direction = dir_a if dir_a == dir_e else 0  # accord requis
        else:
            direction = dir_a or dir_e

        # Bonus alignement — compter les 5 modèles
        dirs = [dir_a, 0, 0, 0, dir_e]  # B/C/D sont non-directionnels
        aligned = sum(1 for d in [dir_a, dir_e] if d == direction and d != 0)
        # alignment sur les 3 timeframes du modèle A
        alignment_a = res_a.get('alignment', 1)
        total_alignment = alignment_a + (1 if dir_e == direction and direction != 0 else 0)

        if total_alignment >= 4:
            raw = min(100.0, raw * 1.20)
        elif total_alignment >= 3:
            raw = min(100.0, raw * 1.10)
        elif total_alignment >= 2:
            raw = min(100.0, raw * 1.05)

        score = round(raw, 1)

        # ── Règle absolue : score < 40 ou pas de direction → WAIT ────────────
        if score < MIN_SCORE_TO_TRADE or direction == 0:
            action = 'WAIT'
        else:
            action = 'BUY' if direction > 0 else 'SELL'

        # ── Confiance ────────────────────────────────────────────────────────
        if score >= 72:
            confidence = 'HIGH'
        elif score >= 56:
            confidence = 'MEDIUM'
        else:
            confidence = 'LOW'

        # ── Alerte spike ─────────────────────────────────────────────────────
        spike_alert = res_c.get('spike_detected', False)
        spike_alert_level = res_c.get('alert_level', '')

        return CompositeSignal(
            symbol=self.symbol,
            action=action,
            score=score,
            direction=direction,
            confidence=confidence,
            alignment=total_alignment,
            score_A=round(sa, 1),
            score_B=round(sb, 1),
            score_C=round(sc, 1),
            score_D=round(sd, 1),
            score_E=round(se, 1),
            details={
                'streak': res_a.get('streaks', {}),
                'probs': res_a.get('probs', {}),
                'volatility_phases': res_b.get('phases', {}),
                'atrs': res_b.get('atrs', {}),
                'event': res_c,
                'monte_carlo': res_d,
                'legacy': res_e.get('details', {}),
            },
            reduce_size=total_alignment < MIN_ALIGNMENT,
            spike_alert=spike_alert,
            spike_alert_level=spike_alert_level,
        )

    def to_dict(self, signal: CompositeSignal) -> dict:
        return {
            'symbol': signal.symbol,
            'action': signal.action,
            'score': signal.score,
            'direction': signal.direction,
            'confidence': signal.confidence,
            'alignment': signal.alignment,
            'scores': {
                'A': signal.score_A, 'B': signal.score_B,
                'C': signal.score_C, 'D': signal.score_D,
                'E': signal.score_E,
            },
            'reduce_size': signal.reduce_size,
            'spike_alert': signal.spike_alert,
            'spike_alert_level': signal.spike_alert_level,
            'details': signal.details,
        }
