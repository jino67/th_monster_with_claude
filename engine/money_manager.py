"""
Money Manager — Kelly Criterion + Martingale bornée + Flat Betting
Règles absolues depuis Bible v1.0 Section 12 & Formule 4-5

v2 : gestion de crise (streaks de pertes + drawdown adaptatif)
  - Score → lots : plage 50%→100% de la mise (score 40 → ×0.50, score 100 → ×1.0)
  - Streak de pertes : réduction paliers puis pause forcée
  - Drawdown adaptatif : réduction progressive si drawdown session > 3%
"""
from __future__ import annotations
import math
import logging
from dataclasses import dataclass
from typing import Literal, Optional

logger = logging.getLogger('dte.money_manager')

# ── Règles absolues ───────────────────────────────────────────────────────────
MAX_RISK_PER_TRADE   = 0.03   # 3% max du capital par trade
STOP_SESSION_PCT     = 0.10   # -10% → arrêt de session
MAX_MARTINGALE_LVLS  = 5
MIN_SCORE_TRADE      = 40.0
MIN_CAPITAL          = 5.0

# ── Gestion de crise : paliers de streaks de pertes ─────────────────────────
# (seuil_pertes_consec, multiplicateur_risque, cycles_pause)
# Exemple : 5 pertes consécutives → risque ×0.30 ; 7 → pause 50 cycles (~100s)
CRISIS_LEVELS = [
    (3, 0.60,  0),   # 3 pertes → -40% de risque
    (5, 0.30,  0),   # 5 pertes → -70% de risque
    (7, 0.00, 50),   # 7 pertes → pause complète 50 cycles
]

# ── Réduction adaptative au drawdown session ─────────────────────────────────
# (seuil_dd_pct, multiplicateur_risque)
DD_LEVELS = [
    (7.5, 0.25),
    (5.0, 0.50),
    (3.0, 0.75),
]

Strategy = Literal['FLAT', 'KELLY', 'MARTINGALE']


@dataclass
class PositionSizing:
    action:           Literal['TRADE', 'WAIT', 'STOP_SESSION']
    amount:           float
    risk_pct:         float
    volume_lots:      float
    strategy:         Strategy
    martingale_level: int
    reason:           str
    crisis_level:     int = 0    # 0 = normal, 1-3 = palier de crise actif


class MoneyManager:
    """Gestionnaire de money management pour le système DTE."""

    def __init__(
        self,
        initial_capital: float,
        strategy: Strategy = 'FLAT',
        base_risk_pct: float = 0.01,
    ):
        self.initial_capital        = initial_capital
        self.current_capital        = initial_capital
        self.session_start_capital  = initial_capital
        self.strategy               = strategy
        self.base_risk_pct          = min(base_risk_pct, MAX_RISK_PER_TRADE)
        self.trades:                list = []
        self.consecutive_losses     = 0
        self.consecutive_wins       = 0
        self.martingale_level       = 0
        self.total_pnl              = 0.0
        self.session_trades         = 0
        self.session_stopped        = False
        self._pause_cycles_left     = 0   # compte à rebours de la pause forcée

    # ── Kelly Criterion (1/4 Kelly) ──────────────────────────────────────────
    def kelly_fraction(self, win_prob: float, rr_ratio: float = 1.0) -> float:
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
        Intègre : gestion de crise streaks, drawdown adaptatif, score→lots.
        """
        # ── Règles absolues ───────────────────────────────────────────────────
        if self.session_stopped:
            return PositionSizing('STOP_SESSION', 0, 0, 0, self.strategy, 0,
                                  'Session stoppée.', 0)

        if self.current_capital < MIN_CAPITAL:
            return PositionSizing('STOP_SESSION', 0, 0, 0, self.strategy, 0,
                                  f'Capital insuffisant ({self.current_capital:.2f})', 0)

        dd = self._session_drawdown()
        if dd >= STOP_SESSION_PCT:
            self.session_stopped = True
            return PositionSizing('STOP_SESSION', 0, 0, 0, self.strategy, 0,
                                  f'Drawdown session {dd*100:.1f}% ≥ {STOP_SESSION_PCT*100:.0f}%', 0)

        if signal_score < MIN_SCORE_TRADE:
            return PositionSizing('WAIT', 0, 0, 0, self.strategy, self.martingale_level,
                                  f'Score {signal_score} < {MIN_SCORE_TRADE}', 0)

        # ── Pause forcée (streak sévère) ──────────────────────────────────────
        if self._pause_cycles_left > 0:
            self._pause_cycles_left -= 1
            return PositionSizing(
                'WAIT', 0, 0, 0, self.strategy, self.martingale_level,
                f'Pause crise — {self._pause_cycles_left} cycles restants '
                f'({self.consecutive_losses} pertes consécutives)', 3,
            )

        # ── Gestion de crise : streak de pertes ───────────────────────────────
        crisis_level = 0
        crisis_mult  = 1.0
        for lvl, (threshold, mult, pause) in enumerate(CRISIS_LEVELS, start=1):
            if self.consecutive_losses >= threshold:
                crisis_level = lvl
                crisis_mult  = mult
                if pause > 0 and mult == 0.0:
                    self._pause_cycles_left = pause
                    return PositionSizing(
                        'WAIT', 0, 0, 0, self.strategy, self.martingale_level,
                        f'Pause crise activée — {self.consecutive_losses} pertes consécutives, '
                        f'{pause} cycles de pause', crisis_level,
                    )

        # ── Risque de base selon stratégie ────────────────────────────────────
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

        risk_pct = min(risk_pct, MAX_RISK_PER_TRADE)

        # ── Score → lots : plage 50%→100% ────────────────────────────────────
        # score 40 → ×0.50 | score 70 → ×0.75 | score 100 → ×1.0
        score_factor = 0.50 + (signal_score - MIN_SCORE_TRADE) / (100.0 - MIN_SCORE_TRADE) * 0.50
        score_factor = max(0.50, min(1.0, score_factor))
        risk_pct = min(risk_pct * score_factor, MAX_RISK_PER_TRADE)

        # ── Drawdown adaptatif ────────────────────────────────────────────────
        dd_mult = 1.0
        dd_pct  = dd * 100.0
        for threshold, mult in DD_LEVELS:
            if dd_pct >= threshold:
                dd_mult = mult
                break
        risk_pct = min(risk_pct * dd_mult, MAX_RISK_PER_TRADE)

        # ── Multiplicateur de crise streak ────────────────────────────────────
        risk_pct = min(risk_pct * crisis_mult, MAX_RISK_PER_TRADE)

        amount = round(self.current_capital * risk_pct, 2)

        reason_parts = [f'Signal {signal_score:.0f}', f'MM:{self.strategy}',
                        f'DD:{dd_pct:.1f}%']
        if crisis_level > 0:
            reason_parts.append(f'CRISE_L{crisis_level}(×{crisis_mult:.2f})')
        if dd_mult < 1.0:
            reason_parts.append(f'DD_RED(×{dd_mult:.2f})')

        return PositionSizing(
            action='TRADE',
            amount=amount,
            risk_pct=round(risk_pct * 100, 2),
            volume_lots=0.0,
            strategy=self.strategy,
            martingale_level=self.martingale_level,
            reason=' | '.join(reason_parts),
            crisis_level=crisis_level,
        )

    # ── Enregistrement d'un trade ─────────────────────────────────────────────
    def record_trade(self, pnl: float) -> None:
        self.current_capital = round(self.current_capital + pnl, 2)
        self.total_pnl       = round(self.total_pnl + pnl, 2)
        self.session_trades += 1
        self.trades.append({'pnl': pnl, 'capital': self.current_capital})

        if pnl < 0:
            self.consecutive_losses += 1
            self.consecutive_wins    = 0
            if self.strategy == 'MARTINGALE':
                self.martingale_level = min(self.martingale_level + 1, MAX_MARTINGALE_LVLS)

            # Log la situation de crise
            for threshold, mult, pause in CRISIS_LEVELS:
                if self.consecutive_losses == threshold:
                    if pause > 0:
                        logger.warning(
                            f'[CRISE] {self.consecutive_losses} pertes consécutives — '
                            f'pause {pause} cycles activée au prochain trade'
                        )
                    else:
                        logger.warning(
                            f'[CRISE] {self.consecutive_losses} pertes consécutives — '
                            f'risque réduit ×{mult:.2f}'
                        )
        else:
            self.consecutive_wins   += 1
            self.consecutive_losses  = 0
            self.martingale_level    = 0
            # Sortie de crise : reset la pause si une victoire survient
            if self._pause_cycles_left > 0:
                self._pause_cycles_left = 0
                logger.info('[CRISE] Victoire enregistrée — pause annulée')

    def reset_session(self) -> None:
        self.session_start_capital  = self.current_capital
        self.session_trades         = 0
        self.session_stopped        = False
        self.martingale_level       = 0
        self.consecutive_losses     = 0
        self._pause_cycles_left     = 0
        logger.info(f'Session réinitialisée. Capital: {self.current_capital}')

    # ── Statistiques ─────────────────────────────────────────────────────────
    def _session_drawdown(self) -> float:
        if self.session_start_capital <= 0:
            return 0.0
        return max(0.0,
                   (self.session_start_capital - self.current_capital) / self.session_start_capital)

    def get_crisis_status(self) -> dict:
        """Résumé de l'état de crise courant."""
        dd_pct = self._session_drawdown() * 100.0
        crisis_level = 0
        crisis_mult  = 1.0
        for lvl, (threshold, mult, _) in enumerate(CRISIS_LEVELS, start=1):
            if self.consecutive_losses >= threshold:
                crisis_level = lvl
                crisis_mult  = mult
        dd_mult = 1.0
        for threshold, mult in DD_LEVELS:
            if dd_pct >= threshold:
                dd_mult = mult
                break
        return {
            'consecutive_losses':  self.consecutive_losses,
            'crisis_level':        crisis_level,
            'crisis_mult':         crisis_mult,
            'dd_pct':              round(dd_pct, 2),
            'dd_mult':             dd_mult,
            'pause_cycles_left':   self._pause_cycles_left,
            'effective_mult':      round(crisis_mult * dd_mult, 3),
        }

    def get_stats(self) -> dict:
        if not self.trades:
            return {'total_trades': 0, 'current_capital': self.current_capital}
        wins    = [t for t in self.trades if t['pnl'] > 0]
        losses  = [t for t in self.trades if t['pnl'] < 0]
        caps    = [self.initial_capital] + [t['capital'] for t in self.trades]
        peak    = caps[0]
        max_dd  = 0.0
        for cap in caps:
            if cap > peak:
                peak = cap
            dd = (peak - cap) / peak * 100
            max_dd = max(max_dd, dd)
        crisis = self.get_crisis_status()
        return {
            'total_trades':         len(self.trades),
            'wins':                 len(wins),
            'losses':               len(losses),
            'win_rate_pct':         round(len(wins) / len(self.trades) * 100, 1),
            'total_pnl':            self.total_pnl,
            'current_capital':      self.current_capital,
            'roi_pct':              round((self.current_capital - self.initial_capital)
                                         / self.initial_capital * 100, 2),
            'max_drawdown_pct':     round(max_dd, 2),
            'consecutive_losses':   self.consecutive_losses,
            'martingale_level':     self.martingale_level,
            'session_drawdown_pct': round(self._session_drawdown() * 100, 2),
            'crisis_level':         crisis['crisis_level'],
            'effective_risk_mult':  crisis['effective_mult'],
            'pause_cycles_left':    crisis['pause_cycles_left'],
        }
