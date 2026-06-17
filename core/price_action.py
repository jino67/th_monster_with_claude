import pandas as pd
import numpy as np
from typing import Dict, List, Optional

class PriceActionAnalyzer:
    """
    ANALYSEUR PRICE ACTION (SMC LITE)
    =================================
    Lecture de la structure (Fractals, HH/HL), VWAP et FVG.
    """

    def __init__(self):
        # Nombre de bougies pour définir un fractal (2 à gauche, 2 à droite)
        self.FRACTAL_WINDOW = 5

    def enrich_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ajoute les fractals et le VWAP au DataFrame"""
        df = df.copy()
        
        # 1. Calcul des Fractals (Sommets et Creux locaux sur 5 bougies)
        window = self.FRACTAL_WINDOW
        df['fractal_high'] = df['high'].rolling(window=window, center=True).max() == df['high']
        df['fractal_low'] = df['low'].rolling(window=window, center=True).min() == df['low']
        
        # 2. Calcul du VWAP (Volume Weighted Average Price)
        if 'tick_volume' in df.columns:
            v = df['tick_volume']
            tp = (df['high'] + df['low'] + df['close']) / 3
            # Le VWAP doit être calculé sur une période plus courte (ex: 100 bougies) ou le jour en cours
            # Ici, on utilise cumsum mais on pourrait le réinitialiser à chaque jour pour être plus précis
            df['vwap'] = (tp * v).cumsum() / v.cumsum()
        else:
            # Fallback si pas de volume : SMA 20 (moins précis, mais nécessaire)
            df['vwap'] = df['close'].rolling(20).mean()
            
        return df

    def get_last_swing_points(self, df: pd.DataFrame) -> Dict:
        """Récupère les prix et indices du dernier High et Low fractal significatifs."""
        
        # On ne regarde que les 50 dernières bougies pour la pertinence
        df_tail = df.iloc[-50:]
        
        # Récupère le dernier high
        high_fractals = df_tail[df_tail['fractal_high'] == True]
        last_high_val = high_fractals['high'].iloc[-1] if not high_fractals.empty else None
        last_high_idx = high_fractals.index[-1] if not high_fractals.empty else None
        
        # Récupère le dernier low
        low_fractals = df_tail[df_tail['fractal_low'] == True]
        last_low_val = low_fractals['low'].iloc[-1] if not low_fractals.empty else None
        last_low_idx = low_fractals.index[-1] if not low_fractals.empty else None
        
        # Pour le Liquidity Sweep (on a besoin du point précédent le plus récent)
        # On prend le 2ème dernier high/low significatif
        prev_high_val = high_fractals['high'].iloc[-2] if len(high_fractals) >= 2 else None
        prev_low_val = low_fractals['low'].iloc[-2] if len(low_fractals) >= 2 else None
        
        # On pourrait ajouter un filtre pour s'assurer que le swing point n'est pas trop proche de l'actuel
        
        return {
            'last_high': last_high_val,
            'last_low': last_low_val,
            'prev_high': prev_high_val,
            'prev_low': prev_low_val,
            'last_high_idx': last_high_idx,
            'last_low_idx': last_low_idx,
        }

    def detect_market_structure(self, df: pd.DataFrame) -> Dict:
        """
        Détermine la tendance par la structure des Fractals (HH/HL ou LH/LL)
        """
        
        swing_points = self.get_last_swing_points(df)
        
        last_high = swing_points['last_high']
        prev_high = swing_points['prev_high']
        last_low = swing_points['last_low']
        prev_low = swing_points['prev_low']
        
        structure = "NEUTRAL"
        strength = 0.0
        
        if prev_high and prev_low and last_high and last_low:
            # TENDANCE HAUSSIÈRE (Bullish Structure) : HH + HL
            if last_high > prev_high and last_low > prev_low:
                structure = "BULLISH_STRUCTURE"
                strength = 0.9 # Augmentation de la force
            
            # TENDANCE BAISSIÈRE (Bearish Structure) : LH + LL
            elif last_high < prev_high and last_low < prev_low:
                structure = "BEARISH_STRUCTURE"
                strength = 0.9
                
            # COMPRESSION / RANGE : Contraction de la volatilité
            elif last_high < prev_high and last_low > prev_low:
                structure = "COMPRESSION"
                strength = 0.5
            
            # EXPANSION (Megaphone) : Volatilité et incertitude
            elif last_high > prev_high and last_low < prev_low:
                structure = "EXPANSION"
                strength = 0.3
        
        # ⚠️ Détection du Break of Structure (BOS)
        # Le prix actuel a cassé le dernier HH (en haussier) ou LL (en baissier)
        bos = "NONE"
        current_close = df['close'].iloc[-1]
        
        # Cas 1: Possible BOS haussier
        if structure == "BULLISH_STRUCTURE" and current_close > last_high:
            bos = "BULLISH_BOS" # Continuation de tendance
            strength += 0.1
        
        # Cas 2: Possible BOS baissier
        elif structure == "BEARISH_STRUCTURE" and current_close < last_low:
            bos = "BEARISH_BOS" # Continuation de tendance
            strength += 0.1
            
        return {
            'type': structure,
            'strength': min(1.0, strength),
            'bos': bos, # Nouveau : Indique si la structure vient d'être cassée
            **swing_points
        }

    def detect_fair_value_gaps(self, df: pd.DataFrame) -> List[Dict]:
        """
        Détermine les Zones de Déséquilibre (FVG - Fair Value Gaps)
        """
        # (Aucun changement nécessaire ici, la logique est déjà correcte)
        fvgs = []
        lookback = 20
        start_idx = max(2, len(df) - lookback)
        
        for i in range(start_idx, len(df)):
            # BULLISH FVG : Espace entre High[i-2] et Low[i]
            if df['low'].iloc[i] > df['high'].iloc[i-2]:
                gap_size = df['low'].iloc[i] - df['high'].iloc[i-2]
                body_size = abs(df['close'].iloc[i-1] - df['open'].iloc[i-1])
                
                if gap_size > 0 and gap_size > (body_size * 0.1):
                    fvgs.append({
                        'type': 'BULLISH_FVG',
                        'top': df['low'].iloc[i],
                        'bottom': df['high'].iloc[i-2],
                        'index': i,
                        'filled': False
                    })
            
            # BEARISH FVG : Espace entre Low[i-2] et High[i]
            elif df['high'].iloc[i] < df['low'].iloc[i-2]:
                gap_size = df['low'].iloc[i-2] - df['high'].iloc[i]
                body_size = abs(df['close'].iloc[i-1] - df['open'].iloc[i-1])
                
                if gap_size > 0 and gap_size > (body_size * 0.1):
                    fvgs.append({
                        'type': 'BEARISH_FVG',
                        'top': df['low'].iloc[i-2],
                        'bottom': df['high'].iloc[i],
                        'index': i,
                        'filled': False
                    })
        
        return sorted(fvgs, key=lambda x: x['index'], reverse=True)

    def analyze_price_action(self, df: pd.DataFrame) -> Dict:
        """Fonction principale à appeler depuis la stratégie"""
        if df is None or len(df) < 20:
            return {'structure': {'type': 'UNKNOWN'}, 'fvgs': [], 'vwap_signal': 'NEUTRAL', 'vwap_value': 0.0, 'current_price': 0.0}
            
        # 1. Enrichissement
        df_rich = self.enrich_data(df)
        
        # 2. Structure
        structure = self.detect_market_structure(df_rich)
        
        # 3. FVG
        fvgs = self.detect_fair_value_gaps(df_rich)
        
        # 4. Signal VWAP
        current_price = df_rich['close'].iloc[-1]
        vwap = df_rich['vwap'].iloc[-1]
        vwap_signal = "BULLISH" if current_price > vwap else "BEARISH"
        
        return {
            'structure': structure, 
            'fvgs': fvgs,
            'vwap_signal': vwap_signal,
            'vwap_value': vwap,
            'current_price': current_price
        }