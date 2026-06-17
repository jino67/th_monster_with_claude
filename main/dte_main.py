"""
DTE Main — Point d'entrée principal de l'écosystème Deriv Trading Ecosystem v1.0
Lance le moteur statistique en boucle, met à jour l'API, exécute les trades via MT5.

Usage:
  python -m main.dte_main
  python -m main.dte_main --symbol "Crash 500 Index" --strategy FLAT --mode SIGNAL_ONLY

Modes:
  SIGNAL_ONLY  — calcule et affiche les signaux, n'exécute rien
  SEMI_AUTO    — affiche le signal, attend confirmation manuelle (input)
  FULL_AUTO    — exécute automatiquement (respect strict des règles absolues)
"""

import os
import sys
import time
import json
import logging
import argparse
import threading
from datetime import datetime
from pathlib import Path

# Ajout du root au path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.mt5_data_provider import MT5DataProvider, SYMBOL_MAP
from engine.signal_fusion import SignalFusion
from engine.money_manager import MoneyManager
from engine.llm_advisor import LLMAdvisor
from engine.mt5_data_provider import RECOMMENDED_SL_PIPS

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR = ROOT / 'logs'
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f'dte_{datetime.now():%Y%m%d}.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger('dte.main')

# ── Constantes ────────────────────────────────────────────────────────────────
STATE_FILE    = ROOT / 'dashboard_live_state.json'   # compatible avec l'ancien dashboard
DTE_STATE_FILE = ROOT / 'dte_live_state.json'        # nouveau fichier pour l'API

DEFAULT_SYMBOLS = [
    'Volatility 100 Index',
    'Volatility 100 (1s) Index',
    'Crash 500 Index',
    'Crash 1000 Index',
    'Boom 500 Index',
    'Boom 1000 Index',
    'Step Index',
    'Range Break 100 Index',
]

LOOP_SLEEP_SEC = 2  # intervalle entre chaque cycle

# ── État global partagé avec l'API ────────────────────────────────────────────
_state = {
    'running': True,
    'mode': 'SIGNAL_ONLY',
    'active_symbol': 'Crash 500 Index',
    'signals': {},
    'account': {},
    'positions': [],
    'session_stats': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0, 'win_rate': 0.0},
    'mm_stats': {},
    'last_update': datetime.now().isoformat(),
    'alerts': [],
}


def write_state():
    """Persiste l'état vers les fichiers JSON (pour API + anciens composants)."""
    try:
        with open(DTE_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_state, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f'Erreur écriture état: {e}')


def add_alert(msg: str, level: str = 'INFO'):
    alert = {'timestamp': datetime.now().isoformat(), 'level': level, 'message': msg}
    _state['alerts'].append(alert)
    if len(_state['alerts']) > 200:
        _state['alerts'] = _state['alerts'][-200:]
    if level in ('WARN', 'ERROR', 'CRITIQUE'):
        logger.warning(f'[ALERT] {msg}')
    else:
        logger.info(f'[ALERT] {msg}')


# ── Boucle principale ─────────────────────────────────────────────────────────
class DTEEngine:

    def __init__(
        self,
        symbols: list,
        strategy: str = 'FLAT',
        mode: str = 'SIGNAL_ONLY',
        base_risk_pct: float = 0.01,
        use_llm: bool = True,
    ):
        self.symbols   = symbols
        self.strategy  = strategy
        self.mode      = mode

        # MT5
        self.provider = MT5DataProvider(
            login=int(os.getenv('MT5_ACCOUNT_NUMBER', '0')),
            password=os.getenv('MT5_PASSWORD', ''),
            server=os.getenv('MT5_SERVER', 'DerivSVG-Server'),
        )

        # Un moteur de signal par symbole
        self.fusions: dict = {s: SignalFusion(s) for s in symbols}

        # Money Manager global (capital récupéré depuis MT5 après connexion)
        self.mm: MoneyManager = None

        # LLM Advisor (optionnel)
        self.llm = LLMAdvisor(enabled=use_llm) if use_llm else None

        self._running = False
        _state['mode'] = mode
        _state['active_symbol'] = symbols[0] if symbols else ''

    def start(self):
        logger.info('═' * 60)
        logger.info('DTE Engine démarrage…')
        logger.info(f'  Symboles : {self.symbols}')
        logger.info(f'  Stratégie MM : {self.strategy}')
        logger.info(f'  Mode : {self.mode}')
        logger.info('═' * 60)

        if not self.provider.connect():
            logger.error('Impossible de se connecter à MT5. Arrêt.')
            return

        account = self.provider.get_account_info()
        balance = account.get('balance', 100.0)
        logger.info(f'Compte MT5 | Login: {account.get("login")} | Solde: {balance} {account.get("currency","USD")}')

        self.mm = MoneyManager(
            initial_capital=balance,
            strategy=self.strategy,
            base_risk_pct=0.01,
        )
        _state['account'] = account
        self._running = True

        try:
            self._loop()
        except KeyboardInterrupt:
            logger.info('Arrêt demandé (Ctrl+C)')
        finally:
            self._shutdown()

    def _loop(self):
        cycle = 0
        while self._running:
            cycle += 1
            cycle_start = time.time()

            # Relire le mode depuis l'état (modifiable par l'API)
            self.mode = _state.get('mode', self.mode)
            active_sym = _state.get('active_symbol', self.symbols[0])

            # Mise à jour compte
            if cycle % 30 == 0:
                acc = self.provider.get_account_info()
                if acc:
                    _state['account'] = acc

            # Traitement de chaque symbole
            all_signals = {}
            for symbol in self.symbols:
                sig_dict = self._process_symbol(symbol, is_active=(symbol == active_sym))
                if sig_dict:
                    all_signals[symbol] = sig_dict

            _state['signals'] = all_signals
            _state['mm_stats'] = self.mm.get_stats() if self.mm else {}
            _state['positions'] = self.provider.get_open_positions()
            _state['last_update'] = datetime.now().isoformat()

            write_state()

            # Essaie de notifier l'API FastAPI si elle tourne
            self._try_notify_api()

            elapsed = time.time() - cycle_start
            sleep = max(0.1, LOOP_SLEEP_SEC - elapsed)
            time.sleep(sleep)

    def _process_symbol(self, symbol: str, is_active: bool) -> dict:
        """Calcule le signal pour un symbole et exécute si nécessaire."""
        try:
            m1, m5, m15 = self.provider.get_all_timeframes(symbol)
            if m1 is None or len(m1) < 20:
                return None
            # H1 pour le Modèle E (Legacy Price Action) — optionnel
            h1 = self.provider.get_candles(symbol, 'H1', count=60)

            # Calcul signal composite (5 modèles)
            signal = self.fusions[symbol].compute(m1, m5, m15, h1=h1)
            sig_dict = self.fusions[symbol].to_dict(signal)

            # Optionnel : enrichissement LLM si score borderline
            if self.llm and is_active and 40 <= signal.score <= 65:
                acc = _state.get('account', {})
                llm_advice = self.llm.advise(sig_dict, account_balance=acc.get('balance', 0))
                sig_dict['llm'] = llm_advice
                # Ajuster le score si le LLM est confiant
                if llm_advice.get('llm_used') and not llm_advice.get('confirmed'):
                    sig_dict['action'] = 'WAIT'
                    logger.info(f'[LLM] Signal {symbol} annulé: {llm_advice.get("reason")}')

            # Log condensé
            action = sig_dict['action']
            score  = sig_dict['score']
            icon = '▲' if action == 'BUY' else ('▼' if action == 'SELL' else '—')
            sc = sig_dict["scores"]
            logger.info(f'{icon} {symbol:30s} | Score: {score:5.1f} | {action:5s} | '
                        f'A:{sc["A"]:4.0f} B:{sc["B"]:4.0f} C:{sc["C"]:4.0f} '
                        f'D:{sc["D"]:4.0f} E:{sc["E"]:4.0f} | Align:{sig_dict["alignment"]}')

            # Alerte spike
            if sig_dict.get('spike_alert') and sig_dict.get('spike_alert_level') in ('HAUTE', 'CRITIQUE'):
                add_alert(f'⚡ SPIKE {sig_dict["spike_alert_level"]} sur {symbol}', level='WARN')

            # Exécution si mode auto et signal actif
            if is_active and action != 'WAIT' and self.mode == 'FULL_AUTO':
                self._execute_trade(symbol, sig_dict, m1)
            elif is_active and action != 'WAIT' and self.mode == 'SEMI_AUTO':
                logger.info(f'[SEMI_AUTO] Signal {action} sur {symbol}. Confirmez dans le popup.')

            return sig_dict

        except Exception as e:
            logger.error(f'Erreur _process_symbol({symbol}): {e}', exc_info=True)
            return None

    def _execute_trade(self, symbol: str, sig_dict: dict, m1):
        """Exécution d'un trade — FULL_AUTO uniquement."""
        if not self.mm:
            return

        acc = self.provider.get_account_info()
        balance = acc.get('balance', 0)
        if balance <= 0:
            return

        # Calcul de la mise
        sizing = self.mm.get_position_size(
            signal_score=sig_dict['score'],
            win_prob=max(50.0, sig_dict['score']),
            rr_ratio=1.5,
        )

        if sizing.action != 'TRADE':
            logger.warning(f'[MM] {sizing.action}: {sizing.reason}')
            if sizing.action == 'STOP_SESSION':
                add_alert(f'⛔ SESSION STOPPÉE: {sizing.reason}', level='CRITIQUE')
                self.mode = 'SIGNAL_ONLY'
                _state['mode'] = 'SIGNAL_ONLY'
            return

        sl_pips = RECOMMENDED_SL_PIPS.get(symbol, 15.0)
        if sig_dict.get('reduce_size'):
            sl_pips *= 1.3  # Élargir le SL si alignement faible

        volume = self.provider.calculate_volume(symbol, sizing.amount, sl_pips)
        if volume <= 0:
            return

        direction = sig_dict['direction']
        action_str = 'BUY' if direction > 0 else 'SELL'
        comment = f'DTE_{symbol[:8]}_S{sig_dict["score"]:.0f}'

        # Vérification : pas de position déjà ouverte sur ce symbole
        existing = self.provider.get_open_positions(symbol)
        if existing:
            logger.info(f'Position déjà ouverte sur {symbol} — on skip')
            return

        result = self.provider.place_order(
            symbol=symbol,
            direction=action_str,
            volume=volume,
            sl_pips=sl_pips,
            comment=comment,
        )

        if result.get('success'):
            msg = f'✅ TRADE {action_str} {symbol} | Vol:{volume} | Prix:{result["price"]} | SL:{sl_pips}pips | Score:{sig_dict["score"]}'
            logger.info(msg)
            add_alert(msg, level='TRADE')
            _state['session_stats']['trades'] += 1
        else:
            logger.error(f'❌ Ordre refusé: {result.get("error")}')
            add_alert(f'❌ Ordre refusé: {result.get("error")}', level='ERROR')

    def _try_notify_api(self):
        """Tente de mettre à jour le state dans l'API FastAPI si elle tourne."""
        try:
            # Import conditionnel — l'API est optionnelle
            from api.main import set_state
            for k, v in _state.items():
                set_state(k, v)
        except Exception:
            pass

    def _shutdown(self):
        self._running = False
        logger.info('DTE Engine arrêt propre…')
        if self.provider:
            self.provider.disconnect()
        write_state()
        logger.info('DTE Engine arrêté.')


# ── Lancement de l'API FastAPI en thread séparé ───────────────────────────────
def start_api_server(host: str = '0.0.0.0', port: int = 8000):
    """Lance uvicorn en arrière-plan dans un thread daemon."""
    try:
        import uvicorn
        config = uvicorn.Config(
            'api.main:app',
            host=host,
            port=port,
            log_level='warning',
            reload=False,
        )
        server = uvicorn.Server(config)
        server.run()
    except ImportError:
        logger.warning('uvicorn non installé — API désactivée (pip install uvicorn)')
    except Exception as e:
        logger.warning(f'API server erreur: {e}')


# ── CLI ───────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description='DTE — Deriv Trading Ecosystem v1.0')
    p.add_argument('--symbol',   default='Crash 500 Index', help='Symbole actif principal')
    p.add_argument('--symbols',  default=None, nargs='+', help='Liste de symboles à surveiller')
    p.add_argument('--strategy', default='FLAT', choices=['FLAT', 'KELLY', 'MARTINGALE'])
    p.add_argument('--mode',     default='SIGNAL_ONLY', choices=['SIGNAL_ONLY', 'SEMI_AUTO', 'FULL_AUTO'])
    p.add_argument('--no-llm',   action='store_true', help='Désactiver le LLM advisor')
    p.add_argument('--no-api',   action='store_true', help='Ne pas lancer le serveur API')
    p.add_argument('--api-port', type=int, default=8000)
    p.add_argument('--all-symbols', action='store_true', help='Surveiller les 8 actifs')
    return p.parse_args()


def main():
    args = parse_args()

    if args.all_symbols:
        symbols = DEFAULT_SYMBOLS
    elif args.symbols:
        symbols = args.symbols
    else:
        symbols = [args.symbol]

    _state['active_symbol'] = symbols[0]
    _state['mode'] = args.mode

    # Lancer l'API FastAPI en arrière-plan
    if not args.no_api:
        api_thread = threading.Thread(
            target=start_api_server,
            kwargs={'port': args.api_port},
            daemon=True,
        )
        api_thread.start()
        logger.info(f'API FastAPI démarrée sur http://localhost:{args.api_port}')
        time.sleep(1.5)  # laisser le temps à uvicorn de démarrer

    engine = DTEEngine(
        symbols=symbols,
        strategy=args.strategy,
        mode=args.mode,
        use_llm=not args.no_llm,
    )
    engine.start()


if __name__ == '__main__':
    main()
