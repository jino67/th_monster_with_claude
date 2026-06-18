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
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from colorama import init as _colorama_init, Fore, Style
_colorama_init()

# Ajout du root au path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.mt5_data_provider import MT5DataProvider, SYMBOL_MAP
from engine.signal_fusion import SignalFusion
from engine.money_manager import MoneyManager
from engine.llm_advisor import LLMAdvisor

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR = ROOT / 'logs'
LOG_DIR.mkdir(exist_ok=True)

_G  = Fore.GREEN   + Style.BRIGHT
_R  = Fore.RED     + Style.BRIGHT
_Y  = Fore.YELLOW
_C  = Fore.CYAN
_DM = Style.DIM
_BL = Fore.BLUE    + Style.BRIGHT
_RS = Style.RESET_ALL

class _ColorFmt(logging.Formatter):
    def format(self, record):
        msg = super().format(record)
        raw = record.getMessage()
        if '| Score:' in raw:
            if raw.startswith('▲'):   return f'{_G}{msg}{_RS}'
            if raw.startswith('▼'):   return f'{_R}{msg}{_RS}'
            return f'{_DM}{msg}{_RS}'
        if raw.startswith('TRADE '):   return f'{_G}{msg}{_RS}'
        if raw.startswith('[BE]') or raw.startswith('[TRAIL]'): return f'{_C}{msg}{_RS}'
        if raw.startswith('══') or raw.startswith('─'):  return f'{_C}{msg}{_RS}'
        if raw.startswith('[LLM]') or raw.startswith('[SEMI_AUTO]'): return f'{_C}{msg}{_RS}'
        if raw.startswith('DTE Engine') or raw.startswith('Compte MT5'): return f'{_BL}{msg}{_RS}'
        if record.levelno >= logging.ERROR:   return f'{_R}{msg}{_RS}'
        if record.levelno == logging.WARNING: return f'{_Y}{msg}{_RS}'
        return msg

class _SummaryFilter(logging.Filter):
    """Ne laisse passer que les logs dte.summary et les erreurs (console principale)."""
    def filter(self, record):
        return record.name == 'dte.summary' or record.levelno >= logging.ERROR

# File handler — tout (debug+info), plain text
_log_file = LOG_DIR / f'dte_{datetime.now():%Y%m%d}.log'
_fh = logging.FileHandler(_log_file, encoding='utf-8')
_fh.setFormatter(logging.Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s'))
_fh.setLevel(logging.DEBUG)

# Console handler — seulement le résumé et les erreurs, avec couleurs
_ch = logging.StreamHandler(sys.stdout)
_ch.setFormatter(_ColorFmt('%(asctime)s  %(message)s', datefmt='%H:%M:%S'))
_ch.addFilter(_SummaryFilter())

logging.basicConfig(level=logging.DEBUG, handlers=[_fh, _ch])
logger  = logging.getLogger('dte.main')     # détails → fichier uniquement
summary = logging.getLogger('dte.summary')  # résumé  → console uniquement

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

LOOP_SLEEP_SEC    = 2    # intervalle entre chaque cycle
SUMMARY_INTERVAL  = 300  # résumé console toutes les 5 minutes
MANAGE_INTERVAL   = 10   # gestion trailing/BE toutes les 10s

# ── Paramètres trailing stop / breakeven ─────────────────────────────────────
BE_TRIGGER              = 0.5  # déclenche BE quand profit ≥ 50% du SL structurel initial
TRAIL_TRIGGER           = 1.0  # déclenche trailing quand profit ≥ 100% du SL structurel initial
TRAIL_DISTANCE          = 0.5  # trail à 50% du SL structurel depuis le cours courant
PARTIAL_TRIGGER         = 1.5  # prise de partiel quand profit ≥ 150% du SL (RR 1.5)
PARTIAL_PCT             = 0.5  # ferme 50% du volume initial au partiel
MAX_POSITIONS_PER_SYMBOL = 2   # pyramiding autorisé jusqu'à N positions simultanées par symbole

# Symboles où on ignore le signal composite — entrée uniquement sur imminence de spike
SPIKE_ONLY_SYMBOLS = frozenset({
    'Crash 500 Index', 'Crash 1000 Index',
    'Boom 500 Index',  'Boom 1000 Index',
})

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
        self._order_cooldown: dict = {}
        self._order_cooldown_sec = 30
        self._last_summary  = 0.0   # timestamp du dernier résumé console
        self._last_manage   = 0.0   # timestamp de la dernière gestion des positions
        # Mémorise la distance SL structurelle ORIGINALE par ticket (avant auto-expansion et BE)
        # Utilisée pour que les triggers BE/trailing/partiel restent calibrés sur le SL initial
        self._pos_init_sl: dict = {}
        self._pos_partial_done: set = set()  # tickets ayant déjà eu leur prise de partiel

    def _open_log_window(self):
        """Ouvre un second terminal PowerShell qui suit le fichier de logs en temps réel."""
        try:
            CREATE_NEW_CONSOLE = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0x00000010)
            subprocess.Popen(
                ['powershell', '-NoExit', '-Command',
                 f'$Host.UI.RawUI.WindowTitle = "DTE — Logs détaillés"; '
                 f'Get-Content "{_log_file}" -Wait -Tail 80'],
                creationflags=CREATE_NEW_CONSOLE,
            )
        except Exception as e:
            summary.warning(f'Impossible d\'ouvrir la fenêtre de logs: {e}')

    def start(self):
        # Ouvrir la fenêtre de logs avant tout
        self._open_log_window()

        logger.info('═' * 60)
        logger.info('DTE Engine démarrage…')
        logger.info(f'  Symboles : {self.symbols}')
        logger.info(f'  Stratégie MM : {self.strategy}')
        logger.info(f'  Mode : {self.mode}')
        logger.info('═' * 60)

        summary.info(f'{"═"*60}')
        summary.info(f'  DTE v1.0 — {self.mode} | {len(self.symbols)} symboles | MM:{self.strategy}')
        summary.info(f'  Logs détaillés: fenêtre "DTE — Logs détaillés"')
        summary.info(f'  Résumé positions toutes les {SUMMARY_INTERVAL//60} minutes')
        summary.info(f'{"═"*60}')

        if not self.provider.connect():
            summary.error('Impossible de se connecter à MT5. Arrêt.')
            return

        account = self.provider.get_account_info()
        balance = account.get('balance', 100.0)
        logger.info(f'Compte MT5 | Login: {account.get("login")} | Solde: {balance} {account.get("currency","USD")}')
        summary.info(f'MT5 connecté | Login:{account.get("login")} | Solde:{balance} {account.get("currency","USD")}')

        self.mm = MoneyManager(
            initial_capital=balance,
            strategy=self.strategy,
            base_risk_pct=0.02,
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
            now   = time.time()
            cycle_start = now

            # Relire le mode
            self.mode  = _state.get('mode', self.mode)
            active_sym = _state.get('active_symbol', self.symbols[0])

            # Mise à jour compte toutes les 30 cycles
            if cycle % 30 == 0:
                acc = self.provider.get_account_info()
                if acc:
                    _state['account'] = acc

            # Gestion trailing stop / breakeven toutes les MANAGE_INTERVAL secondes
            if now - self._last_manage >= MANAGE_INTERVAL:
                self._manage_open_positions()
                self._last_manage = now

            # Traitement des signaux pour chaque symbole
            logger.info(f'{"─"*28} Cycle {cycle:04d}  [{self.mode}]  {datetime.now():%H:%M:%S} {"─"*8}')
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
            self._try_notify_api()

            # Résumé console toutes les SUMMARY_INTERVAL secondes
            if now - self._last_summary >= SUMMARY_INTERVAL:
                self._print_summary()
                self._last_summary = now

            elapsed = time.time() - cycle_start
            time.sleep(max(0.1, LOOP_SLEEP_SEC - elapsed))

    def _print_summary(self):
        """Affiche un résumé positions + PnL dans la fenêtre principale toutes les 5 min."""
        positions = self.provider.get_open_positions()
        acc       = self.provider.get_account_info()
        balance   = acc.get('balance', 0)
        equity    = acc.get('equity',  0)
        profit    = acc.get('profit',  0)
        n_trades  = _state.get('session_stats', {}).get('trades', 0)

        pl_c = _G if profit >= 0 else _R
        summary.info(f'{"═"*60}')
        summary.info(f'  {datetime.now():%H:%M:%S} | Balance:{balance:.2f}$ | Equity:{equity:.2f}$ | '
                     f'Session PnL:{pl_c}{profit:+.2f}${_RS} | Trades:{n_trades} | [{self.mode}]')
        if not positions:
            summary.info('  Aucune position ouverte')
        else:
            for p in positions:
                t   = 'BUY ' if p.get('type', 0) == 0 else 'SELL'
                pl  = p.get('profit', 0)
                sym = p.get('symbol', '')
                vol = p.get('volume', 0)
                pc  = _G if pl >= 0 else _R
                summary.info(f'  {t} {sym:30} Vol:{vol:.2f} | PnL:{pc}{pl:+.2f}${_RS}')
        summary.info(f'{"═"*60}')

    def _manage_open_positions(self):
        """Gestion active : Breakeven (profit≥50% SL) et Trailing Stop (profit≥100% SL).

        Le SL de référence pour les triggers est le SL STRUCTUREL INITIAL stocké dans
        _pos_init_sl, pas le SL courant MT5. Cela évite deux bugs :
          1. Après auto-expansion (×1.5–×3.375), le SL MT5 trop large → trigger jamais atteint
          2. Après BE, sl MT5 ≈ entry → sl_dist ≈ 0 → trailing uselessly serré
        """
        positions = self.provider.get_open_positions()

        # Nettoyage des tickets fermés
        open_tickets = {pos.get('ticket') for pos in positions}
        for t in list(self._pos_init_sl.keys()):
            if t not in open_tickets:
                del self._pos_init_sl[t]
        self._pos_partial_done -= (self._pos_partial_done - open_tickets)

        for pos in positions:
            ticket  = pos.get('ticket')
            is_buy  = pos.get('type', 0) == 0
            entry   = pos.get('price_open', 0.0)
            current = pos.get('price_current', entry)
            sl      = pos.get('sl',  0.0)
            tp      = pos.get('tp',  0.0)

            if entry == 0.0 or sl == 0.0:
                continue
            sl_dist_mt5 = abs(entry - sl)
            if sl_dist_mt5 < 1e-10:
                continue

            # SL de référence : structurel initial si connu, sinon SL MT5 courant
            ref_sl_dist = self._pos_init_sl.get(ticket, sl_dist_mt5)
            if ref_sl_dist < 1e-10:
                ref_sl_dist = sl_dist_mt5

            profit_dist = (current - entry) if is_buy else (entry - current)

            # ── Partial Take Profit ───────────────────────────────────────────
            if ticket not in self._pos_partial_done and profit_dist >= ref_sl_dist * PARTIAL_TRIGGER:
                full_vol    = pos.get('volume', 0.0)
                mt5_sym     = pos.get('symbol', '')
                specs       = self.provider._specs.get(mt5_sym, {})
                vol_min     = specs.get('volume_min', 0.01)
                partial_vol = round(full_vol * PARTIAL_PCT, 2)
                remain_vol  = round(full_vol - partial_vol, 2)
                if partial_vol >= vol_min and remain_vol >= vol_min:
                    res = self.provider.close_partial(ticket, partial_vol)
                    if res.get('success'):
                        self._pos_partial_done.add(ticket)
                        logger.info(
                            f'[PARTIAL] #{ticket} {pos["symbol"]} — {partial_vol:.2f}L clôturés '
                            f'({PARTIAL_PCT*100:.0f}%) | RR={PARTIAL_TRIGGER} | '
                            f'profit:{profit_dist:.4f} ≥ {ref_sl_dist*PARTIAL_TRIGGER:.4f}'
                        )
                        summary.info(
                            f'  [PARTIAL TP] #{ticket} {pos["symbol"]} — '
                            f'{partial_vol:.2f}L @ RR{PARTIAL_TRIGGER}'
                        )
                        # Forcer BE immédiatement après le partiel si SL encore sous l'entrée
                        buffer   = ref_sl_dist * 0.02
                        be_sl    = round((entry + buffer) if is_buy else (entry - buffer), 5)
                        needs_be = (is_buy and sl < be_sl - 1e-6) or (not is_buy and sl > be_sl + 1e-6)
                        if needs_be:
                            if self.provider.modify_position_sl(ticket, be_sl, tp):
                                logger.info(f'[PARTIAL→BE] #{ticket} SL forcé à {be_sl:.5f}')
                    else:
                        logger.warning(f'[PARTIAL] #{ticket} échec: {res.get("error")}')

            # ── Breakeven ─────────────────────────────────────────────────────
            if profit_dist >= ref_sl_dist * BE_TRIGGER:
                buffer = ref_sl_dist * 0.02
                be_sl  = round((entry + buffer) if is_buy else (entry - buffer), 5)
                needs_be = (is_buy and sl < be_sl - 1e-6) or (not is_buy and sl > be_sl + 1e-6)
                if needs_be and self.provider.modify_position_sl(ticket, be_sl, tp):
                    logger.info(f'[BE] #{ticket} {pos["symbol"]} → SL={be_sl:.5f} '
                                f'(profit:{profit_dist:.4f} ≥ {ref_sl_dist*BE_TRIGGER:.4f})')

            # ── Trailing Stop ─────────────────────────────────────────────────
            if profit_dist >= ref_sl_dist * TRAIL_TRIGGER:
                trail_dist = ref_sl_dist * TRAIL_DISTANCE
                new_sl = round(
                    (current - trail_dist) if is_buy
                    else (current + trail_dist), 5
                )
                needs_trail = (is_buy and new_sl > sl + 1e-6) or (not is_buy and new_sl < sl - 1e-6)
                if needs_trail and self.provider.modify_position_sl(ticket, new_sl, tp):
                    logger.info(f'[TRAIL] #{ticket} {pos["symbol"]} → SL={new_sl:.5f} '
                                f'(profit:{profit_dist:.4f} ≥ {ref_sl_dist*TRAIL_TRIGGER:.4f})')

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

            # Données de marché pour la projection chartographique (extension Chrome)
            if len(m1) > 14:
                hi = m1['high'].values; lo = m1['low'].values; cl = m1['close'].values
                tr = [max(float(hi[i]-lo[i]), abs(float(hi[i]-cl[i-1])), abs(float(lo[i]-cl[i-1])))
                      for i in range(1, 15)]
                sig_dict['atr_price']     = round(sum(tr) / len(tr), 8)
                sig_dict['current_price'] = float(cl[-1])
            mt5_sym = SYMBOL_MAP.get(symbol, symbol)
            sig_dict['point_size'] = float(self.provider._specs.get(mt5_sym, {}).get('point', 0.01))

            # Log condensé — couleurs via _ColorFmt (▲=vert, ▼=rouge, —=gris)
            action = sig_dict['action']
            score  = sig_dict['score']
            icon = '▲' if action == 'BUY' else ('▼' if action == 'SELL' else '—')
            sc = sig_dict["scores"]
            active_marker = '*' if is_active else ' '
            spike_lvl = sig_dict.get('spike_alert_level', '')
            spike_tag = f' ⚡{spike_lvl}' if spike_lvl in ('HAUTE', 'CRITIQUE') else ''
            logger.info(f'{icon}{active_marker}{symbol:29s} | Score:{score:5.1f} | {action:4s} | '
                        f'A:{sc["A"]:3.0f} B:{sc["B"]:3.0f} C:{sc["C"]:3.0f} '
                        f'D:{sc["D"]:3.0f} E:{sc["E"]:3.0f} | Aln:{sig_dict["alignment"]}{spike_tag}')

            if sig_dict.get('spike_alert') and spike_lvl in ('HAUTE', 'CRITIQUE'):
                add_alert(f'SPIKE {spike_lvl} sur {symbol}', level='WARN')

            # Exécution
            if symbol in SPIKE_ONLY_SYMBOLS:
                # Boom/Crash : on ne trade PAS les briques — uniquement les spikes imminents.
                # La direction est imposée par l'actif (Crash→SELL, Boom→BUY), indépendamment
                # du signal composite (qui serait pollué par les 90% de briques UP/DOWN).
                spike_lvl           = sig_dict.get('spike_alert_level', '')
                spike_just_happened = sig_dict.get('spike_alert', False)
                if not spike_just_happened and spike_lvl in ('HAUTE', 'CRITIQUE'):
                    if self.mode == 'FULL_AUTO':
                        self._execute_trade(symbol, self._build_spike_sig(symbol, sig_dict), m1, m5)
                    elif self.mode == 'SEMI_AUTO':
                        logger.info(f'[SEMI_AUTO] Spike {spike_lvl} imminent sur {symbol}. Confirmez.')
            else:
                if action != 'WAIT' and self.mode == 'FULL_AUTO':
                    self._execute_trade(symbol, sig_dict, m1, m5)
                elif action != 'WAIT' and self.mode == 'SEMI_AUTO':
                    logger.info(f'[SEMI_AUTO] Signal {action} sur {symbol}. Confirmez dans le popup.')

            return sig_dict

        except Exception as e:
            logger.error(f'Erreur _process_symbol({symbol}): {e}', exc_info=True)
            return None

    def _build_spike_sig(self, symbol: str, sig_dict: dict) -> dict:
        """Construit un sig_dict orienté spike pour Boom/Crash.

        Direction imposée par la nature de l'actif (Crash→SELL, Boom→BUY).
        Score = score_C (probabilité spike) pour un sizing calibré sur la confiance réelle.
        spike_alert=True → compute_sl_tp utilise min_rr=1.2 (trade court, spike rapide).
        """
        from engine.event_detector import SPIKE_STATS
        spike_dir  = SPIKE_STATS.get(symbol, {}).get('direction', 0)
        spike_score = sig_dict.get('scores', {}).get('C', 60.0)
        d = dict(sig_dict)
        d['direction']   = spike_dir
        d['action']      = 'BUY' if spike_dir > 0 else 'SELL'
        d['spike_alert'] = True    # → min_rr = 1.2 dans compute_sl_tp
        d['score']       = spike_score
        return d

    def _execute_trade(self, symbol: str, sig_dict: dict, m1, m5=None):
        """Exécution d'un trade — FULL_AUTO uniquement."""
        if not self.mm:
            return

        acc = self.provider.get_account_info()
        balance = acc.get('balance', 0)
        if balance <= 0:
            return

        score       = sig_dict['score']
        direction   = sig_dict['direction']
        action_str  = 'BUY' if direction > 0 else 'SELL'
        reduce_size = sig_dict.get('reduce_size', False)
        spike_alert = sig_dict.get('spike_alert', False)

        # ── SL/TP structurels (swing high/low M5/M1 + liquidité) ─────────────
        sl_tp = self.provider.compute_sl_tp_structural(
            symbol=symbol,
            direction=action_str,
            m1=m1,
            m5=m5,
            score=score,
            spike_alert=spike_alert,
        )
        sl_pips  = sl_tp['sl_pips']
        tp_pips  = sl_tp['tp_pips']
        rr       = sl_tp['rr_ratio']
        atr_p    = sl_tp['atr_pips']
        sl_price = sl_tp['sl_price']
        tp_price = sl_tp['tp_price']

        # ── Money Manager avec RR dynamique ──────────────────────────────────
        sizing = self.mm.get_position_size(
            signal_score=score,
            win_prob=max(50.0, score),
            rr_ratio=rr,
        )

        if sizing.action != 'TRADE':
            logger.warning(f'[MM] {sizing.action}: {sizing.reason}')
            if sizing.action == 'STOP_SESSION':
                add_alert(f'SESSION STOPPEE: {sizing.reason}', level='CRITIQUE')
                self.mode = 'SIGNAL_ONLY'
                _state['mode'] = 'SIGNAL_ONLY'
            return

        # ── Volume en lots, réduit si alignement faible ───────────────────────
        volume = self.provider.calculate_volume(symbol, sizing.amount, sl_pips)
        if volume <= 0:
            return
        if reduce_size:
            volume = round(volume * 0.75, 8)

        # Cooldown local — évite les doublons pendant la latence de confirmation MT5
        last_order_time = self._order_cooldown.get(symbol, 0)
        if time.time() - last_order_time < self._order_cooldown_sec:
            return

        # Vérification MT5 — limite de positions simultanées par symbole
        existing = self.provider.get_open_positions(symbol)
        if len(existing) >= MAX_POSITIONS_PER_SYMBOL:
            return

        # Marquer le cooldown AVANT l'envoi (bloque les cycles suivants même si MT5 est lent)
        self._order_cooldown[symbol] = time.time()

        comment = f'DTE_{symbol[:8]}_S{score:.0f}'
        result = self.provider.place_order(
            symbol=symbol,
            direction=action_str,
            volume=volume,
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            sl_price=sl_price,
            tp_price=tp_price,
            comment=comment,
        )

        if result.get('success'):
            actual_sl  = result.get('sl', sl_price)
            actual_tp  = result.get('tp', tp_price)
            actual_vol = result.get('volume', volume)
            actual_px  = result.get('price', 0.0)
            # Mémoriser la distance SL STRUCTURELLE initiale (avant toute expansion/BE)
            ticket = result.get('ticket')
            if ticket and sl_price > 0 and actual_px > 0:
                self._pos_init_sl[ticket] = abs(actual_px - sl_price)
            msg = (f'TRADE {action_str} {symbol} | Vol:{actual_vol:.2f} | Prix:{actual_px:.4f} '
                   f'| SL:{actual_sl:.4f} TP:{actual_tp:.4f} RR:{rr} ATR:{atr_p:.1f}p '
                   f'| Score:{score}{" [REDUIT]" if reduce_size else ""}')
            logger.info(msg)
            summary.info(f'{_G}TRADE{_RS} {action_str} {symbol} | Vol:{actual_vol:.2f} | RR:{rr} | Score:{score}')
            add_alert(msg, level='TRADE')
            _state['session_stats']['trades'] += 1
        else:
            err = result.get("error", "?")
            logger.error(f'Ordre refuse: {err} | {symbol} {action_str} SL={sl_price:.4f} TP={tp_price:.4f}')
            add_alert(f'Ordre refuse: {err}', level='ERROR')
            # On conserve le cooldown 30s même en cas d'échec pour éviter le spam

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
