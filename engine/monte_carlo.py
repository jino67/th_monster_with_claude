"""
Modèle D — Momentum Engine (remplace le Monte Carlo bruité)

Ancienne version : simulait 1000 séquences depuis le win_rate empirique des
20 dernières bougies. Sur RNG (win_rate ≈ 50%) → score toujours ~50 = bruit pur.

Nouvelle version : score de momentum multi-timeframe basé sur les EMA.
- EMA(9) vs EMA(21) : croisement directionnel par timeframe
- Pente EMA(9) sur 3 bougies : accélération du momentum
- Alignement M1/M5/M15 : bonus si les 3 timeframes sont en accord
- Résultat [0-100] avec direction exploitable

Cela fournit un vrai signal additionnel pour les Volatility indices (où les
streaks du modèle A sont proches de 50%) et un contexte de tendance cohérent
pour les autres actifs.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, Optional


class MonteCarloEngine:
    """
    Modèle D — Momentum multi-timeframe (EMA9/EMA21).
    Conserve le nom MonteCarloEngine pour compatibilité avec signal_fusion.py.
    """

    def __init__(self, symbol: str, n_simulations: int = 500):
        self.symbol = symbol
        # n_simulations conservé pour compatibilité mais non utilisé

    def _score_timeframe(self, df: Optional[pd.DataFrame]) -> tuple[float, int]:
        """
        Score [-100, +100] et direction pour un timeframe.
        Retourne (0, 0) si données insuffisantes.
        """
        if df is None or len(df) < 22:
            return 0.0, 0

        close = df['close']
        ema9  = close.ewm(span=9,  adjust=False).mean()
        ema21 = close.ewm(span=21, adjust=False).mean()

        e9   = float(ema9.iloc[-1])
        e21  = float(ema21.iloc[-1])
        direction = 1 if e9 > e21 else (-1 if e9 < e21 else 0)

        # Force = écart EMA9/EMA21 normalisé par ATR14
        atr = float((df['high'] - df['low']).tail(14).mean())
        if atr < 1e-10:
            return float(direction) * 30.0, direction

        gap      = abs(e9 - e21)
        strength = min(1.0, gap / atr)

        # Pente EMA9 : la tendance s'accélère-t-elle dans la bonne direction ?
        if len(ema9) >= 4:
            slope = float(ema9.iloc[-1] - ema9.iloc[-4])
            slope_aligned = (slope > 0 and direction == 1) or (slope < 0 and direction == -1)
        else:
            slope_aligned = True

        raw = direction * strength * (1.25 if slope_aligned else 0.75) * 100.0
        return max(-100.0, min(100.0, raw)), direction

    def compute(
        self,
        m1:  Optional[pd.DataFrame],
        m5:  Optional[pd.DataFrame] = None,
        m15: Optional[pd.DataFrame] = None,
    ) -> dict:
        """Score du modèle D [0-100] + direction dominante."""
        weights = {'M1': 0.50, 'M5': 0.35, 'M15': 0.15}
        composite = 0.0
        dirs = []

        for tf, df, w in [('M1', m1, 0.50), ('M5', m5, 0.35), ('M15', m15, 0.15)]:
            s, d = self._score_timeframe(df)
            composite += s * w
            dirs.append(d)

        # Bonus si les 3 timeframes sont alignés dans la même direction
        non_zero = [d for d in dirs if d != 0]
        if len(non_zero) >= 2 and len(set(non_zero)) == 1:
            composite *= 1.25

        score = round(min(100.0, max(0.0, 50.0 + composite / 2.0)), 1)
        dominant = 1 if composite > 5 else (-1 if composite < -5 else 0)

        return {
            'score':      score,
            'composite':  round(composite, 1),
            'direction':  dominant,
            'tf_dirs':    dirs,
        }

    # ── Rétrocompatibilité ────────────────────────────────────────────────────
    def simulate(self, candles: pd.DataFrame, horizon: int = 10) -> dict:
        """Alias legacy — redirige vers compute()."""
        result = self.compute(candles)
        return {
            'score':                result['score'],
            'prob_positive_pct':    result['score'],
            'expected_value':       0.0,
            'ci_5_95':              (0.0, 0.0),
            'win_rate_empirical':   50.0,
            'horizon':              horizon,
        }
