"""
DTE FastAPI Backend — API REST pour l'extension Chrome et le dashboard
Lance avec : uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations
import json
import time
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any

import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger('dte.api')

# ── Application ───────────────────────────────────────────────────────────────
app = FastAPI(
    title='Deriv Trading Ecosystem API',
    description='Backend REST pour le DTE — MT5 + Signaux + Dashboard',
    version='1.0.0',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=False,   # True + '*' = invalide CORS spec, navigateur bloque
    allow_methods=['*'],
    allow_headers=['*'],
)


class _PrivateNetworkMiddleware(BaseHTTPMiddleware):
    """Chrome Private Network Access (PNA) — requis depuis Chrome 98+.
    Les sites publics (deriv.com) ne peuvent appeler localhost que si le serveur
    répond Access-Control-Allow-Private-Network: true sur le preflight OPTIONS."""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers['Access-Control-Allow-Private-Network'] = 'true'
        return response


app.add_middleware(_PrivateNetworkMiddleware)


def _sanitize(obj):
    """Convertit récursivement les types numpy en types Python natifs (numpy.bool_ cause ValueError dans jsonable_encoder)."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj

# ── État partagé (mis à jour par dte_main.py via set_state) ──────────────────
_system_state: Dict[str, Any] = {
    'running': False,
    'mode': 'SIGNAL_ONLY',   # SIGNAL_ONLY | SEMI_AUTO | FULL_AUTO
    'active_symbol': 'Volatility 100 Index',
    'signals': {},            # symbol → CompositeSignal dict
    'account': {},
    'positions': [],
    'session_stats': {
        'trades': 0, 'wins': 0, 'losses': 0,
        'pnl': 0.0, 'win_rate': 0.0,
    },
    'mm_stats': {},
    'last_update': datetime.now().isoformat(),
    'alerts': [],
}

_websocket_clients: list = []


def set_state(key: str, value: Any):
    """Appelé depuis dte_main.py pour mettre à jour l'état."""
    _system_state[key] = value
    _system_state['last_update'] = datetime.now().isoformat()


def get_state() -> dict:
    return _system_state


# ── Modèles Pydantic ──────────────────────────────────────────────────────────
class ModeRequest(BaseModel):
    mode: str  # SIGNAL_ONLY | SEMI_AUTO | FULL_AUTO


class SymbolRequest(BaseModel):
    symbol: str


class TradeRequest(BaseModel):
    symbol: str
    direction: str      # BUY | SELL
    volume: float = 0.01
    sl_pips: float = 15.0
    tp_pips: float = 0.0
    comment: str = 'DTE_manual'


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get('/')
async def root():
    return {'status': 'ok', 'version': '1.0.0', 'timestamp': datetime.now().isoformat()}


@app.get('/api/status')
async def get_status():
    return {
        'running': _system_state['running'],
        'mode': _system_state['mode'],
        'active_symbol': _system_state['active_symbol'],
        'last_update': _system_state['last_update'],
    }


@app.get('/api/signal')
async def get_signal(symbol: Optional[str] = None):
    """Retourne le signal courant (pour un symbole ou tous)."""
    if symbol:
        sig = _system_state['signals'].get(symbol)
        if sig is None:
            return {'signal': None, 'message': f'Pas de signal pour {symbol}'}
        return {'signal': sig, 'timestamp': _system_state['last_update']}
    return {
        'signals': _system_state['signals'],
        'timestamp': _system_state['last_update'],
    }


@app.get('/api/account')
async def get_account():
    return _system_state.get('account', {})


@app.get('/api/positions')
async def get_positions():
    return {'positions': _system_state.get('positions', []), 'count': len(_system_state.get('positions', []))}


@app.get('/api/stats')
async def get_stats():
    return {
        'session': _system_state.get('session_stats', {}),
        'money_manager': _system_state.get('mm_stats', {}),
    }


@app.get('/api/alerts')
async def get_alerts():
    alerts = _system_state.get('alerts', [])
    return {'alerts': alerts[-50:], 'count': len(alerts)}


@app.post('/api/mode')
async def set_mode(req: ModeRequest):
    valid = ['SIGNAL_ONLY', 'SEMI_AUTO', 'FULL_AUTO']
    if req.mode not in valid:
        raise HTTPException(400, f'Mode invalide. Choisir parmi: {valid}')
    _system_state['mode'] = req.mode
    logger.info(f'Mode changé → {req.mode}')
    return {'success': True, 'mode': req.mode}


@app.post('/api/symbol')
async def set_symbol(req: SymbolRequest):
    _system_state['active_symbol'] = req.symbol
    return {'success': True, 'symbol': req.symbol}


@app.post('/api/emergency_stop')
async def emergency_stop():
    """Ferme toutes les positions et passe en SIGNAL_ONLY."""
    _system_state['mode'] = 'SIGNAL_ONLY'
    _system_state['running'] = False
    # Le dte_main.py détectera ce changement et fermera les positions
    _system_state['alerts'].append({
        'type': 'EMERGENCY_STOP',
        'timestamp': datetime.now().isoformat(),
        'message': 'EMERGENCY STOP activé via API',
    })
    return {'success': True, 'message': 'Emergency stop activé'}


@app.get('/api/full_state')
async def get_full_state():
    """Dump complet de l'état — pour l'extension Chrome."""
    return JSONResponse(content=_sanitize(_system_state))


# ── WebSocket pour push temps réel ───────────────────────────────────────────
@app.websocket('/ws')
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _websocket_clients.append(ws)
    try:
        while True:
            await ws.receive_text()  # keepalive
    except WebSocketDisconnect:
        _websocket_clients.remove(ws)


async def broadcast_state():
    """Appelé par dte_main.py pour pusher l'état aux clients WS."""
    dead = []
    safe = _sanitize(_system_state)
    for ws in _websocket_clients:
        try:
            await ws.send_json(safe)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _websocket_clients.remove(ws)
