import pandas as pd
import numpy as np
import os
from typing import Dict, List, Optional
from datetime import datetime
import json
# On a besoin de fetch_h1 pour le contexte
from utils.market_data_mt5 import fetch_h1
# AJOUT : Import des indicateurs nécessaires (ATR, RSI)
from utils.indicators import atr, rsi
# Note: La classe PriceActionAnalyzer est supposée exister dans core.price_action
from core.price_action import PriceActionAnalyzer

class VolatilityStrategy:
    def __init__(self, config_path: str = "config/config_symbols_v2.json"):
        self.config = self.load_config(config_path)
        # PARAMÈTRE CONFIGURABLE : Seuil d'entrée de confiance (ABAISSÉ de 70 à 60)
        self.min_score_entry = 60 
        self.pa = PriceActionAnalyzer()
        # PARAMÈTRE CONFIGURABLE : Seuil d'ATR en points (pour filtrer la faible volatilité)
        self.MIN_ATR_M5_POINTS = 50.0
        
    def load_config(self, config_path: str) -> Dict:
        try:
            # Tentative de chargement du chemin absolu
            if not os.path.exists(config_path):
                # Fallback pour le chemin relatif
                script_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.dirname(os.path.dirname(script_dir))
                config_path = os.path.join(project_root, config_path)
                
            with open(config_path, 'r') as f: return json.load(f)
        except Exception:
            # print(f"❌ Erreur de chargement config VolatilityStrategy: {e}")
            return {}

    def analyze_volatility_conditions(self, symbol: str, df_m1: pd.DataFrame,
                                      df_m5: pd.DataFrame, df_m15: pd.DataFrame) -> Dict:
        
        # Cas d'urgence : Données manquantes
        if df_m5 is None or len(df_m5) < 20 or df_m15 is None or len(df_m15) < 20:
            return {'action': 'HOLD', 'confidence_score': 0.0, 'risk_adjustment': 0.0, 'reason': 'Data Missing'}

        # --- 1. CONTEXTE SUPERIEUR (H1) - LE JUGE DE PAIX ---
        df_h1 = fetch_h1(symbol, 50)
        trend_h1 = "NEUTRAL"
        fvgs_h1 = [] # Intégration FVG H1

        if df_h1 is not None and len(df_h1) > 50:
            # EMA 50 (vision long-moyen terme)
            ema_50 = df_h1['close'].ewm(span=50, adjust=False).mean().iloc[-1]
            current_h1 = df_h1['close'].iloc[-1]
            
            # Analyse Structure H1 (HH/HL)
            pa_h1 = self.pa.analyze_price_action(df_h1)
            struct_h1 = pa_h1.get('structure', {}).get('type', 'NEUTRAL_STRUCTURE')
            fvgs_h1 = pa_h1.get('fvgs', []) # Récupère les FVG H1
            
            if current_h1 > ema_50 and struct_h1 == "BULLISH_STRUCTURE":
                trend_h1 = "BULLISH"
            elif current_h1 < ema_50 and struct_h1 == "BEARISH_STRUCTURE":
                trend_h1 = "BEARISH"
                
        # --- 2. FILTRE VOLATILITÉ ET MOMENTUM ---
        score = 0
        pa_m5 = self.pa.analyze_price_action(df_m5)
        
        # A. ATR M5 : Filtrer la faible volatilité (Exploitation des données M5)
        atr_m5_value = atr(df_m5["close"], df_m5["high"], df_m5["low"], period=20).iloc[-1]
        
        # Récupération de la taille du point (utiliser MT5 pour la précision)
        try:
            import MetaTrader5 as mt5
            symbol_info = mt5.symbol_info(symbol)
            point_size = symbol_info.point if symbol_info else 1e-5
        except:
            point_size = 1e-5 # Fallback 
            
        atr_m5_points = atr_m5_value / point_size

        if atr_m5_points < self.MIN_ATR_M5_POINTS:
            reason = f"Low Volatility Filter ({atr_m5_points:.0f} pts < {self.MIN_ATR_M5_POINTS} pts)"
            return {'action': 'HOLD', 'confidence_score': 0.0, 'risk_adjustment': 0.0, 'reason': reason}
        
        # B. RSI M15 : Filtre de surachat/survente (Exploitation des données M15)
        rsi_m15 = rsi(df_m15['close'], period=14).iloc[-1]
        
        # --- 3. DÉTECTION "LIQUIDITY SWEEP" (Le Piège) ---
        sweep_signal = "NONE"
        current_low = df_m5.iloc[-1]['low']
        current_high = df_m5.iloc[-1]['high']

        if len(df_m5) > 3:
            curr = df_m5.iloc[-1]
            # Utilisation du fractal pour la robustesse (Préférer un Low/High de structure si possible)
            prev_low_fractal = df_m5['low'].iloc[-10:-2].min()
            prev_high_fractal = df_m5['high'].iloc[-10:-2].max()
            
            # Setup ACHAT : Sweep Low (chasse aux stops) + Rejet
            if curr['low'] < prev_low_fractal and curr['close'] > curr['open']:
                sweep_signal = "BULLISH_SWEEP"
            
            # Setup VENTE : Sweep High (chasse aux stops) + Rejet
            elif curr['high'] > prev_high_fractal and curr['close'] < curr['open']:
                sweep_signal = "BEARISH_SWEEP"

        # --- 4. CALCUL DU SCORE FINAL ---
        direction = "NEUTRAL"
        reason = "Waiting for setup..."
        
        # FILTRE PRINCIPAL : On ne trade que dans le sens du H1
        if trend_h1 == "BULLISH":
            direction = "BULLISH"
            
            if sweep_signal == "BULLISH_SWEEP":
                score += 50 
                reason = "Liquidity Sweep in Uptrend"
                
                # NOUVEAU BONUS FVG H1 : Convergence (le prix tape dans un déséquilibre H1)
                for fvg in fvgs_h1:
                    if fvg['type'] == 'BULLISH_FVG' and current_low >= fvg['bottom'] and current_low <= fvg['top']:
                         score += 20 # Convergence majeure
                         reason += " + FVG H1 Hit"
                         break
            
            elif pa_m5.get('structure', {}).get('type', 'N/A') == "BULLISH_STRUCTURE":
                score += 30 # Continuation
                reason = "M5 Continuation in Uptrend"
                
            # Confirmation VWAP
            if df_m5['close'].iloc[-1] > pa_m5.get('vwap_value', -1): score += 20
            
            # Ajustements RSI (Reste inchangé)
            # PÉNALITÉ MOMENTUM : Éviter le surachat (RSI > 75)
            if rsi_m15 > 75: score -= 15; reason += " (RSI M15 High)"
            # BONUS PULLBACK : Achat à bon prix (RSI < 30)
            if rsi_m15 < 30: score += 10

        elif trend_h1 == "BEARISH":
            direction = "BEARISH"
            
            if sweep_signal == "BEARISH_SWEEP":
                score += 50
                reason = "Liquidity Sweep in Downtrend"
                
                # NOUVEAU BONUS FVG H1 : Convergence
                for fvg in fvgs_h1:
                    if fvg['type'] == 'BEARISH_FVG' and current_high >= fvg['bottom'] and current_high <= fvg['top']:
                         score += 20 # Convergence majeure
                         reason += " + FVG H1 Hit"
                         break
            
            elif pa_m5.get('structure', {}).get('type', 'N/A') == "BEARISH_STRUCTURE":
                score += 30 # Continuation
                reason = "M5 Continuation in Downtrend"
                
            # Confirmation VWAP
            if df_m5['close'].iloc[-1] < pa_m5.get('vwap_value', 9e9): score += 20
            
            # Ajustements RSI (Reste inchangé)
            # PÉNALITÉ MOMENTUM : Éviter la survente (RSI < 25)
            if rsi_m15 < 25: score -= 15; reason += " (RSI M15 Low)"
            # BONUS PULLBACK : Vente à bon prix (RSI > 70)
            if rsi_m15 > 70: score += 10
            
        else:
            # H1 NEUTRE : On autorise les Sweeps (mais avec un risque plus faible)
            reason = "H1 Trend Unclear / Low Confidence"
            
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
        
        # Normalisation du score (max 100, ou 120 théorique avec FVG)
        final_score = min(100, score)
        
        if final_score >= self.min_score_entry:
            action = "BUY" if direction == "BULLISH" else "SELL"
            
            # Ajustement du risque en fonction de la qualité du signal
            if "FVG H1 Hit" in reason:
                risk = 1.2 # Très haute probabilité (Sweep + FVG H1)
            elif "Sweep" in reason:
                risk = 1.0 # Haute probabilité
            elif final_score >= 80:
                 risk = 0.8 # Bonne continuation
            else: # Scénario continuation ou H1 neutre
                risk = 0.5 # Risque modéré/faible

        return {
            'symbol': symbol,
            'action': action,
            'direction': direction,
            'confidence_score': final_score / 100,
            'risk_adjustment': risk,
            'reason': f"{reason} (H1: {trend_h1} / ATR M5: {atr_m5_points:.0f} pts)",
            'timestamp': datetime.now().isoformat()
        }