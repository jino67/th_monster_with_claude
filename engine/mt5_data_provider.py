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

# Stop-loss recommandés en pips (Bible v1.0)
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
        # Respecter les contraintes MT5
        vol = max(sym_info.volume_min, min(sym_info.volume_max, vol))
        # Arrondir au step
        step = sym_info.volume_step
        vol = round(round(vol / step) * step, 8)
        return max(sym_info.volume_min, vol)

    def place_order(
        self,
        symbol: str,
        direction: str,           # 'BUY' | 'SELL'
        volume: float,
        sl_pips: float = 0.0,
        tp_pips: float = 0.0,
        comment: str = '',
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
            'deviation':    20,
            'magic':        MAGIC_NUMBER,
            'comment':      comment[:31],
            'type_time':    mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_IOC,
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
            'type_filling': mt5.ORDER_FILLING_IOC,
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

    def close_all_positions(self) -> List[dict]:
        """Urgence : ferme toutes les positions DTE."""
        results = []
        for pos in self.get_open_positions():
            r = self.close_position(pos['ticket'])
            results.append(r)
            time.sleep(0.1)
        return results
