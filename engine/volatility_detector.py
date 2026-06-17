"""
Modèle B — Volatility Cycle Detector
Détecte les phases de compression/expansion/transition basées sur l'ATR
Seuils calibrés par actif depuis les données historiques réelles (Bible v1.0)
"""
import pandas as pd
import numpy as np
from typing import Dict, Tuple

# Seuils ATR par actif et timeframe (Bible v1.0 Section 6.2)
ATR_THRESHOLDS: Dict[str, Dict] = {
    'Volatility 100 Index': {
        'M1': {'comp': 0.45, 'exp': 0.85},
        'M5': {'comp': 1.20, 'exp': 2.00},
        'M15': {'comp': 2.10, 'exp': 3.60},
    },
    'Volatility 100 (1s) Index': {
        'M1': {'comp': 1.00, 'exp': 2.00},
        'M5': {'comp': 2.50, 'exp': 4.50},
        'M15': {'comp': 4.50, 'exp': 8.50},
    },
    'Crash 500 Index': {
        'M1': {'comp': 0.45, 'exp': 0.85},
        'M5': {'comp': 2.00, 'exp': 3.50},
        'M15': {'comp': 4.00, 'exp': 8.00},
    },
    'Crash 1000 Index': {
        'M1': {'comp': 0.45, 'exp': 0.85},
        'M5': {'comp': 2.00, 'exp': 4.00},
        'M15': {'comp': 4.50, 'exp': 9.00},
    },
    'Boom 500 Index': {
        'M1': {'comp': 0.80, 'exp': 1.60},
        'M5': {'comp': 3.50, 'exp': 6.00},
        'M15': {'comp': 7.00, 'exp': 13.00},
    },
    'Boom 1000 Index': {
        'M1': {'comp': 1.15, 'exp': 2.30},
        'M5': {'comp': 5.00, 'exp': 9.00},
        'M15': {'comp': 12.00, 'exp': 22.00},
    },
    'Step Index': {
        'M1': {'comp': 0.80, 'exp': 1.40},
        'M5': {'comp': 2.00, 'exp': 3.50},
        'M15': {'comp': 3.50, 'exp': 5.50},
    },
    'Range Break 100 Index': {
        'M1': {'comp': 8.00, 'exp': 16.00},
        'M5': {'comp': 20.00, 'exp': 40.00},
        'M15': {'comp': 35.00, 'exp': 65.00},
    },
}

PHASE_SCORES = {
    'expansion':   75.0,
    'transition':  50.0,
    'compression': 25.0,
}

PHASE_WEIGHTS = {'M1': 0.50, 'M5': 0.35, 'M15': 0.15}


def calculate_atr(df: pd.DataFrame, window: int = 14) -> float:
    """ATR adapté aux synthétiques RNG (pas de gap overnight)."""
    if df is None or len(df) < 2:
        return 0.0
    recent = df.tail(window)
    return float((recent['high'] - recent['low']).mean())


def classify_phase(atr: float, symbol: str, timeframe: str) -> str:
    thresholds = ATR_THRESHOLDS.get(symbol, {}).get(timeframe, {})
    if not thresholds:
        return 'transition'
    if atr < thresholds['comp']:
        return 'compression'
    elif atr > thresholds['exp']:
        return 'expansion'
    return 'transition'


class VolatilityCycleDetector:
    """Modèle B — Détection des phases de volatilité par timeframe."""

    def __init__(self, symbol: str, window: int = 14):
        self.symbol = symbol
        self.window = window

    def compute(self, m1: pd.DataFrame, m5: pd.DataFrame, m15: pd.DataFrame) -> dict:
        """Score du modèle B [0-100]. Expansion = favorable, compression = attendre."""
        results = {}
        composite = 0.0

        for tf, df in [('M1', m1), ('M5', m5), ('M15', m15)]:
            atr = calculate_atr(df, self.window)
            phase = classify_phase(atr, self.symbol, tf)
            score = PHASE_SCORES[phase]
            results[tf] = {'atr': round(atr, 4), 'phase': phase, 'score': score}
            composite += score * PHASE_WEIGHTS[tf]

        return {
            'score': round(composite, 1),
            'phases': {tf: results[tf]['phase'] for tf in results},
            'atrs': {tf: results[tf]['atr'] for tf in results},
        }
