import pandas as pd
import numpy as np
import os
from typing import Dict, List, Optional
from datetime import datetime
import json
# Importations nécessaires
from utils.market_data_mt5 import fetch_h1
# NOTE: Assurez-vous que les fonctions atr et rsi existent dans utils.indicators
from utils.indicators import atr, rsi 
# NOTE: La classe PriceActionAnalyzer doit contenir les fonctions améliorées 
# pour détecter les points de swing précis (prev_low, prev_high).
from core.price_action import PriceActionAnalyzer

class VolatilityStrategy:
    def __init__(self, config_path: str = "config/config_symbols_v2.json"):
        self.config = self.load_config(config_path)
        # PARAMÈTRE CLÉ : Seuil d'entrée de confiance
        self.min_score_entry = 60 
        self.pa = PriceActionAnalyzer()
        # PARAMÈTRE CLÉ : Seuil d'ATR en points (pour filtrer la faible volatilité)
        self.MIN_ATR_M5_POINTS = 50.0
        
    def load_config(self, config_path: str) -> Dict:
        """Charge la configuration du fichier JSON, avec fallback de chemin."""
        try:
            # Code pour gestion de chemin (omise ici pour la concision, si elle fonctionne)
            with open(config_path, 'r') as f: return json.load(f)
        except Exception:
            return {}

    def analyze_volatility_conditions(self, symbol: str, df_m1: pd.DataFrame,
                                      df_m5: pd.DataFrame, df_m15: pd.DataFrame) -> Dict:
        
        # Cas d'urgence : Données manquantes
        if df_m5 is None or len(df_m5) < 20 or df_m15 is None or len(df_m15) < 20:
            return {'symbol': symbol, 'action': 'HOLD', 'confidence_score': 0.0, 'risk_adjustment': 0.0, 'reason': 'Data Missing'}

        # --- 1. CONTEXTE SUPERIEUR (H1) - LE JUGE DE PAIX ---
        df_h1 = fetch_h1(symbol, 50)
        trend_h1 = "NEUTRAL"
        fvgs_h1 = [] # Pour stocker les FVG H1
        score = 0
        
        if df_h1 is not None and len(df_h1) > 50:
            # EMA 50
            ema_50 = df_h1['close'].ewm(span=50, adjust=False).mean().iloc[-1]
            current_h1 = df_h1['close'].iloc[-1]
            
            # Analyse Structure H1
            pa_h1 = self.pa.analyze_price_action(df_h1)
            struct_h1 = pa_h1.get('structure', {}).get('type', 'NEUTRAL_STRUCTURE')
            fvgs_h1 = pa_h1.get('fvgs', []) # Récupère les FVG H1
            
            # Définition de la tendance H1 (Alignement EMA et Structure)
            if current_h1 > ema_50 and struct_h1 == "BULLISH_STRUCTURE":
                trend_h1 = "BULLISH"
            elif current_h1 < ema_50 and struct_h1 == "BEARISH_STRUCTURE":
                trend_h1 = "BEARISH"
                
        # --- 2. FILTRE VOLATILITÉ ET MOMENTUM ---
        pa_m5 = self.pa.analyze_price_action(df_m5)
        
        # A. ATR M5 : Filtrer la faible volatilité
        atr_m5_value = atr(df_m5["close"], df_m5["high"], df_m5["low"], period=20).iloc[-1]
        
        # NOTE: La variable point_size doit être définie correctement par MT5
        # (Pour cet exemple, je définis un fallback pour ne pas bloquer le code)
        try:
            import MetaTrader5 as mt5
            symbol_info = mt5.symbol_info(symbol)
            point_size = symbol_info.point if symbol_info else 1e-5
        except:
             point_size = 1e-5 
             
        atr_m5_points = atr_m5_value / point_size

        if atr_m5_points < self.MIN_ATR_M5_POINTS:
            reason = f"Low Volatility Filter ({atr_m5_points:.0f} pts < {self.MIN_ATR_M5_POINTS} pts)"
            return {'symbol': symbol, 'action': 'HOLD', 'confidence_score': 0.0, 'risk_adjustment': 0.0, 'reason': reason}
        
        # B. RSI M15 : Filtre de surachat/survente
        rsi_m15 = rsi(df_m15['close'], period=14).iloc[-1]
        
        # --- 3. DÉTECTION "LIQUIDITY SWEEP" (Le Piège) - CODE FUSIONNÉ ET AMÉLIORÉ ---
        sweep_signal = "NONE"
        curr = df_m5.iloc[-1]
        
        # UTILISATION DU SWING SIGNIFICATIF (PRÉCISION STRUCTURELLE DE LA V2)
        prev_low_swing = pa_m5['structure'].get('prev_low')
        prev_high_swing = pa_m5['structure'].get('prev_high')
        
        if len(df_m5) > 3 and prev_low_swing is not None and prev_high_swing is not None:
            
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
        direction = "NEUTRAL"
        reason = "Waiting for setup..."
        
        current_low = df_m5.iloc[-1]['low']
        current_high = df_m5.iloc[-1]['high']
        
        # FILTRE PRINCIPAL : On ne trade que dans le sens du H1
        if trend_h1 == "BULLISH":
            direction = "BULLISH"
            
            if sweep_signal == "BULLISH_SWEEP":
                score += 50 
                reason = "Liquidity Sweep in Uptrend"
                
                # BONUS FVG H1 : Convergence (le prix tape dans un déséquilibre H1)
                for fvg in fvgs_h1:
                    # Le low actuel est entré dans la zone FVG BULLISH
                    if fvg['type'] == 'BULLISH_FVG' and current_low >= fvg['bottom'] and current_low <= fvg['top']:
                         score += 20 # Convergence majeure
                         reason += " + FVG H1 Hit"
                         break
            
            elif pa_m5.get('structure', {}).get('type', 'N/A') == "BULLISH_STRUCTURE":
                score += 30 # Continuation
                reason = "M5 Continuation in Uptrend"
                
            # Confirmation VWAP
            if df_m5['close'].iloc[-1] > pa_m5.get('vwap_value', -1): score += 20
            
            # Confirmation BOS (Break of Structure - Tendance accélère)
            if pa_m5['structure'].get('bos') == "BULLISH_BOS": score += 10
            
            # Ajustements RSI (Momentum)
            if rsi_m15 > 75: score -= 15; reason += " (RSI M15 High)" # PÉNALITÉ SURACHAT
            if rsi_m15 < 30: score += 10 # BONUS PULLBACK
            
        elif trend_h1 == "BEARISH":
            direction = "BEARISH"
            
            if sweep_signal == "BEARISH_SWEEP":
                score += 50
                reason = "Liquidity Sweep in Downtrend"
                
                # BONUS FVG H1 : Convergence
                for fvg in fvgs_h1:
                    # Le high actuel est entré dans la zone FVG BEARISH
                    if fvg['type'] == 'BEARISH_FVG' and current_high >= fvg['bottom'] and current_high <= fvg['top']:
                         score += 20 # Convergence majeure
                         reason += " + FVG H1 Hit"
                         break
            
            elif pa_m5.get('structure', {}).get('type', 'N/A') == "BEARISH_STRUCTURE":
                score += 30 # Continuation
                reason = "M5 Continuation in Downtrend"
                
            # Confirmation VWAP
            if df_m5['close'].iloc[-1] < pa_m5.get('vwap_value', 9e9): score += 20
            
            # Confirmation BOS
            if pa_m5['structure'].get('bos') == "BEARISH_BOS": score += 10
            
            # Ajustements RSI (Momentum)
            if rsi_m15 < 25: score -= 15; reason += " (RSI M15 Low)" # PÉNALITÉ SURVENTE
            if rsi_m15 > 70: score += 10 # BONUS PULLBACK
            
        else:
            # H1 NEUTRE : On autorise les Sweeps M5 pour du scalping (risque faible)
            reason = "H1 Trend Unclear / Low Confidence"
            
            # On vérifie seulement le Sweep, mais on s'assure qu'on ne va pas contre la structure M5
            if sweep_signal == "BULLISH_SWEEP" and pa_m5.get('structure', {}).get('type', 'N/A') != "BEARISH_STRUCTURE":
                score += 50
                direction = "BULLISH"
                reason = "Sweep (M5) in H1 Neutral"
            elif sweep_signal == "BEARISH_SWEEP" and pa_m5.get('structure', {}).get('type', 'N/A') != "BULLISH_STRUCTURE":
                score += 50
                direction = "BEARISH"
                reason = "Sweep (M5) in H1 Neutral"
            else:
                score = 0

        # --- 5. GESTION DU RISQUE ET ACTION FINALE ---
        action = "HOLD"
        risk = 0.0
        
        # Normalisation du score (max 100, ou 130 théorique avec tous les bonus)
        final_score = min(100, score)
        
        if final_score >= self.min_score_entry:
            action = "BUY" if direction == "BULLISH" else "SELL"
            
            # Ajustement du risque en fonction de la qualité du signal
            if "FVG H1 Hit" in reason and "Sweep" in reason:
                risk = 1.2 # Très haute probabilité (Sweep + FVG H1)
            elif "Sweep" in reason:
                risk = 1.0 # Haute probabilité
            elif final_score >= 80:
                 risk = 0.8 # Bonne continuation (VWAP + Structure + BOS)
            else: 
                risk = 0.5 # Risque modéré (Scénario continuation simple ou H1 neutre)

        return {
            'symbol': symbol,
            'action': action,
            'direction': direction,
            'confidence_score': final_score / 100,
            'risk_adjustment': risk,
            'reason': f"{reason} (Score: {final_score})",
            'timestamp': datetime.now().isoformat()
        }