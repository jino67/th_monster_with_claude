import pandas as pd
import numpy as np
from typing import Dict, List, Optional

class PriceActionAnalyzer:
    """
    ANALYSEUR PRICE ACTION (SMC LITE)
    =================================
    Remplace les indicateurs retardataires (SMA, MACD) par la lecture de la structure.
    """

    def __init__(self):
        pass

    def enrich_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ajoute les fractals et le VWAP au DataFrame"""
        df = df.copy()
        
        # 1. Calcul des Fractals (Sommets et Creux locaux sur 5 bougies)
        # Un fractal High est un point plus haut que les 2 bougies avant et 2 après
        window = 5
        df['fractal_high'] = df['high'].rolling(window=window, center=True).max() == df['high']
        df['fractal_low'] = df['low'].rolling(window=window, center=True).min() == df['low']
        
        # 2. Calcul du VWAP (Volume Weighted Average Price)
        # C'est le "Vrai Prix" institutionnel
        if 'tick_volume' in df.columns:
            v = df['tick_volume']
            tp = (df['high'] + df['low'] + df['close']) / 3
            df['vwap'] = (tp * v).cumsum() / v.cumsum()
        else:
            # Fallback si pas de volume : SMA rapide
            df['vwap'] = df['close'].rolling(20).mean()
            
        return df

    def detect_market_structure(self, df: pd.DataFrame) -> Dict:
        """
        Détermine la tendance par la structure des Fractals (HH/HL ou LH/LL)
        """
        # On extrait uniquement les bougies qui sont des fractals
        highs = df[df['fractal_high'] == True]['high'].tail(5).values
        lows = df[df['fractal_low'] == True]['low'].tail(5).values
        
        structure = "UNCERTAIN"
        strength = 0.0
        
        if len(highs) >= 2 and len(lows) >= 2:
            last_high = highs[-1]
            prev_high = highs[-2]
            last_low = lows[-1]
            prev_low = lows[-2]
            
            # TENDANCE HAUSSIÈRE (Bullish Structure)
            # Higher High + Higher Low
            if last_high > prev_high and last_low > prev_low:
                structure = "BULLISH_STRUCTURE"
                strength = 0.8
            
            # TENDANCE BAISSIÈRE (Bearish Structure)
            # Lower High + Lower Low
            elif last_high < prev_high and last_low < prev_low:
                structure = "BEARISH_STRUCTURE"
                strength = 0.8
                
            # COMPRESSION / RANGE
            elif last_high < prev_high and last_low > prev_low:
                structure = "COMPRESSION" # Triangle
                strength = 0.3
            
            # EXPANSION (Megaphone)
            elif last_high > prev_high and last_low < prev_low:
                structure = "EXPANSION" # Volatilité dangereuse
                strength = 0.2
        
        return {
            'type': structure,
            'strength': strength,
            'last_high': highs[-1] if len(highs) > 0 else 0,
            'last_low': lows[-1] if len(lows) > 0 else 0
        }

    def detect_fair_value_gaps(self, df: pd.DataFrame) -> List[Dict]:
        """
        Détermine les Zones de Déséquilibre (FVG - Fair Value Gaps)
        Le prix revient souvent tester ces zones.
        """
        fvgs = []
        # Analyse des 20 dernières bougies
        lookback = 20
        start_idx = max(2, len(df) - lookback)
        
        for i in range(start_idx, len(df)):
            # BULLISH FVG : Espace entre High[i-2] et Low[i]
            # Bougie i-1 doit être une grande bougie verte
            if df['low'].iloc[i] > df['high'].iloc[i-2]:
                gap_size = df['low'].iloc[i] - df['high'].iloc[i-2]
                body_size = abs(df['close'].iloc[i-1] - df['open'].iloc[i-1])
                
                # Filtre : Le gap doit être significatif par rapport à la bougie
                if gap_size > 0 and gap_size > (body_size * 0.1):
                    fvgs.append({
                        'type': 'BULLISH_FVG',
                        'top': df['low'].iloc[i],
                        'bottom': df['high'].iloc[i-2],
                        'index': i,
                        'filled': False # On pourrait vérifier si le prix est revenu dedans
                    })
            
            # BEARISH FVG : Espace entre Low[i-2] et High[i]
            # Bougie i-1 doit être une grande bougie rouge
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
        
        # On retourne les FVG les plus récents en premier
        return sorted(fvgs, key=lambda x: x['index'], reverse=True)

    def analyze_price_action(self, df: pd.DataFrame) -> Dict:
        """Fonction principale à appeler depuis la stratégie"""
        if df is None or len(df) < 20:
            return {'structure': 'UNKNOWN', 'fvgs': [], 'vwap_signal': 'NEUTRAL'}
            
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
            'structure': structure, # Contient 'type' (ex: BULLISH_STRUCTURE)
            'fvgs': fvgs,           # Liste des zones magnétiques
            'vwap_signal': vwap_signal, # BULLISH ou BEARISH
            'vwap_value': vwap,
            'current_price': current_price
        }