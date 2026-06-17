"""
Modèle A — Streak Analyser
Analyse les séquences consécutives UP/DOWN sur Ticks, M1, M5, M15
Probabilités conditionnelles extraites des données historiques réelles (Bible v1.0)
"""
import numpy as np
import pandas as pd
from typing import Dict, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Probabilités conditionnelles réelles par actif (données empiriques Bible v1.0)
# cp_up[N]  = P(bougie suivante UP  | N bougies UP  consécutives)
# cp_down[N] = P(bougie suivante DOWN | N bougies DOWN consécutives)
# ─────────────────────────────────────────────────────────────────────────────
STREAK_STATS: Dict[str, Dict] = {
    'Volatility 100 Index': {
        'M1': {
            'cp_up':   {1: 50.1, 2: 51.2, 3: 45.7, 4: 41.3, 5: 64.4, 6: 39.5, 7: 50.0, 8: 28.6},
            'cp_down': {1: 50.8, 2: 50.3, 3: 46.9, 4: 50.0, 5: 50.7, 6: 41.7, 7: 66.7},
        },
        'M5': {
            'cp_up':   {1: 50.5, 2: 51.4, 3: 59.1, 4: 48.0, 5: 44.4, 6: 62.5},
            'cp_down': {1: 50.9, 2: 49.4, 3: 42.3, 4: 58.8, 5: 56.7, 6: 41.2},
        },
        'M15': {
            'cp_up':   {1: 50.3, 2: 50.1, 3: 49.8, 4: 48.5},
            'cp_down': {1: 49.7, 2: 50.2, 3: 50.1, 4: 51.5},
        },
    },
    'Volatility 100 (1s) Index': {
        'M1': {
            'cp_up':   {1: 52.3, 2: 47.9, 3: 53.2, 4: 48.5, 5: 62.0, 6: 49.0, 7: 58.3, 8: 14.3},
            'cp_down': {1: 50.1, 2: 49.8, 3: 50.5, 4: 47.1, 5: 45.4, 6: 37.3},
        },
        'M5': {
            'cp_up':   {1: 50.2, 2: 49.8, 3: 50.1, 4: 49.9, 5: 50.5},
            'cp_down': {1: 49.8, 2: 50.2, 3: 49.9, 4: 50.1, 5: 49.5},
        },
        'M15': {
            'cp_up':   {1: 50.3, 2: 50.1, 3: 49.8, 4: 48.5},
            'cp_down': {1: 49.7, 2: 50.2, 3: 50.1, 4: 51.5},
        },
    },
    'Crash 500 Index': {
        'M1': {
            'cp_up':   {1: 90.8, 2: 89.1, 3: 90.0, 4: 92.2, 5: 88.6, 6: 87.5, 7: 90.7, 8: 87.0, 9: 86.6, 10: 88.9},
            'cp_down': {1: 10.3, 2: 14.9, 3: 14.3, 4: 0.0},
        },
        'M5': {
            'cp_up':   {1: 67.7, 2: 65.5, 3: 64.0, 4: 62.5},
            'cp_down': {1: 32.3, 2: 30.5, 3: 28.0},
        },
        'M15': {
            'cp_up':   {1: 55.9, 2: 54.5, 3: 53.0},
            'cp_down': {1: 44.1, 2: 45.5, 3: 47.0},
        },
    },
    'Crash 1000 Index': {
        'M1': {
            'cp_up':   {1: 93.0, 2: 96.2, 3: 93.5, 4: 93.0, 5: 96.5, 6: 92.2, 7: 93.8, 8: 95.8, 9: 95.6, 10: 93.5},
            'cp_down': {1: 5.9, 2: 20.0, 3: 0.0},
        },
        'M5': {
            'cp_up':   {1: 78.4, 2: 76.0, 3: 74.0},
            'cp_down': {1: 21.6, 2: 24.0, 3: 26.0},
        },
        'M15': {
            'cp_up':   {1: 61.3, 2: 60.0, 3: 58.5},
            'cp_down': {1: 38.7, 2: 40.0, 3: 41.5},
        },
    },
    'Boom 500 Index': {
        'M1': {
            'cp_up':   {1: 10.4, 2: 10.2, 3: 0.0},
            'cp_down': {1: 91.9, 2: 90.5, 3: 89.5, 4: 88.3, 5: 89.0, 6: 90.2, 7: 88.7, 8: 87.3, 9: 95.8, 10: 87.5},
        },
        'M5': {
            'cp_up':   {1: 34.5, 2: 32.0, 3: 30.0},
            'cp_down': {1: 65.5, 2: 67.0, 3: 69.0},
        },
        'M15': {
            'cp_up':   {1: 42.2, 2: 41.0, 3: 39.5},
            'cp_down': {1: 57.8, 2: 59.0, 3: 60.5},
        },
    },
    'Boom 1000 Index': {
        'M1': {
            'cp_up':   {1: 7.8, 2: 4.8, 3: 0.0},
            'cp_down': {1: 94.4, 2: 92.7, 3: 91.8, 4: 90.6, 5: 92.1, 6: 94.9, 7: 90.5, 8: 92.1, 9: 96.4, 10: 91.3},
        },
        'M5': {
            'cp_up':   {1: 22.4, 2: 20.0, 3: 18.0},
            'cp_down': {1: 77.5, 2: 79.0, 3: 81.0},
        },
        'M15': {
            'cp_up':   {1: 40.5, 2: 39.0, 3: 37.5},
            'cp_down': {1: 59.6, 2: 61.0, 3: 62.5},
        },
    },
    'Step Index': {
        'M1': {
            'cp_up':   {1: 48.9, 2: 48.0, 3: 47.7, 4: 43.7, 5: 46.8, 6: 62.1, 7: 44.4, 8: 62.5},
            'cp_down': {1: 50.3, 2: 48.9, 3: 49.8, 4: 51.0, 5: 58.2, 6: 54.3, 7: 44.0},
        },
        'M5': {
            'cp_up':   {1: 50.1, 2: 50.0, 3: 49.9},
            'cp_down': {1: 49.9, 2: 50.0, 3: 50.1},
        },
        'M15': {
            'cp_up':   {1: 50.0, 2: 50.0, 3: 50.0},
            'cp_down': {1: 50.0, 2: 50.0, 3: 50.0},
        },
    },
    'Range Break 100 Index': {
        'M1': {
            'cp_up':   {1: 47.7, 2: 45.5, 3: 40.3, 4: 48.3, 5: 42.1, 6: 33.3, 7: 25.0},
            'cp_down': {1: 47.7, 2: 44.8, 3: 43.6, 4: 42.9, 5: 38.9, 6: 52.4, 7: 27.3},
        },
        'M5': {
            'cp_up':   {1: 50.6, 2: 49.5, 3: 48.5},
            'cp_down': {1: 49.3, 2: 50.5, 3: 51.5},
        },
        'M15': {
            'cp_up':   {1: 48.6, 2: 48.0, 3: 47.5},
            'cp_down': {1: 51.4, 2: 52.0, 3: 52.5},
        },
    },
}


def compute_streak(candles: pd.DataFrame) -> Tuple[int, int]:
    """
    Calcule le streak courant depuis les N dernières bougies.
    Retourne (streak_value, length) où streak_value > 0 = UP, < 0 = DOWN.
    """
    if candles is None or len(candles) < 2:
        return 0, 0
    bodies = (candles['close'] - candles['open']).values
    streak = 0
    for body in reversed(bodies):
        direction = 1 if body > 0 else (-1 if body < 0 else 0)
        if direction == 0:
            break
        if streak == 0:
            streak = direction
        elif (streak > 0 and direction > 0) or (streak < 0 and direction < 0):
            streak += direction
        else:
            break
    return streak, abs(streak)


class StreakAnalyser:
    """Modèle A — Analyse des streaks avec probabilités conditionnelles empiriques."""

    WEIGHTS = {'M1': 0.50, 'M5': 0.30, 'M15': 0.20}

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.stats = STREAK_STATS.get(symbol, {})

    def _get_continuation_prob(self, timeframe: str, streak_val: int) -> float:
        tf_stats = self.stats.get(timeframe, {})
        n = abs(streak_val)
        if streak_val > 0:
            return tf_stats.get('cp_up', {}).get(n, 50.0)
        elif streak_val < 0:
            return tf_stats.get('cp_down', {}).get(n, 50.0)
        return 50.0

    def compute(self, m1: pd.DataFrame, m5: pd.DataFrame, m15: pd.DataFrame) -> dict:
        """
        Calcule le score du modèle A [0-100] et la direction dominante.
        Retourne aussi les streaks détectés par timeframe.
        """
        results = {}
        composite_dir = 0.0
        composite_score = 0.0

        for tf, df in [('M1', m1), ('M5', m5), ('M15', m15)]:
            streak_val, n = compute_streak(df)
            prob = self._get_continuation_prob(tf, streak_val)
            direction = 1 if streak_val > 0 else (-1 if streak_val < 0 else 0)
            # [-100, +100] centré sur 0 = neutre
            raw = (prob - 50.0) * 2.0 * direction
            results[tf] = {
                'streak': streak_val,
                'n': n,
                'prob': prob,
                'raw_score': raw,
                'direction': direction,
            }
            w = self.WEIGHTS[tf]
            composite_score += raw * w
            composite_dir += direction * w

        # Bonus alignement
        directions = [results[tf]['direction'] for tf in ['M1', 'M5', 'M15']]
        aligned = sum(1 for d in directions if d == directions[0] and d != 0)
        if aligned == 3:
            composite_score *= 1.25
        elif aligned == 2:
            composite_score *= 1.10

        # Normaliser [0, 100]
        score = min(100.0, max(0.0, 50.0 + composite_score))
        dominant_dir = 1 if composite_dir > 0.1 else (-1 if composite_dir < -0.1 else 0)

        return {
            'score': round(score, 1),
            'direction': dominant_dir,
            'alignment': aligned,
            'streaks': {tf: results[tf]['streak'] for tf in results},
            'probs': {tf: results[tf]['prob'] for tf in results},
        }
