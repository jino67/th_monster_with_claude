import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
import json
# Assurez-vous d'avoir la nouvelle classe PriceActionAnalyzer ici
from core.price_action import PriceActionAnalyzer 
from utils.market_data_mt5 import fetch_h1 

class VolatilityStrategy:
    def __init__(self, config_path: str = "config/config_symbols_v2.json"):
        self.config = self.load_config(config_path)
        # Score d'entrée maintenu élevé
        self.min_score_entry = 70 
        self.pa = PriceActionAnalyzer()
        
    def load_config(self, config_path: str) -> Dict:
        try:
            with open(config_path, 'r') as f: return json.load(f)
        except: return {}

    def analyze_volatility_conditions(self, symbol: str, df_m1: pd.DataFrame, 
                                    df_m5: pd.DataFrame, df_m15: pd.DataFrame) -> Dict:
        
        # --- 1. CONTEXTE SUPERIEUR (H1) - LE JUGE DE PAIX ---
        df_h1 = fetch_h1(symbol, 50)
        trend_h1 = "NEUTRAL"
        
        if df_h1 is not None and len(df_h1) > 20:
            # Simple mais efficace : EMA 50
            ema_50 = df_h1['close'].ewm(span=50).mean().iloc[-1]
            current_h1 = df_h1['close'].iloc[-1]
            
            # Analyse Structure H1 (HH/HL)
            pa_h1 = self.pa.analyze_price_action(df_h1)
            struct_h1 = pa_h1['structure']['type']
            
            # Définition de la tendance H1 (Alignement EMA et Structure)
            if current_h1 > ema_50 and struct_h1 == "BULLISH_STRUCTURE":
                trend_h1 = "BULLISH"
            elif current_h1 < ema_50 and struct_h1 == "BEARISH_STRUCTURE":
                trend_h1 = "BEARISH"
                
        # --- 2. ANALYSE TACTIQUE (M5) - L'ENTRÉE ---
        pa_m5 = self.pa.analyze_price_action(df_m5)
        
        # On utilise les points de swing significatifs du M5 pour le sweep
        prev_low_swing = pa_m5['structure']['prev_low']
        prev_high_swing = pa_m5['structure']['prev_high']
        
        # --- 3. DÉTECTION "LIQUIDITY SWEEP" (Le Piège) ---
        # Maintenant plus précis grâce à PriceActionAnalyzer
        sweep_signal = "NONE"
        
        if len(df_m5) > 3 and prev_low_swing and prev_high_swing:
            curr = df_m5.iloc[-1]
            
            # Setup ACHAT : Le prix a cassé le dernier low significatif (piège) et remonte
            # Condition 1: Le low actuel a mordu le low de swing précédent
            # Condition 2: La bougie a clôturé en étant haussière (corps vert)
            if curr['low'] < prev_low_swing and curr['close'] > curr['open']:
                sweep_signal = "BULLISH_SWEEP"
            
            # Setup VENTE : Le prix a cassé le dernier high significatif (piège) et redescend
            # Condition 1: Le high actuel a mordu le high de swing précédent
            # Condition 2: La bougie a clôturé en étant baissière (corps rouge)
            elif curr['high'] > prev_high_swing and curr['close'] < curr['open']:
                sweep_signal = "BEARISH_SWEEP"

        # --- 4. CALCUL DU SCORE FINAL ---
        score = 0
        direction = "NEUTRAL"
        reason = "Waiting for setup..."
        
        # FILTRE PRINCIPAL : On ne trade que dans le sens du H1
        if trend_h1 == "BULLISH":
            direction = "BULLISH"
            
            # 4.1. Signal Primaire (Sweep)
            if sweep_signal == "BULLISH_SWEEP":
                score += 50 
                reason = "Liquidity Sweep in H1 Uptrend"
                
            # 4.2. Signal Secondaire (Continuation de Structure M5)
            elif pa_m5['structure']['type'] == "BULLISH_STRUCTURE":
                score += 30 
                reason = "M5 Continuation Structure in H1 Uptrend"
            
            # 4.3. Confirmations
            # Confirmation VWAP (Prix au-dessus du prix moyen pondéré par le volume)
            if df_m5['close'].iloc[-1] > pa_m5['vwap_value']: score += 20
            
            # Confirmation BOS (Break of Structure - Tendance accélère)
            if pa_m5['structure']['bos'] == "BULLISH_BOS": score += 10 # Petit boost
            
        elif trend_h1 == "BEARISH":
            direction = "BEARISH"
            
            # 4.1. Signal Primaire (Sweep)
            if sweep_signal == "BEARISH_SWEEP":
                score += 50
                reason = "Liquidity Sweep in H1 Downtrend"
                
            # 4.2. Signal Secondaire (Continuation de Structure M5)
            elif pa_m5['structure']['type'] == "BEARISH_STRUCTURE":
                score += 30
                reason = "M5 Continuation Structure in H1 Downtrend"
                
            # 4.3. Confirmations
            # Confirmation VWAP
            if df_m5['close'].iloc[-1] < pa_m5['vwap_value']: score += 20
            
            # Confirmation BOS
            if pa_m5['structure']['bos'] == "BEARISH_BOS": score += 10 # Petit boost
            
        else:
            # H1 est neutre ou contradictoire
            score = 0
            reason = "H1 Trend Unclear"

        # --- 5. GESTION DU RISQUE ---
        action = "HOLD"
        risk = 0.0
        
        if score >= self.min_score_entry:
            action = "BUY" if direction == "BULLISH" else "SELL"
            # Si c'est un SWEEP (50 points), le trade est considéré comme haute probabilité
            # Si le score >= 80 sans SWEEP, on peut aussi considérer un risque normal (ex: Structure + VWAP + BOS)
            if "SWEEP" in reason or score >= 80:
                risk = 1.0 # Risque Normal
            else:
                risk = 0.5 # Risque Réduit
                
        # --- 6. GESTION FVG (Objectifs Potentiels ou Zones de Réaction) ---
        # On pourrait ici intégrer l'analyse FVG pour définir le TP (Take Profit) ou le SL (Stop Loss)
        # Mais pour l'instant, on se contente de la renvoyer pour information
        
        return {
            'symbol': symbol,
            'action': action,
            'direction': direction,
            'confidence_score': min(1.0, score / 100), # S'assurer que le score est max 1.0
            'risk_adjustment': risk,
            'reason': f"{reason} (Score: {score})",
            'timestamp': datetime.now().isoformat()
        }