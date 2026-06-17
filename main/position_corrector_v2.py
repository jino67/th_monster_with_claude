import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
from typing import Dict, List, Optional, Tuple
import json
import os

class SmartPositionCorrectorV2: # On garde le nom V2 pour ne pas casser les imports
    def __init__(self, adaptive_system):
        self.adaptive_system = adaptive_system
        self.correction_history = []
        self.data_dir = os.path.join("data_historical", "corrections")
        self.MAGIC_NUMBER = 999666 
        
        # --- PARAMÈTRES V3 DYNAMIQUES ---
        self.max_risk_equity_pct = 0.05  # Max perte par trade = 5% de l'équité (Urgence)
        self.hedge_trigger_equity_pct = 0.02 # Hedge si perte > 2%
        self.take_partial_trigger_r = 1.5 # Prendre partiel si Gain > 1.5x le Risque initial
        
        self._ensure_directory()
        self.load_correction_history()
        
    def _ensure_directory(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            
    def load_correction_history(self):
        try:
            history_file = os.path.join(self.data_dir, "position_corrections_v2.json")
            if os.path.exists(history_file):
                with open(history_file, 'r') as f:
                    self.correction_history = json.load(f)
        except Exception:
            self.correction_history = []
            
    def get_account_equity(self):
        """Récupère l'équité actuelle du compte"""
        acc = mt5.account_info()
        return acc.equity if acc else 100.0 # Valeur par défaut safe

    def monitor_and_correct_positions(self) -> List[Dict]:
        """Surveille et corrige toutes les positions (LOGIQUE V3)"""
        try:
            positions = mt5.positions_get()
            if not positions:
                return []
            
            corrections_applied = []
            equity = self.get_account_equity()
            
            for position in positions:
                if position.magic != self.MAGIC_NUMBER:
                    continue

                try:
                    # Analyse enrichie avec l'équité
                    correction = self.analyze_and_correct_position(position, equity)
                    if correction:
                        corrections_applied.append(correction)
                        self.log_correction(correction)
                except Exception as e:
                    print(f"❌ Erreur correction position {position.ticket}: {e}")
            
            return corrections_applied
            
        except Exception as e:
            print(f"❌ Erreur globale monitor: {e}")
            return []
            
    def analyze_and_correct_position(self, position, equity: float) -> Optional[Dict]:
        """Analyse V3 basée sur % Equity et Structure (CORRIGÉE)"""
        
        # --- CORRECTION ATTRIBUTS ---
        # On utilise getattr avec une valeur par défaut 0.0 pour éviter le crash
        profit = getattr(position, 'profit', 0.0)
        swap = getattr(position, 'swap', 0.0)
        commission = getattr(position, 'commission', 0.0)
        
        net_profit = profit + swap + commission
        
        entry_price = position.price_open
        current_price = position.price_current
        
        # Calcul du % de P&L par rapport au compte
        pl_percent = (net_profit / equity) * 100 if equity > 0 else 0
        
        # Récupération SL pour ratio
        risk_monetary = 0.0
        if position.sl > 0:
            if position.type == mt5.ORDER_TYPE_BUY:
                dist_sl = entry_price - position.sl
            else:
                dist_sl = position.sl - entry_price
            
            dist_current = abs(current_price - entry_price)
            if dist_current > 0:
                val_per_point = abs(profit) / dist_current
                risk_monetary = dist_sl * val_per_point
        
        # --- ARBRE DE DÉCISION V3 ---

        # 1. FERMETURE D'URGENCE
        if net_profit < -(equity * self.max_risk_equity_pct):
            return self.apply_emergency_close(position, "Max Equity Risk Hit")

        # 2. HEDGING DE SAUVETAGE
        if net_profit < -(equity * self.hedge_trigger_equity_pct) and "Hedge" not in position.comment:
            return self.apply_smart_hedge(position)

        # 3. TAKE PROFIT PARTIEL
        if risk_monetary > 0 and net_profit > (risk_monetary * 1.5) and "Partial" not in position.comment:
            return self.apply_partial_close(position, 0.5)

        # 4. BREAK-EVEN & TRAILING
        if pl_percent > 0.5:
             return self.apply_smart_trailing(position)

        return None
    
    def apply_smart_trailing(self, position) -> Optional[Dict]:
        """Trailing Stop basé sur l'ATR pour laisser respirer"""
        try:
            # On calcule un ATR rapide localement
            rates = mt5.copy_rates_from_pos(position.symbol, mt5.TIMEFRAME_M1, 0, 15)
            if rates is None: return None
            
            df = pd.DataFrame(rates)
            high, low, close = df['high'], df['low'], df['close']
            tr = np.maximum(high - low, np.abs(high - close.shift(1)))
            atr = tr.mean()
            
            current_price = position.price_current
            entry_price = position.price_open
            
            new_sl = 0.0
            
            if position.type == mt5.ORDER_TYPE_BUY:
                # Le SL traîne à 2 ATR derrière
                proposed_sl = current_price - (atr * 2.0)
                # On ne descend jamais le SL
                if proposed_sl > position.sl and proposed_sl > entry_price: 
                    new_sl = proposed_sl
                    
            elif position.type == mt5.ORDER_TYPE_SELL:
                proposed_sl = current_price + (atr * 2.0)
                # On ne remonte jamais le SL (pour un sell)
                if (position.sl == 0 or proposed_sl < position.sl) and proposed_sl < entry_price:
                    new_sl = proposed_sl
            
            if new_sl != 0.0:
                # Vérification distance minimale broker
                info = mt5.symbol_info(position.symbol)
                min_dist = info.trade_stops_level * info.point
                if abs(current_price - new_sl) < min_dist:
                    return None # Trop près

                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": position.ticket,
                    "symbol": position.symbol,
                    "sl": new_sl,
                    "tp": position.tp,
                    "magic": self.MAGIC_NUMBER
                }
                res = mt5.order_send(request)
                if res.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"🏃 Trailing V3 sur {position.symbol} (Locked)")
                    return {'type': 'trailing', 'ticket': position.ticket, 'time': datetime.now().isoformat()}
            
            return None
        except Exception:
            return None

    def apply_smart_hedge(self, position) -> Optional[Dict]:
        """Hedge intelligent avec vérification de marge"""
        # Vérification Marge Libre
        account = mt5.account_info()
        if account.margin_free < 10: # Si moins de 10$ de marge, on ne hedge pas (trop dangereux)
            print(f"⚠️ Impossible de hedger {position.symbol} : Marge insuffisante")
            return None

        print(f"🛡️ HEDGE V3 activé pour {position.symbol} (Protection Capital)")
        
        hedge_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(position.symbol).bid if hedge_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(position.symbol).ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume, # Hedge total
            "type": hedge_type,
            "price": price,
            "deviation": 20,
            "magic": self.MAGIC_NUMBER,
            "comment": f"Hedge_{position.ticket}", # Lien avec le parent
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        res = mt5.order_send(request)
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            return {'type': 'hedge', 'ticket': position.ticket, 'time': datetime.now().isoformat()}
        return None

    def apply_partial_close(self, position, ratio: float) -> Optional[Dict]:
        """Ferme une partie de la position pour sécuriser des gains"""
        # Calcul du volume à fermer
        vol_to_close = round(position.volume * ratio, 2)
        info = mt5.symbol_info(position.symbol)
        
        if vol_to_close < info.volume_min: 
            return None # Trop petit pour diviser
            
        print(f"💰 TAKE PROFIT PARTIEL V3 : {vol_to_close} lots sur {position.symbol}")
        
        close_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(position.symbol).bid if close_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(position.symbol).ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": position.ticket,
            "symbol": position.symbol,
            "volume": vol_to_close,
            "type": close_type,
            "price": price,
            "deviation": 20,
            "magic": self.MAGIC_NUMBER,
            "comment": f"Partial_{position.ticket}" # Marque le trade comme "déjà payé"
        }
        res = mt5.order_send(request)
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            return {'type': 'partial_tp', 'ticket': position.ticket, 'gain': vol_to_close, 'time': datetime.now().isoformat()}
        return None

    def apply_emergency_close(self, position, reason: str) -> Optional[Dict]:
        """Fermeture totale et immédiate"""
        print(f"🚨 FERMETURE URGENCE {position.symbol} : {reason}")
        
        close_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(position.symbol).bid if close_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(position.symbol).ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": position.ticket,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": close_type,
            "price": price,
            "deviation": 20,
            "magic": self.MAGIC_NUMBER,
            "comment": "Emergency_V3"
        }
        res = mt5.order_send(request)
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            return {'type': 'emergency', 'ticket': position.ticket, 'reason': reason, 'time': datetime.now().isoformat()}
        return None

    def log_correction(self, correction_info: Dict):
        self.correction_history.append(correction_info)
        if len(self.correction_history) % 5 == 0:
            self.save_correction_history()

    def save_correction_history(self):
        try:
            history_file = os.path.join(self.data_dir, "position_corrections_v2.json")
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(self.correction_history, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def update_correction_metrics(self, corrections):
        pass # Simplifié pour V3