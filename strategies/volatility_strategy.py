import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
import json
from core.price_action import PriceActionAnalyzer 
# On a besoin de fetch_h1 pour le contexte
from utils.market_data_mt5 import fetch_h1 

class VolatilityStrategy:
    def __init__(self, config_path: str = "config/config_symbols_v2.json"):
        self.config = self.load_config(config_path)
        # On augmente le seuil : on ne veut que la crème de la crème
        self.min_score_entry = 90 
        self.pa = PriceActionAnalyzer()
        
    def load_config(self, config_path: str) -> Dict:
        try:
            with open(config_path, 'r') as f: return json.load(f)
        except: return {}

    def analyze_volatility_conditions(self, symbol: str, df_m1: pd.DataFrame, 
                                    df_m5: pd.DataFrame, df_m15: pd.DataFrame) -> Dict:
        
        # --- 1. CONTEXTE SUPERIEUR (H1) - LE JUGE DE PAIX ---
        # On récupère le H1 pour connaitre la VRAIE tendance
        df_h1 = fetch_h1(symbol, 50)
        trend_h1 = "NEUTRAL"
        
        if df_h1 is not None and len(df_h1) > 20:
            # Simple mais efficace : EMA 50
            ema_50 = df_h1['close'].ewm(span=50).mean().iloc[-1]
            current_h1 = df_h1['close'].iloc[-1]
            
            # Analyse Structure H1 (HH/HL)
            pa_h1 = self.pa.analyze_price_action(df_h1)
            struct_h1 = pa_h1['structure']['type']
            
            if current_h1 > ema_50 and struct_h1 == "BULLISH_STRUCTURE":
                trend_h1 = "BULLISH"
            elif current_h1 < ema_50 and struct_h1 == "BEARISH_STRUCTURE":
                trend_h1 = "BEARISH"
                
        # --- 2. ANALYSE TACTIQUE (M5) - L'ENTRÉE ---
        pa_m5 = self.pa.analyze_price_action(df_m5)
        
        # --- 3. DÉTECTION "LIQUIDITY SWEEP" (Le Piège) ---
        # On cherche une bougie qui a mordu le plus bas précédent mais a clôturé au-dessus
        sweep_signal = "NONE"
        
        if len(df_m5) > 3:
            curr = df_m5.iloc[-1]
            prev = df_m5.iloc[-2]
            prev_low_fractal = df_m5['low'].iloc[-10:-2].min() # Le plus bas des 10 dernières bougies
            prev_high_fractal = df_m5['high'].iloc[-10:-2].max()
            
            # Setup ACHAT : Le prix a cassé un bas récent (piegé les vendeurs) et remonte
            if curr['low'] < prev_low_fractal and curr['close'] > curr['open']:
                sweep_signal = "BULLISH_SWEEP"
            
            # Setup VENTE : Le prix a cassé un haut récent (piegé les acheteurs) et redescend
            elif curr['high'] > prev_high_fractal and curr['close'] < curr['open']:
                sweep_signal = "BEARISH_SWEEP"

        # --- 4. CALCUL DU SCORE FINAL ---
        score = 0
        direction = "NEUTRAL"
        reason = "Waiting for setup..."
        
        # FILTRE PRINCIPAL : On ne trade que dans le sens du H1
        if trend_h1 == "BULLISH":
            # On cherche uniquement des achats
            if sweep_signal == "BULLISH_SWEEP":
                score += 50 # Gros signal : Sweep dans la tendance
                reason = "Liquidity Sweep in Uptrend"
            elif pa_m5['structure']['type'] == "BULLISH_STRUCTURE":
                score += 30 # Continuation
                
            # Confirmation VWAP
            if df_m5['close'].iloc[-1] > pa_m5['vwap_value']: score += 20
            
            direction = "BULLISH"
            
        elif trend_h1 == "BEARISH":
            # On cherche uniquement des ventes
            if sweep_signal == "BEARISH_SWEEP":
                score += 50
                reason = "Liquidity Sweep in Downtrend"
            elif pa_m5['structure']['type'] == "BEARISH_STRUCTURE":
                score += 30
                
            # Confirmation VWAP
            if df_m5['close'].iloc[-1] < pa_m5['vwap_value']: score += 20
            
            direction = "BEARISH"
            
        else:
            # H1 est neutre ou contradictoire -> On ne fait rien ou scalping très léger
            score = 0
            reason = "H1 Trend Unclear"

        # --- 5. GESTION DU RISQUE ---
        action = "HOLD"
        risk = 0.0
        
        if score >= self.min_score_entry:
            action = "BUY" if direction == "BULLISH" else "SELL"
            # Si c'est un SWEEP (Piège), c'est un trade haute probabilité -> Risque Normal
            # Si c'est juste une structure -> Risque Réduit
            risk = 1.0 if "SWEEP" in reason else 0.5

        return {
            'symbol': symbol,
            'action': action,
            'direction': direction,
            'confidence_score': score / 100,
            'risk_adjustment': risk,
            'reason': f"{reason} (H1: {trend_h1})",
            'timestamp': datetime.now().isoformat()
        }