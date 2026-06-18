"""
Money Manager — Kelly Criterion + Martingale bornée + Flat Betting
Règles absolues depuis Bible v1.0 Section 12 & Formule 4-5
"""
from __future__ import annotations
import math
import logging
from dataclasses import dataclass
from typing import Literal, Optional

logger = logging.getLogger('dte.money_manager')

# ── Règles absolues (inchangeables) ──────────────────────────────────────────
MAX_RISK_PER_TRADE   = 0.03   # 3% max du capital par trade
STOP_SESSION_PCT     = 0.10   # -10% → arrêt de session
MAX_MARTINGALE_LVLS  = 5      # Max 5 doublements
MIN_SCORE_TRADE      = 40.0   # Score minimum
MIN_CAPITAL          = 5.0    # Capital minimum pour ouvrir un trade

Strategy = Literal['FLAT', 'KELLY', 'MARTINGALE']


@dataclass
class PositionSizing:
    action: Literal['TRADE', 'WAIT', 'STOP_SESSION']
    amount: float          # montant en devise du compte
    risk_pct: float        # % du capital risqué
    volume_lots: float     # en lots MT5 (calculé séparément)
    strategy: Strategy
    martingale_level: int
    reason: str


class MoneyManager:
    """Gestionnaire de money management pour le système DTE."""

    def __init__(
        self,
        initial_capital: float,
        strategy: Strategy = 'FLAT',
        base_risk_pct: float = 0.01,
    ):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.session_start_capital = initial_capital
        self.strategy = strategy
        self.base_risk_pct = min(base_risk_pct, MAX_RISK_PER_TRADE)
        self.trades: list = []
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.martingale_level = 0
        self.total_pnl = 0.0
        self.session_trades = 0
        self.session_stopped = False

    # ── Kelly Criterion (1/4 Kelly) ──────────────────────────────────────────
    def kelly_fraction(self, win_prob: float, rr_ratio: float = 1.0) -> float:
        """
        f* = (p*b - q) / b,  b = RR ratio,  fraction = f*/4
        Borné entre 1% et 3%
        """
        p = min(0.99, max(0.01, win_prob / 100.0))
        q = 1.0 - p
        b = max(0.1, rr_ratio)
        kelly_full = (p * b - q) / b
        if kelly_full <= 0:
            return 0.01
        return max(0.01, min(MAX_RISK_PER_TRADE, kelly_full / 4.0))

    # ── Calcul de la mise ─────────────────────────────────────────────────────
    def get_position_size(
        self,
        signal_score: float,
        win_prob: float = 55.0,
        rr_ratio: float = 1.5,
    ) -> PositionSizing:
        """
        Calcule la taille de position selon la stratégie active.
        Applique toutes les règles absolues avant de retourner.
        """
        # Règle absolue : session stoppée
        if self.session_stopped:
            return PositionSizing('STOP_SESSION', 0, 0, 0, self.strategy, 0,
                                  'Session stoppée manuellement.')

        # Règle absolue : capital insuffisant
        if self.current_capital < MIN_CAPITAL:
            return PositionSizing('STOP_SESSION', 0, 0, 0, self.strategy, 0,
                                  f'Capital insuffisant ({self.current_capital:.2f})')

        # Règle absolue : stop de session
        dd = self._session_drawdown()
        if dd >= STOP_SESSION_PCT:
            self.session_stopped = True
            return PositionSizing('STOP_SESSION', 0, 0, 0, self.strategy, 0,
                                  f'Drawdown session {dd*100:.1f}% ≥ {STOP_SESSION_PCT*100:.0f}%')

        # Règle absolue : score insuffisant
        if signal_score < MIN_SCORE_TRADE:
            return PositionSizing('WAIT', 0, 0, 0, self.strategy, self.martingale_level,
                                  f'Score {signal_score} < {MIN_SCORE_TRADE}')

        # ── Calcul du risque de base ──────────────────────────────────────────
        if self.strategy == 'FLAT':
            risk_pct = self.base_risk_pct

        elif self.strategy == 'KELLY':
            risk_pct = self.kelly_fraction(win_prob, rr_ratio)

        elif self.strategy == 'MARTINGALE':
            if self.martingale_level >= MAX_MARTINGALE_LVLS:
                logger.warning('Martingale max atteint → reset au niveau 0')
                self.martingale_level = 0
            risk_pct = self.base_risk_pct * (2 ** self.martingale_level)

        else:
            risk_pct = self.base_risk_pct

        # Règle absolue : plafond à 2%
        risk_pct = min(risk_pct, MAX_RISK_PER_TRADE)

        # Moduler légèrement selon le score (score 40 → ×0.8, score 100 → ×1.0)
        score_factor = 0.80 + (signal_score - MIN_SCORE_TRADE) / (100 - MIN_SCORE_TRADE) * 0.20
        risk_pct = min(risk_pct * score_factor, MAX_RISK_PER_TRADE)

        amount = round(self.current_capital * risk_pct, 2)
        # volume_lots est calculé ailleurs (besoin du tick_value MT5)
        return PositionSizing(
            action='TRADE',
            amount=amount,
            risk_pct=round(risk_pct * 100, 2),
            volume_lots=0.0,  # à remplir par l'appelant
            strategy=self.strategy,
            martingale_level=self.martingale_level,
            reason=f'Signal {signal_score} | Strategy {self.strategy} | DD {dd*100:.1f}%',
        )

    # ── Enregistrement d'un trade ─────────────────────────────────────────────
    def record_trade(self, pnl: float) -> None:
        self.current_capital = round(self.current_capital + pnl, 2)
        self.total_pnl = round(self.total_pnl + pnl, 2)
        self.session_trades += 1
        t = {'pnl': pnl, 'capital': self.current_capital}
        self.trades.append(t)

        if pnl < 0:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            if self.strategy == 'MARTINGALE':
                self.martingale_level = min(self.martingale_level + 1, MAX_MARTINGALE_LVLS)
        else:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            self.martingale_level = 0

    def reset_session(self) -> None:
        self.session_start_capital = self.current_capital
        self.session_trades = 0
        self.session_stopped = False
        self.martingale_level = 0
        self.consecutive_losses = 0
        logger.info(f'Session réinitialisée. Capital: {self.current_capital}')

    # ── Statistiques ─────────────────────────────────────────────────────────
    def _session_drawdown(self) -> float:
        if self.session_start_capital <= 0:
            return 0.0
        return max(0.0, (self.session_start_capital - self.current_capital) / self.session_start_capital)

    def get_stats(self) -> dict:
        if not self.trades:
            return {'total_trades': 0, 'current_capital': self.current_capital}
        wins = [t for t in self.trades if t['pnl'] > 0]
        losses = [t for t in self.trades if t['pnl'] < 0]
        capitals = [self.initial_capital] + [t['capital'] for t in self.trades]
        peak = capitals[0]
        max_dd = 0.0
        for cap in capitals:
            if cap > peak:
                peak = cap
            dd = (peak - cap) / peak * 100
            max_dd = max(max_dd, dd)
        return {
            'total_trades': len(self.trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate_pct': round(len(wins) / len(self.trades) * 100, 1),
            'total_pnl': self.total_pnl,
            'current_capital': self.current_capital,
            'roi_pct': round((self.current_capital - self.initial_capital) / self.initial_capital * 100, 2),
            'max_drawdown_pct': round(max_dd, 2),
            'consecutive_losses': self.consecutive_losses,
            'martingale_level': self.martingale_level,
            'session_drawdown_pct': round(self._session_drawdown() * 100, 2),
        }
