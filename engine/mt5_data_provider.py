"""
MT5 Data Provider — Toutes les données viennent de MetaTrader 5
Remplace entièrement le WebSocket Deriv API
Fournit : ticks live, bougies M1/M5/M15, info compte, exécution d'ordres
"""
from __future__ import annotations
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple

import pandas as pd
import numpy as np

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

logger = logging.getLogger('dte.mt5_provider')

# ── Mapping symboles Deriv API → MT5 (Bible v1.0 Section 4.5) ────────────────
SYMBOL_MAP: Dict[str, str] = {
    'R_100':    'Volatility 100 Index',
    '1HZ100V':  'Volatility 100 (1s) Index',
    'CRASH500': 'Crash 500 Index',
    'CRASH1000':'Crash 1000 Index',
    'BOOM500':  'Boom 500 Index',
    'BOOM1000': 'Boom 1000 Index',
    'stpRNG':   'Step Index',
    'RB100':    'Range Break 100 Index',
}
SYMBOL_MAP_REVERSE = {v: k for k, v in SYMBOL_MAP.items()}

# Pip sizes par symbole MT5 (Bible v1.0 Section 4.5)
PIP_SIZES: Dict[str, float] = {
    'Volatility 100 Index':       0.01,
    'Volatility 100 (1s) Index':  0.01,
    'Crash 500 Index':            0.001,
    'Crash 1000 Index':           0.001,
    'Boom 500 Index':             0.001,
    'Boom 1000 Index':            0.001,
    'Step Index':                 0.1,
    'Range Break 100 Index':      0.1,
}

# Stop-loss minimum en pips — plancher absolu (Bible v1.0)
RECOMMENDED_SL_PIPS: Dict[str, float] = {
    'Volatility 100 Index':       20.0,
    'Volatility 100 (1s) Index':  25.0,
    'Crash 500 Index':            15.0,
    'Crash 1000 Index':           20.0,
    'Boom 500 Index':             15.0,
    'Boom 1000 Index':            25.0,
    'Step Index':                 30.0,
    'Range Break 100 Index':      50.0,
}

# Multiplicateur ATR pour le SL dynamique — par actif
# Crash/Boom : spikes brusques → SL plus large pour éviter le stop-hunt
# Step Index  : mouvements réguliers → SL serré suffisant
SL_ATR_MULT: Dict[str, float] = {
    'Crash 500 Index':            2.5,
    'Crash 1000 Index':           2.5,
    'Boom 500 Index':             2.5,
    'Boom 1000 Index':            2.5,
    'Volatility 100 Index':       1.8,
    'Volatility 100 (1s) Index':  2.0,
    'Step Index':                 1.2,
    'Range Break 100 Index':      1.5,
}

MAGIC_NUMBER = 20260617  # Identifiant unique de l'écosystème DTE


class MT5DataProvider:
    """
    Fournit les données de marché et l'exécution des ordres via MT5.
    Un seul objet partagé dans tout l'écosystème.
    """

    def __init__(self, login: int = None, password: str = None, server: str = None):
        self.login = login
        self.password = password
        self.server = server
        self.connected = False
        self._max_retries = 3

    # ── Connexion ─────────────────────────────────────────────────────────────
    def connect(self) -> bool:
        if not MT5_AVAILABLE:
            logger.error('MetaTrader5 non installé (pip install MetaTrader5)')
            return False
        if not mt5.initialize():
            logger.error(f'mt5.initialize() failed: {mt5.last_error()}')
            return False
        if self.login and self.password and self.server:
            if not mt5.login(int(self.login), self.password, self.server):
                logger.error(f'mt5.login() failed: {mt5.last_error()}')
                mt5.shutdown()
                return False
        self.connected = True
        info = mt5.account_info()
        if info:
            logger.info(f'MT5 connecté | Compte: {info.login} | Solde: {info.balance} | Serveur: {info.server}')
        return True

    def disconnect(self):
        if MT5_AVAILABLE:
            mt5.shutdown()
        self.connected = False

    def ensure_connected(self) -> bool:
        if not self.connected:
            return self.connect()
        try:
            return mt5.account_info() is not None
        except Exception:
            self.connected = False
            return self.connect()

    # ── Données de marché ─────────────────────────────────────────────────────
    def get_candles(
        self,
        symbol: str,
        timeframe_str: str = 'M1',
        count: int = 500,
    ) -> Optional[pd.DataFrame]:
        """
        Récupère les bougies OHLCV depuis MT5.
        symbol peut être le nom MT5 direct ou le code API Deriv.
        """
        if not self.ensure_connected():
            return None

        mt5_sym = SYMBOL_MAP.get(symbol, symbol)
        tf_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'H1': mt5.TIMEFRAME_H1,
        }
        tf = tf_map.get(timeframe_str, mt5.TIMEFRAME_M1)

        if not mt5.symbol_select(mt5_sym, True):
            logger.warning(f'Impossible de sélectionner {mt5_sym}')
            return None

        rates = mt5.copy_rates_from_pos(mt5_sym, tf, 0, count)
        if rates is None or len(rates) == 0:
            logger.warning(f'Pas de données pour {mt5_sym} {timeframe_str}: {mt5.last_error()}')
            return None

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        df['body'] = df['close'] - df['open']
        df['range'] = df['high'] - df['low']
        return df

    def get_all_timeframes(
        self,
        symbol: str,
        count_m1: int = 200,
        count_m5: int = 150,
        count_m15: int = 100,
    ) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """Récupère M1, M5, M15 en une seule opération."""
        m1 = self.get_candles(symbol, 'M1', count_m1)
        m5 = self.get_candles(symbol, 'M5', count_m5)
        m15 = self.get_candles(symbol, 'M15', count_m15)
        return m1, m5, m15

    def get_current_price(self, symbol: str) -> Optional[Dict]:
        """Prix bid/ask courant depuis MT5."""
        if not self.ensure_connected():
            return None
        mt5_sym = SYMBOL_MAP.get(symbol, symbol)
        tick = mt5.symbol_info_tick(mt5_sym)
        if tick is None:
            return None
        return {'bid': tick.bid, 'ask': tick.ask, 'time': tick.time}

    def get_account_info(self) -> dict:
        if not self.ensure_connected():
            return {}
        info = mt5.account_info()
        if info is None:
            return {}
        return {
            'login': info.login,
            'balance': info.balance,
            'equity': info.equity,
            'margin': info.margin,
            'free_margin': info.margin_free,
            'profit': info.profit,
            'currency': info.currency,
            'leverage': info.leverage,
            'server': info.server,
        }

    # ── Exécution d'ordres ────────────────────────────────────────────────────
    def calculate_volume(
        self,
        symbol: str,
        risk_amount: float,
        sl_pips: float = 15.0,
    ) -> float:
        """
        Calcule le volume en lots pour risquer `risk_amount` avec `sl_pips` de stop.
        Volume = risk_amount / (sl_pips * pip_size * tick_value_per_lot)
        """
        if not self.ensure_connected():
            return 0.01
        mt5_sym = SYMBOL_MAP.get(symbol, symbol)
        sym_info = mt5.symbol_info(mt5_sym)
        if sym_info is None:
            return 0.01

        pip_size = PIP_SIZES.get(mt5_sym, sym_info.point * 10)
        tick_value = sym_info.trade_tick_value
        tick_size = sym_info.trade_tick_size
        if tick_size <= 0 or tick_value <= 0:
            return sym_info.volume_min

        # Valeur monétaire par pip par lot
        pip_value_per_lot = (pip_size / tick_size) * tick_value
        if pip_value_per_lot <= 0 or sl_pips <= 0:
            return sym_info.volume_min

        vol = risk_amount / (sl_pips * pip_value_per_lot)
        vol = max(sym_info.volume_min, min(sym_info.volume_max, vol))
        step = sym_info.volume_step
        vol = round(round(vol / step) * step, 8)
        # Re-clamp après arrondi (step peut dépasser volume_max)
        vol = max(sym_info.volume_min, min(sym_info.volume_max, vol))
        return vol

    def place_order(
        self,
        symbol: str,
        direction: str,           # 'BUY' | 'SELL'
        volume: float,
        sl_pips: float = 0.0,
        tp_pips: float = 0.0,
        comment: str = '',
        sl_price: float = 0.0,   # prix absolu SL (prioritaire sur sl_pips)
        tp_price: float = 0.0,   # prix absolu TP (prioritaire sur tp_pips)
    ) -> dict:
        """Place un ordre sur un actif synthétique via MT5."""
        if not self.ensure_connected():
            return {'success': False, 'error': 'MT5 non connecté'}

        mt5_sym = SYMBOL_MAP.get(symbol, symbol)
        if not mt5.symbol_select(mt5_sym, True):
            return {'success': False, 'error': f'Symbole {mt5_sym} introuvable'}

        sym_info = mt5.symbol_info(mt5_sym)
        tick = mt5.symbol_info_tick(mt5_sym)
        if sym_info is None or tick is None:
            return {'success': False, 'error': 'Impossible d\'obtenir info symbole/tick'}

        order_type = mt5.ORDER_TYPE_BUY if direction == 'BUY' else mt5.ORDER_TYPE_SELL
        price = tick.ask if direction == 'BUY' else tick.bid
        point = sym_info.point

        # Utilise les prix absolus si fournis, sinon calcule depuis pips
        if sl_price > 0 and tp_price > 0:
            sl = sl_price
            tp = tp_price
        else:
            sl = 0.0
            tp = 0.0
            if sl_pips > 0:
                sl = price - sl_pips * point if direction == 'BUY' else price + sl_pips * point
            if tp_pips > 0:
                tp = price + tp_pips * point if direction == 'BUY' else price - tp_pips * point

        request = {
            'action':       mt5.TRADE_ACTION_DEAL,
            'symbol':       mt5_sym,
            'volume':       float(volume),
            'type':         order_type,
            'price':        price,
            'sl':           sl,
            'tp':           tp,
            'deviation':    50,
            'magic':        MAGIC_NUMBER,
            'comment':      comment[:31],
            'type_time':    mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_FOK,
        }

        result = mt5.order_send(request)
        if result is None:
            return {'success': False, 'error': f'order_send None: {mt5.last_error()}'}
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {'success': False, 'retcode': result.retcode, 'error': result.comment}

        return {
            'success': True,
            'ticket': result.order,
            'symbol': mt5_sym,
            'direction': direction,
            'volume': volume,
            'price': result.price,
            'sl': sl,
            'tp': tp,
            'timestamp': datetime.now().isoformat(),
        }

    def close_position(self, ticket: int) -> dict:
        """Clôture une position ouverte par son ticket."""
        if not self.ensure_connected():
            return {'success': False, 'error': 'MT5 non connecté'}

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return {'success': False, 'error': f'Position {ticket} introuvable'}

        pos = positions[0]
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            return {'success': False, 'error': 'Tick indisponible'}

        order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask

        request = {
            'action':       mt5.TRADE_ACTION_DEAL,
            'symbol':       pos.symbol,
            'volume':       pos.volume,
            'type':         order_type,
            'position':     ticket,
            'price':        price,
            'deviation':    20,
            'magic':        MAGIC_NUMBER,
            'comment':      f'Close #{ticket}',
            'type_time':    mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_FOK,
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            return {'success': True, 'ticket': ticket, 'profit': pos.profit}
        return {'success': False, 'error': result.comment if result else 'Erreur inconnue'}

    def get_open_positions(self, symbol: str = None) -> list:
        """Retourne les positions ouvertes du système DTE (magic number)."""
        if not self.ensure_connected():
            return []
        mt5_sym = SYMBOL_MAP.get(symbol, symbol) if symbol else None
        positions = mt5.positions_get(symbol=mt5_sym) if mt5_sym else mt5.positions_get()
        if positions is None:
            return []
        return [p._asdict() for p in positions if p.magic == MAGIC_NUMBER]

    def compute_sl_tp_dynamic(
        self,
        symbol: str,
        direction: str,
        m1: 'pd.DataFrame',
        score: float = 60.0,
        spike_alert: bool = False,
        reduce_size: bool = False,
    ) -> dict:
        """
        Calcule SL et TP dynamiquement depuis l'ATR M1 courant.

        Travaille entièrement en unités de prix brutes (sym_info.point) pour
        éviter toute conversion pip→point incorrecte.

        SL = max(plancher, ATR_14 × mult, distance_mini_broker)
        TP = SL × RR    (RR : spike→1.2 | ≥80→2.5 | ≥65→2.0 | sinon→1.5)
        """
        mt5_sym = SYMBOL_MAP.get(symbol, symbol)

        # ── Infos symbole depuis MT5 (source de vérité) ──────────────────────
        sym_info = None
        tick = None
        if self.ensure_connected():
            mt5.symbol_select(mt5_sym, True)
            sym_info = mt5.symbol_info(mt5_sym)
            tick = mt5.symbol_info_tick(mt5_sym)

        point = sym_info.point if sym_info else PIP_SIZES.get(mt5_sym, 0.001)

        # ── ATR 14 périodes en unités de prix brutes ──────────────────────────
        atr_raw = 0.0
        if m1 is not None and len(m1) >= 15:
            v = m1['range'].rolling(14).mean().iloc[-1]
            if v == v:   # test NaN
                atr_raw = float(v)

        # ── SL distance en prix bruts ─────────────────────────────────────────
        atr_mult   = SL_ATR_MULT.get(mt5_sym, 1.8)
        min_sl_raw = RECOMMENDED_SL_PIPS.get(mt5_sym, 20.0) * point
        sl_dist    = max(min_sl_raw, atr_raw * atr_mult)

        # Respecter la distance minimale imposée par le broker (trade_stops_level)
        if sym_info and tick:
            spread        = tick.ask - tick.bid
            broker_min    = sym_info.trade_stops_level * point
            sl_dist = max(sl_dist, broker_min, spread * 2, point * 10)

        # ── RR ratio ─────────────────────────────────────────────────────────
        if spike_alert:
            rr = 1.2
        elif score >= 80:
            rr = 2.5
        elif score >= 65:
            rr = 2.0
        else:
            rr = 1.5

        tp_dist = sl_dist * rr

        # ── Prix absolus SL/TP ────────────────────────────────────────────────
        sl_price = tp_price = 0.0
        if tick:
            price = tick.ask if direction == 'BUY' else tick.bid
            digits = sym_info.digits if sym_info else 5
            if direction == 'BUY':
                sl_price = round(price - sl_dist, digits)
                tp_price = round(price + tp_dist, digits)
            else:
                sl_price = round(price + sl_dist, digits)
                tp_price = round(price - tp_dist, digits)

        # Valeurs display en pips (informatif dans les logs)
        pip_size = PIP_SIZES.get(mt5_sym, point)
        atr_pips = round(atr_raw / pip_size, 1) if pip_size > 0 else 0.0
        sl_pips  = round(sl_dist  / pip_size, 1) if pip_size > 0 else 0.0
        tp_pips  = round(tp_dist  / pip_size, 1) if pip_size > 0 else 0.0

        return {
            'sl_pips':  sl_pips,
            'tp_pips':  tp_pips,
            'rr_ratio': rr,
            'atr_pips': atr_pips,
            'sl_price': sl_price,
            'tp_price': tp_price,
        }

    def modify_position_sl(self, ticket: int, new_sl: float, new_tp: float = 0.0) -> bool:
        """Modifie le SL (et optionnellement TP) d'une position ouverte via TRADE_ACTION_SLTP."""
        if not self.ensure_connected():
            return False
        pos_list = mt5.positions_get(ticket=ticket)
        if not pos_list:
            return False
        pos = pos_list[0]
        request = {
            'action':   mt5.TRADE_ACTION_SLTP,
            'symbol':   pos.symbol,
            'position': ticket,
            'sl':       new_sl,
            'tp':       new_tp if new_tp > 0 else pos.tp,
        }
        result = mt5.order_send(request)
        return bool(result and result.retcode == mt5.TRADE_RETCODE_DONE)

    def close_all_positions(self) -> List[dict]:
        """Urgence : ferme toutes les positions DTE."""
        results = []
        for pos in self.get_open_positions():
            r = self.close_position(pos['ticket'])
            results.append(r)
            time.sleep(0.1)
        return results
