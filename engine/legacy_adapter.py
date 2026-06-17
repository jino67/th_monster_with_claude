"""
Modèle E — Legacy Adapter
Intègre les signaux de l'ancien écosystème (strategies/ + core/) dans le score composite DTE.

Ce module fait le pont entre :
  - CrashBoomStrategy (Price Action SMC, FVG, Structure H1)
  - VolatilityStrategy (EMA, ATR, structure multi-TF)
  - MarketRegimeDetector (régime trending/ranging/volatile)

et le score composite [0-100] attendu par signal_fusion.py.
"""
from __future__ import annotations
import logging
import pandas as pd
import numpy as np
from typing import Optional, Dict

logger = logging.getLogger('dte.legacy_adapter')

# Mapping symbol MT5 → type de stratégie legacy
_CRASH_BOOM_SYMBOLS = {
    'Crash 500 Index', 'Crash 1000 Index',
    'Boom 500 Index', 'Boom 1000 Index',
}
_VOLATILITY_SYMBOLS = {
    'Volatility 100 Index', 'Volatility 100 (1s) Index',
    'Step Index', 'Range Break 100 Index',
}

# Multiplicateurs de régime (depuis config/market_regimes_config.json)
_REGIME_MULTIPLIERS = {
    'TRENDING_MARKET': 1.10,
    'VOLATILE_MARKET': 0.75,
    'RANGING_MARKET':  0.85,
    'NEUTRAL_MARKET':  0.90,
    'MIXED_MARKET':    0.65,
}


def _load_strategy(symbol: str):
    """
    Charge dynamiquement la bonne stratégie legacy.
    Import tardif pour éviter les erreurs si l'ancien code a des dépendances manquantes.
    """
    import sys, os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        if symbol in _CRASH_BOOM_SYMBOLS:
            from strategies.crash_boom_strategy import CrashBoomStrategy
            return CrashBoomStrategy(), 'crash_boom'
        elif symbol in _VOLATILITY_SYMBOLS:
            from strategies.top_volatility_strategy import VolatilityStrategy
            return VolatilityStrategy(), 'volatility'
        else:
            return None, None
    except ImportError as e:
        logger.warning(f'Import stratégie legacy échoué: {e}')
        return None, None


def _load_regime_detector():
    try:
        from core.market_regime_detector import MarketRegimeDetector
        return MarketRegimeDetector()
    except ImportError:
        return None


def _action_to_direction(action: str) -> int:
    a = (action or '').upper()
    if a in ('BUY', 'LONG'):  return 1
    if a in ('SELL', 'SHORT'): return -1
    return 0


def _confidence_to_score(confidence: float, direction: int) -> float:
    """
    Convertit confidence [0.0-1.0] + direction → score [0-100].
    confidence=1.0 direction=+1 → 100 (fort signal long)
    confidence=0.0 → 50 (neutre)
    """
    c = max(0.0, min(1.0, float(confidence)))
    return 50.0 + direction * c * 50.0


class LegacyAdapter:
    """
    Modèle E — Adapte les stratégies legacy vers un score DTE [0-100].

    Ce modèle est isolé des 4 modèles stat pour ne pas les contaminer :
    si l'ancien code plante, le score E = 50 (neutre) sans bloquer le système.
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self._strategy = None
        self._strategy_type = None
        self._regime_detector = None
        self._initialized = False

    def _lazy_init(self):
        if self._initialized:
            return
        self._strategy, self._strategy_type = _load_strategy(self.symbol)
        self._regime_detector = _load_regime_detector()
        self._initialized = True

    def compute(
        self,
        m1: pd.DataFrame,
        m5: pd.DataFrame,
        m15: pd.DataFrame,
        h1: Optional[pd.DataFrame] = None,
    ) -> dict:
        """
        Calcule le score du Modèle E [0-100].
        Retourne 50 (neutre) si la stratégie legacy n'est pas disponible ou plante.
        """
        self._lazy_init()

        base_score = 50.0
        direction = 0
        regime_mult = 1.0
        details: Dict = {}

        # ── 1. Régime de marché ────────────────────────────────────────────────
        try:
            if self._regime_detector and m1 is not None and m5 is not None and m15 is not None:
                regime = self._regime_detector.detect_current_regime(self.symbol, m1, m5, m15)
                cr = regime.get('composite_regime', 'NEUTRAL_MARKET')
                regime_mult = _REGIME_MULTIPLIERS.get(cr, 0.90)
                details['regime'] = cr
                details['regime_confidence'] = regime.get('confidence', 0.5)
        except Exception as e:
            logger.debug(f'Regime detector erreur: {e}')

        # ── 2. Stratégie legacy ────────────────────────────────────────────────
        if self._strategy is None or m1 is None or m5 is None or m15 is None:
            return self._build_result(base_score, direction, regime_mult, details,
                                       reason='Stratégie legacy non disponible')

        try:
            if self._strategy_type == 'crash_boom':
                result = self._run_crash_boom(m1, m5, m15, h1)
            elif self._strategy_type == 'volatility':
                result = self._run_volatility(m1, m5, m15)
            else:
                return self._build_result(base_score, direction, regime_mult, details)

            action     = result.get('action', 'HOLD')
            confidence = result.get('confidence_score', 0.5)
            direction  = _action_to_direction(action)
            base_score = _confidence_to_score(confidence, direction)

            details['legacy_action']     = action
            details['legacy_confidence'] = round(confidence, 3)
            details['legacy_reason']     = result.get('reason', '')

        except Exception as e:
            logger.warning(f'Legacy strategy({self.symbol}) erreur: {e}')

        return self._build_result(base_score, direction, regime_mult, details)

    def _run_crash_boom(self, m1, m5, m15, h1):
        """Appelle CrashBoomStrategy.analyze_crash_boom_conditions()."""
        # H1 est nécessaire pour la stratégie Crash/Boom V5
        if h1 is None or len(h1) < 10:
            # Construire H1 en agrégeant M15 (4 bougies = 1h)
            h1 = self._build_h1_from_m15(m15)
        return self._strategy.analyze_crash_boom_conditions(self.symbol, m1, m5, m15, h1)

    def _run_volatility(self, m1, m5, m15):
        """Appelle VolatilityStrategy.analyze_volatility_conditions()."""
        return self._strategy.analyze_volatility_conditions(self.symbol, m1, m5, m15)

    @staticmethod
    def _build_h1_from_m15(m15: pd.DataFrame) -> pd.DataFrame:
        """Agrège M15 → H1 quand le data provider MT5 ne fournit pas H1."""
        if m15 is None or len(m15) < 4:
            return pd.DataFrame()
        try:
            df = m15.copy()
            df.index = pd.to_datetime(df.index)
            h1 = df.resample('1h').agg({
                'open': 'first', 'high': 'max',
                'low': 'min', 'close': 'last',
                'tick_volume': 'sum',
            }).dropna()
            h1['body']  = h1['close'] - h1['open']
            h1['range'] = h1['high'] - h1['low']
            return h1
        except Exception:
            return pd.DataFrame()

    def _build_result(
        self,
        score: float,
        direction: int,
        regime_mult: float,
        details: dict,
        reason: str = '',
    ) -> dict:
        # Appliquer le multiplicateur de régime (sur l'écart par rapport à 50)
        adjusted = 50.0 + (score - 50.0) * regime_mult
        adjusted = round(min(100.0, max(0.0, adjusted)), 1)
        if reason:
            details['reason'] = reason
        return {
            'score': adjusted,
            'direction': direction,
            'regime_multiplier': regime_mult,
            'details': details,
        }
