"""
DTE Backtest — 6 mois de données historiques MT5
=================================================
Usage :
    python backtest/run_backtest.py
    python backtest/run_backtest.py --months 3 --symbols "Crash 500 Index,Boom 500 Index"
    python backtest/run_backtest.py --no-cache      # force re-téléchargement

Télécharge M1/M5/M15/H1, rejoue les 5 modèles DTE sans look-ahead,
calcule win rate, expectancy et courbe P&L par symbole.

Résultats : backtest/results/backtest_<date>.csv + rapport console.
"""
from __future__ import annotations
import os, sys, argparse, pickle, time, logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

# ── Chemin projet ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

# ── Config ─────────────────────────────────────────────────────────────────────
DEFAULT_MONTHS   = 6
STEP_M1          = 2        # évaluer le signal tous les N candles M1
MAX_HOLD_M1      = 300      # max candles avant timeout (~5h)
MIN_LOOKBACK     = 250      # candles M1 minimum pour initialiser les modèles
COOLDOWN_M1      = 30       # cooldown entre trades sur même symbole
SL_ATR_MULT      = 1.5      # SL = ATR × mult
MIN_SCORE        = 40.0
TICKS_PER_M1     = 60       # proxy : 1 min ≈ 60 ticks sur synthétiques Deriv

SPIKE_ONLY_SYMBOLS = frozenset({
    'Crash 500 Index', 'Crash 1000 Index',
    'Boom 500 Index',  'Boom 1000 Index',
})

ALL_SYMBOLS = [
    'Volatility 100 Index',
    'Volatility 100 (1s) Index',
    'Crash 500 Index',
    'Crash 1000 Index',
    'Boom 500 Index',
    'Boom 1000 Index',
    'Step Index',
    'Range Break 100 Index',
]

SYMBOL_MAP_MT5 = {
    'Volatility 100 Index':       'Volatility 100 Index',
    'Volatility 100 (1s) Index':  'Volatility 100 (1s) Index',
    'Crash 500 Index':            'Crash 500 Index',
    'Crash 1000 Index':           'Crash 1000 Index',
    'Boom 500 Index':             'Boom 500 Index',
    'Boom 1000 Index':            'Boom 1000 Index',
    'Step Index':                 'Step Index',
    'Range Break 100 Index':      'Range Break 100 Index',
}

CACHE_DIR   = ROOT / 'backtest' / 'cache'
RESULTS_DIR = ROOT / 'backtest' / 'results'

logging.basicConfig(level=logging.WARNING, format='%(message)s')


# ─────────────────────────────────────────────────────────────────────────────
# Téléchargement & cache
# ─────────────────────────────────────────────────────────────────────────────

def _connect_mt5() -> bool:
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print('ERROR: MetaTrader5 non installé (pip install MetaTrader5)')
        return False
    if not mt5.initialize():
        print(f'ERROR: mt5.initialize() échoué: {mt5.last_error()}')
        return False
    login = int(os.getenv('MT5_ACCOUNT_NUMBER', '0'))
    pwd   = os.getenv('MT5_PASSWORD', '')
    srv   = os.getenv('MT5_SERVER', 'DerivSVG-Server')
    if login and pwd:
        if not mt5.login(login, pwd, srv):
            print(f'ERROR: mt5.login() échoué: {mt5.last_error()}')
            mt5.shutdown()
            return False
    info = mt5.account_info()
    if info:
        print(f'  MT5 connecté | Login:{info.login} | Solde:{info.balance} {info.currency} | Serveur:{info.server}')
    else:
        print(f'  WARN: mt5.account_info() None — terminal peut-être non connecté au broker')
    return True


def _download_m1(symbol: str, months: int) -> Optional[pd.DataFrame]:
    """Utilise copy_rates_from_pos (position-based) — évite les problèmes de
    timezone avec copy_rates_range sur certaines versions du terminal MT5."""
    import MetaTrader5 as mt5
    mt5_sym = SYMBOL_MAP_MT5.get(symbol, symbol)
    if not mt5.symbol_select(mt5_sym, True):
        print(f'  WARN: symbol_select({mt5_sym}) échoué: {mt5.last_error()}')
        return None
    # 6 mois × 31 jours × 24h × 60min — synthétiques Deriv 24/7
    count = months * 31 * 24 * 60
    rates = mt5.copy_rates_from_pos(mt5_sym, mt5.TIMEFRAME_M1, 0, count)
    if rates is None or len(rates) == 0:
        print(f'  WARN: pas de données M1 pour {symbol} — {mt5.last_error()}')
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    df.set_index('time', inplace=True)
    df['body']  = df['close'] - df['open']
    df['range'] = df['high']  - df['low']
    return df


def _resample(m1: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {'open': 'first', 'high': 'max', 'low': 'min',
           'close': 'last', 'tick_volume': 'sum'}
    df = m1.resample(rule, label='left', closed='left').agg(agg).dropna()
    df['body']  = df['close'] - df['open']
    df['range'] = df['high']  - df['low']
    return df


def load_data(symbol: str, months: int, use_cache: bool = True) -> Optional[dict]:
    """Charge (ou télécharge + cache) M1/M5/M15/H1."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f'{symbol.replace(" ", "_")}_{months}m.pkl'

    if use_cache and cache_file.exists():
        age_days = (time.time() - cache_file.stat().st_mtime) / 86400
        if age_days < 1:
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
            print(f'  [{symbol}] données depuis cache')

    print(f'  [{symbol}] téléchargement {months} mois M1…', end=' ', flush=True)
    m1 = _download_m1(symbol, months)
    if m1 is None:
        return None
    print(f'{len(m1):,} bougies')

    data = {
        'M1':  m1,
        'M5':  _resample(m1, '5min'),
        'M15': _resample(m1, '15min'),
        'H1':  _resample(m1, '1h'),
    }
    with open(cache_file, 'wb') as f:
        pickle.dump(data, f)
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Outcome vectorisé (SL / TP)
# ─────────────────────────────────────────────────────────────────────────────

def check_outcome(
    highs: np.ndarray,
    lows:  np.ndarray,
    closes: np.ndarray,
    entry: float,
    sl: float,
    tp: float,
    is_buy: bool,
) -> tuple[str, float, int]:
    n = len(highs)
    if n == 0:
        return 'TIMEOUT', 0.0, 0

    if is_buy:
        sl_hit = lows  <= sl
        tp_hit = highs >= tp
    else:
        sl_hit = highs >= sl
        tp_hit = lows  <= tp

    sl_idx = int(np.argmax(sl_hit)) if sl_hit.any() else n
    tp_idx = int(np.argmax(tp_hit)) if tp_hit.any() else n

    if tp_idx < sl_idx:
        pnl = (tp - entry) if is_buy else (entry - tp)
        return 'WIN', pnl, tp_idx + 1
    if sl_idx < n:
        pnl = (sl - entry) if is_buy else (entry - sl)
        return 'LOSS', pnl, sl_idx + 1

    pnl = (closes[-1] - entry) if is_buy else (entry - closes[-1])
    return 'TIMEOUT', pnl, n


# ─────────────────────────────────────────────────────────────────────────────
# Boucle backtest par symbole
# ─────────────────────────────────────────────────────────────────────────────

def backtest_symbol(symbol: str, data: dict) -> list[dict]:
    from engine.signal_fusion import SignalFusion
    from engine.event_detector import SPIKE_STATS

    m1_full  = data['M1']
    m5_full  = data['M5']
    m15_full = data['M15']
    h1_full  = data['H1']

    # Index numpy pour searchsorted (timezone-naive comparison)
    m5_idx  = m5_full.index.view(np.int64)
    m15_idx = m15_full.index.view(np.int64)
    h1_idx  = h1_full.index.view(np.int64)

    m1_times_ns = m1_full.index.view(np.int64)

    # Données numpy (accès rapide)
    m1_open  = m1_full['open'].values
    m1_high  = m1_full['high'].values
    m1_low   = m1_full['low'].values
    m1_close = m1_full['close'].values

    fusion     = SignalFusion(symbol, n_mc_simulations=200, use_legacy=False)
    spike_stats = SPIKE_STATS.get(symbol, {})
    is_spike_only = symbol in SPIKE_ONLY_SYMBOLS

    trades        = []
    last_trade_i  = -COOLDOWN_M1
    m1_since_spike = 0

    total = (len(m1_full) - MIN_LOOKBACK) // STEP_M1
    done  = 0
    t0    = time.time()

    for i in range(MIN_LOOKBACK, len(m1_full) - MAX_HOLD_M1, STEP_M1):
        done += 1
        if done % 5000 == 0:
            elapsed = time.time() - t0
            eta = elapsed / done * (total - done)
            print(f'\r  [{symbol[:22]:22}] {done}/{total}  ETA {eta:.0f}s   ', end='', flush=True)

        current_time_ns = m1_times_ns[i - 1]

        # ── Fenêtres glissantes sans look-ahead ──────────────────────────────
        m1_slice  = m1_full.iloc[max(0, i - 200):i]

        m5_i  = int(np.searchsorted(m5_idx,  current_time_ns, side='right'))
        m15_i = int(np.searchsorted(m15_idx, current_time_ns, side='right'))
        h1_i  = int(np.searchsorted(h1_idx,  current_time_ns, side='right'))

        m5_slice  = m5_full.iloc[max(0, m5_i  - 150):m5_i]
        m15_slice = m15_full.iloc[max(0, m15_i - 100):m15_i]
        h1_slice  = h1_full.iloc[max(0, h1_i  - 60):h1_i]

        if len(m5_slice) < 5 or len(m15_slice) < 5:
            continue

        # ── Compteur spike M1-proxy pour Boom/Crash ───────────────────────────
        real_tick_counts: dict = {}
        if is_spike_only and spike_stats:
            if fusion.model_c.detect_spike_from_candles(m1_slice):
                m1_since_spike = 0
            else:
                m1_since_spike += STEP_M1
            real_tick_counts[symbol] = m1_since_spike * TICKS_PER_M1

        # ── Signal composite ──────────────────────────────────────────────────
        try:
            signal  = fusion.compute(m1_slice, m5_slice, m15_slice,
                                     h1=h1_slice, real_tick_counts=real_tick_counts)
            sig     = fusion.to_dict(signal)
        except Exception:
            continue

        action    = sig['action']
        score     = sig['score']
        spike_lvl = sig.get('spike_alert_level', '')
        spike_now = sig.get('spike_alert', False)

        # ── Décision d'entrée ─────────────────────────────────────────────────
        direction = 0
        entry_score = score

        if is_spike_only:
            if not spike_now and spike_lvl in ('HAUTE', 'CRITIQUE'):
                direction   = spike_stats.get('direction', 0)
                entry_score = sig['scores']['C']
        else:
            if action != 'WAIT' and score >= MIN_SCORE:
                direction = sig['direction']

        if direction == 0:
            continue
        if i - last_trade_i < COOLDOWN_M1:
            continue

        # ── Entrée à l'open de la bougie suivante (anti look-ahead) ──────────
        entry_price = float(m1_open[i])

        # ── SL / TP ATR-based ─────────────────────────────────────────────────
        atr = float(m1_slice['range'].tail(14).mean())
        if atr < 1e-10:
            continue

        rr = (1.2 if is_spike_only
              else 2.5 if entry_score >= 80
              else 2.0 if entry_score >= 65
              else 1.5)
        sl_dist = atr * SL_ATR_MULT
        tp_dist = sl_dist * rr
        is_buy  = direction > 0
        sl = entry_price - sl_dist if is_buy else entry_price + sl_dist
        tp = entry_price + tp_dist if is_buy else entry_price - tp_dist

        # ── Outcome vectorisé ─────────────────────────────────────────────────
        end_i  = min(i + MAX_HOLD_M1, len(m1_full))
        fut_hi = m1_high[i:end_i]
        fut_lo = m1_low[i:end_i]
        fut_cl = m1_close[i:end_i]

        outcome, pnl_pts, candles_held = check_outcome(
            fut_hi, fut_lo, fut_cl, entry_price, sl, tp, is_buy
        )

        pnl_r = pnl_pts / sl_dist if sl_dist > 0 else 0.0

        trades.append({
            'time':        m1_full.index[i - 1],
            'symbol':      symbol,
            'direction':   'BUY' if is_buy else 'SELL',
            'score':       round(entry_score, 1),
            'rr_target':   rr,
            'outcome':     outcome,
            'pnl_pts':     round(pnl_pts, 6),
            'pnl_r':       round(pnl_r, 3),
            'candles':     candles_held,
            'atr':         round(atr, 6),
            'spike_lvl':   spike_lvl,
            'score_A':     round(sig['scores']['A'], 1),
            'score_B':     round(sig['scores']['B'], 1),
            'score_C':     round(sig['scores']['C'], 1),
            'score_D':     round(sig['scores']['D'], 1),
        })
        last_trade_i = i

    print(f'\r  [{symbol[:22]:22}] terminé — {len(trades)} trades en {time.time()-t0:.0f}s')
    return trades


# ─────────────────────────────────────────────────────────────────────────────
# Rapport
# ─────────────────────────────────────────────────────────────────────────────

def _bar(v: float, width: int = 20) -> str:
    """Mini barre ASCII −width … +width."""
    mid = width // 2
    pos = int(min(max(v * mid, -mid), mid))
    bar = [' '] * width
    bar[mid] = '│'
    if pos > 0:
        for k in range(mid + 1, mid + pos + 1):
            bar[k] = '▓'
    elif pos < 0:
        for k in range(mid + pos, mid):
            bar[k] = '░'
    return ''.join(bar)


def print_report(all_trades: list[dict]) -> None:
    if not all_trades:
        print('\nAucun trade généré.')
        return

    df = pd.DataFrame(all_trades)
    n  = len(df)
    W  = df[df['outcome'] == 'WIN']
    L  = df[df['outcome'] == 'LOSS']
    T  = df[df['outcome'] == 'TIMEOUT']

    wr   = len(W) / n * 100
    exp  = df['pnl_r'].mean()
    pnl  = df['pnl_r'].sum()
    mdd  = _max_drawdown_r(df['pnl_r'].values)

    print('\n' + '═' * 72)
    print(f'  DTE BACKTEST — {n} trades | {df["symbol"].nunique()} symboles '
          f'| {df["time"].min().strftime("%Y-%m-%d")} → {df["time"].max().strftime("%Y-%m-%d")}')
    print('═' * 72)
    print(f'  Win rate     : {wr:.1f}%   ({len(W)}W / {len(L)}L / {len(T)}T)')
    print(f'  Expectancy   : {exp:+.3f}R  par trade')
    print(f'  P&L total    : {pnl:+.1f}R')
    print(f'  Max drawdown : {mdd:.1f}R')
    print()
    print(f'  {"Symbole":34} {"N":>5} {"Win%":>6} {"E(R)":>7}  {"Barre":20}  {"Verdict"}')
    print(f'  {"─"*34} {"─"*5} {"─"*6} {"─"*7}  {"─"*20}  {"─"*12}')

    by_sym = df.groupby('symbol')
    rows = []
    for sym, g in by_sym:
        n_s  = len(g)
        wr_s = len(g[g['outcome'] == 'WIN']) / n_s * 100
        e_s  = g['pnl_r'].mean()
        rows.append((sym, n_s, wr_s, e_s))
    rows.sort(key=lambda x: x[3], reverse=True)

    for sym, n_s, wr_s, e_s in rows:
        if e_s > 0.08:
            verdict = '✅ TRADE'
        elif e_s > 0.0:
            verdict = '⚠️  BORDERLINE'
        else:
            verdict = '❌ SKIP'
        bar = _bar(e_s / 0.5)
        print(f'  {sym:34} {n_s:>5} {wr_s:>5.1f}% {e_s:>+7.3f}R  {bar}  {verdict}')

    print()
    # Courbe P&L condensée (20 points)
    cumul = df['pnl_r'].cumsum().values
    step  = max(1, len(cumul) // 20)
    pts   = cumul[::step]
    mn, mx = pts.min(), pts.max()
    span = max(mx - mn, 0.1)
    bars = ''.join('▁▂▃▄▅▆▇█'[min(7, int((v - mn) / span * 7.99))] for v in pts)
    print(f'  P&L curve : {cumul[0]:.1f}R ── {bars} ── {cumul[-1]:.1f}R')
    print('═' * 72)


def _max_drawdown_r(pnl_r_array: np.ndarray) -> float:
    cumul = np.cumsum(pnl_r_array)
    peak  = np.maximum.accumulate(cumul)
    dd    = peak - cumul
    return float(dd.max()) if len(dd) > 0 else 0.0


def save_results(all_trades: list[dict]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime('%Y%m%d_%H%M')
    path = RESULTS_DIR / f'backtest_{ts}.csv'
    pd.DataFrame(all_trades).to_csv(path, index=False)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Entrée principale
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='DTE Backtest')
    parser.add_argument('--months',  type=int, default=DEFAULT_MONTHS)
    parser.add_argument('--symbols', type=str, default='',
                        help='Symboles séparés par virgule (défaut : tous)')
    parser.add_argument('--no-cache', action='store_true',
                        help='Force re-téléchargement depuis MT5')
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(',') if s.strip()] if args.symbols else ALL_SYMBOLS
    use_cache = not args.no_cache

    print(f'\n  DTE Backtest — {args.months} mois — {len(symbols)} symboles')
    print(f'  {"─"*50}')

    # Connexion MT5
    if not _connect_mt5():
        sys.exit(1)

    import MetaTrader5 as _mt5

    print('\n  [1/2] Téléchargement données…')
    datasets = {}
    for sym in symbols:
        data = load_data(sym, args.months, use_cache)
        if data is not None:
            datasets[sym] = data

    _mt5.shutdown()

    if not datasets:
        print('ERROR: aucune donnée disponible.')
        sys.exit(1)

    print(f'\n  [2/2] Simulation ({sum(len(d["M1"]) for d in datasets.values()):,} bougies M1 total)…\n')
    all_trades: list[dict] = []
    for sym, data in datasets.items():
        trades = backtest_symbol(sym, data)
        all_trades.extend(trades)

    print_report(all_trades)

    if all_trades:
        path = save_results(all_trades)
        print(f'\n  Résultats → {path}\n')


if __name__ == '__main__':
    main()
