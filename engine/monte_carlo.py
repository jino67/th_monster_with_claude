"""
Modèle D — Monte Carlo Engine
Simule la distribution des prochains résultats basée sur les stats observées
Score de confiance probabiliste pour le signal composite
"""
import numpy as np
import pandas as pd
from typing import Dict, Tuple


class MonteCarloEngine:
    """Modèle D — Simulations Monte Carlo sur les statistiques de l'actif."""

    def __init__(self, symbol: str, n_simulations: int = 1000):
        self.symbol = symbol
        self.n_simulations = n_simulations

    def _compute_empirical_stats(self, candles: pd.DataFrame) -> Dict:
        """Calcule les statistiques empiriques sur les bougies récentes."""
        if candles is None or len(candles) < 20:
            return {'win_rate': 0.50, 'avg_up': 1.0, 'avg_down': 1.0}
        bodies = candles['close'] - candles['open']
        ups = bodies[bodies > 0]
        downs = bodies[bodies < 0]
        win_rate = len(ups) / max(1, len(ups) + len(downs))
        avg_up = float(ups.mean()) if len(ups) > 0 else 0.001
        avg_down = float(abs(downs.mean())) if len(downs) > 0 else 0.001
        return {'win_rate': win_rate, 'avg_up': avg_up, 'avg_down': avg_down}

    def simulate(self, candles: pd.DataFrame, horizon: int = 10) -> dict:
        """
        Simule `n_simulations` séquences de `horizon` bougies.
        Retourne la probabilité que le bilan soit positif sur cet horizon.
        """
        stats = self._compute_empirical_stats(candles)
        win_rate = stats['win_rate']
        avg_up = stats['avg_up']
        avg_down = stats['avg_down']

        rng = np.random.default_rng(seed=None)
        outcomes = rng.random((self.n_simulations, horizon))
        pnl_matrix = np.where(outcomes < win_rate, avg_up, -avg_down)
        session_pnl = pnl_matrix.sum(axis=1)

        prob_positive = float((session_pnl > 0).mean()) * 100.0
        expected_value = float(session_pnl.mean())
        confidence_interval = (
            float(np.percentile(session_pnl, 5)),
            float(np.percentile(session_pnl, 95)),
        )

        # Score [0-100] : probabilité d'être positif sur l'horizon
        score = min(100.0, max(0.0, prob_positive))

        return {
            'score': round(score, 1),
            'prob_positive_pct': round(prob_positive, 1),
            'expected_value': round(expected_value, 4),
            'ci_5_95': (round(confidence_interval[0], 4), round(confidence_interval[1], 4)),
            'win_rate_empirical': round(win_rate * 100, 1),
            'horizon': horizon,
        }

    def compute(self, m1: pd.DataFrame, m5: pd.DataFrame = None, m15: pd.DataFrame = None) -> dict:
        """Point d'entrée principal du modèle D."""
        return self.simulate(m1, horizon=10)
