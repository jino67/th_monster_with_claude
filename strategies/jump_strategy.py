import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import json
# IMPORT DU NOUVEAU CERVEAU SMART MONEY
# Assurez-vous que cette classe PriceActionAnalyzer est définie dans core/price_action.py
from core.price_action import PriceActionAnalyzer 

class JumpStrategy:
    def __init__(self, config_path: str = "config/config_symbols_v2.json"):
        self.config = self.load_config(config_path)
        self.jump_threshold = 0.08      # 8% pour détecter un jump (INCHANGÉ)
        self.retracement_threshold = 0.03 # 3% pour la confirmation (INCHANGÉ)
        self.performance_history = []
        
        # Initialisation de l'analyseur Price Action
        self.pa = PriceActionAnalyzer()
        
        # --- PARAMÈTRES OPTIMISÉS V5 ---
        # 1. Lookback M1 réduit pour une réactivité maximale
        self.M1_MOMENTUM_LOOKBACK = 8 
        # 2. Lookback M5 ajusté pour un contexte court terme plus stable
        self.M5_MOMENTUM_LOOKBACK = 25
        # 3. Période RSI réduite pour les indices Jump (plus de réactivité au momentum)
        self.RSI_PERIOD = 9 
        # 4. Seuils de volatilité ajustés (hypothèse : indice à très haute volatilité, type VIX/Jump 100)
        self.VOLATILITY_HIGH_THRESHOLD = 0.35 
        self.VOLATILITY_MID_THRESHOLD = 0.20 
        self.VOLATILITY_CALM_THRESHOLD = 0.10 
        # -----------------------------
        
    def load_config(self, config_path: str) -> Dict:
        """Charge la configuration des symboles"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Fichier de configuration {config_path} non trouvé")
            return {}
    
    def analyze_jump_conditions(self, symbol: str, df_m1: pd.DataFrame,
                                df_m5: pd.DataFrame, df_m15: pd.DataFrame, 
                                df_h1: pd.DataFrame) -> Dict:
        """Analyse les conditions spécifiques aux indices Jump (VERSION V5 SMART MONEY H1 OPTIMISÉE)"""
        
        # 1. Détection des jumps
        jump_analysis = self.detect_jumps(df_m5, df_m15)
        
        # 2. Momentum post-jump (utilise les lookbacks optimisés)
        momentum_analysis = self.analyze_post_jump_momentum(df_m1, df_m5)
        
        # 3. Structure de prix M15
        price_structure = self.analyze_price_structure(df_m15)
        
        # 4. Volatilité (utilise les seuils optimisés)
        volatility_profile = self.analyze_jump_volatility(df_m1, df_m5)
        
        # --- ANALYSE PRICE ACTION (SMC) ---
        pa_analysis_m5 = self.pa.analyze_price_action(df_m5)
        pa_analysis_h1 = self.pa.analyze_price_action(df_h1)
        
        # 5. Opportunité de trading (méthode de scoring optimisée)
        trading_opportunity = self.assess_jump_opportunity_v5_optimized(
            symbol, jump_analysis, momentum_analysis, price_structure, 
            volatility_profile, pa_analysis_m5, pa_analysis_h1, df_m1, df_m5
        )
        
        return {
            'symbol': symbol,
            'trading_opportunity': trading_opportunity,
            'action': trading_opportunity['action'],            
            'recommended_action': trading_opportunity['action'], 
            'confidence_score': trading_opportunity['confidence'],
            'risk_adjustment': trading_opportunity['risk_adjustment'],
            'timestamp': datetime.now().isoformat()
        }
    
    def assess_jump_opportunity_v5_optimized(self, symbol: str, jump_analysis: Dict,
                                         momentum_analysis: Dict, price_structure: Dict,
                                         volatility_profile: Dict, pa_m5: Dict, 
                                         pa_h1: Dict,
                                         df_m1: pd.DataFrame, df_m5: pd.DataFrame) -> Dict:
        """
        Évaluation V5 Optimisée : Seuils d'entrée plus stricts.
        """
        score = 0
        
        direction = momentum_analysis['m5_momentum']['direction']
        
        # --- PILIER 0 : FILTRE H1 (35 points) ---
        h1_structure = pa_h1.get('structure', {}).get('type', 'RANGING')
        h1_aligned = False
        
        # 1. Alignement de la Structure H1
        if direction == "BULLISH":
            if h1_structure in ["BULLISH_STRUCTURE", "RANGING"]:
                h1_aligned = True
            elif h1_structure == "BEARISH_STRUCTURE":
                score -= 40 # PÉNALITÉ MAJEURE AUGMENTÉE
        
        elif direction == "BEARISH":
            if h1_structure in ["BEARISH_STRUCTURE", "RANGING"]:
                h1_aligned = True
            elif h1_structure == "BULLISH_STRUCTURE":
                score -= 40 # PÉNALITÉ MAJEURE AUGMENTÉE
    
        if h1_aligned:
            score += 35 # BONUS LÉGÈREMENT AUGMENTÉ
        
        # --- PILIER 1 : MOMENTUM M5/M1 (45 points max) ---
        mom_strength = momentum_analysis['momentum_strength']
        
        # Seuil de force MOMENTUM remonté
        if mom_strength > 0.7: score += 45 # Exige un momentum M5 plus fort
        elif mom_strength > 0.5: score += 30
        elif mom_strength > 0.3: score += 10
        
        if momentum_analysis['momentum_alignment'] == "ALIGNED":
            score += 5 # Bonus léger (timing fin)

        # --- PILIER 2 : PRICE ACTION M5 (Structure & VWAP) (20 points) ---
        structure_type_m5 = pa_m5.get('structure', {}).get('type', 'UNKNOWN')
        
        if direction == "BULLISH":
            if structure_type_m5 == "BULLISH_STRUCTURE": score += 10
            if pa_m5.get('vwap_signal') == "BULLISH": score += 10
            
        elif direction == "BEARISH":
            if structure_type_m5 == "BEARISH_STRUCTURE": score += 10
            if pa_m5.get('vwap_signal') == "BEARISH": score += 10

        # --- PILIER 3 : VOLATILITÉ (10 points) ---
        volatility_profile = self.analyze_jump_volatility(df_m1, df_m5)
        vol_regime = volatility_profile.get('volatility_regime', 'JUMP_NORMAL')
        
        if vol_regime in ["JUMP_EXPANSION", "JUMP_NORMAL"]:
            score += 10
        elif vol_regime == "JUMP_CALM":
            score -= 15 # Pénalité augmentée si marché trop calme
        elif vol_regime in ["JUMP_IMMINENT", "HIGH_JUMP_RISK"]:
             score -= 5 # Réduction légère si c'est risqué, mais pas éliminatoire

        # --- DÉCISION FINALE ---
        score = max(0, min(100, score)) # Borner 0-100
        action = "HOLD"
        risk_adjustment = 0.0
        
        # SEUIL D'ENTRÉE GLOBAL REMONTÉ
        if score >= 75: 
            action = "BUY" if direction == "BULLISH" else "SELL"
            
            # Gestion du risque intelligente OPTIMISÉE
            if score >= 90:
                risk_adjustment = 1.0     # H1 Alignement parfait + Momentum/VWAP/Structure M5 très fort
            elif score >= 80: # Seuil pour 0.75 remonté à 80
                risk_adjustment = 0.75    # H1 Alignement + Bon Momentum/Structure M5
            else:
                risk_adjustment = 0.5     # Entrée spéculative, mais direction H1/M5 OK
        
        return {
            'action': action,
            'direction': direction,
            'confidence': score / 100,
            'risk_adjustment': risk_adjustment,
            'reason': f"V5 Opt Score: {score} (H1 Struct: {h1_structure} | M5 Struct: {structure_type_m5} | Mom: {mom_strength:.2f})"
        }
    
    # --- MÉTHODES UTILITAIRES MODIFIÉES / COMPLÈTES ---
    
    def calculate_momentum(self, df: pd.DataFrame, lookback: int) -> Dict:
        """Calcule les indicateurs de momentum (utilise self.RSI_PERIOD)"""
        if len(df) < lookback:
            return {'rsi': 50, 'macd_hist': 0, 'velocity': 0, 'direction': 'RANGING'}
        
        close = df['close']
        
        # RSI - UTILISE self.RSI_PERIOD = 9
        rsi = self.calculate_rsi(close, self.RSI_PERIOD).iloc[-1] if len(close) >= self.RSI_PERIOD else 50
        
        # MACD Histogram
        macd_hist = self.calculate_macd_histogram(close).iloc[-1] if len(close) >= 26 else 0
        
        # Velocity (taux de changement) - UTILISE lookback DYNAMIQUE
        price_change = (close.iloc[-1] - close.iloc[-lookback]) / close.iloc[-lookback] * 100
        velocity = price_change / lookback 
        
        return {
            'rsi': rsi,
            'macd_hist': macd_hist,
            'velocity': velocity,
            'direction': 'BULLISH' if velocity > 0 else 'BEARISH'
        }

    def analyze_post_jump_momentum(self, df_m1: pd.DataFrame, df_m5: pd.DataFrame) -> Dict:
        """Analyse le momentum après un jump (utilise lookbacks optimisés)"""
        # Momentum à très court terme (M1) - UTILISE self.M1_MOMENTUM_LOOKBACK = 8
        m1_momentum = self.calculate_momentum(df_m1, self.M1_MOMENTUM_LOOKBACK) 
        
        # Momentum à court terme (M5) - UTILISE self.M5_MOMENTUM_LOOKBACK = 25
        m5_momentum = self.calculate_momentum(df_m5, self.M5_MOMENTUM_LOOKBACK) 
        
        momentum_alignment = self.assess_momentum_alignment(m1_momentum, m5_momentum)
        momentum_strength = self.calculate_momentum_strength(m1_momentum, m5_momentum)
        
        return {
            'm1_momentum': m1_momentum,
            'm5_momentum': m5_momentum,
            'momentum_alignment': momentum_alignment,
            'momentum_strength': momentum_strength,
            'trend_continuation': self.assess_trend_continuation(m1_momentum, m5_momentum)
        }
    
    def classify_jump_volatility_regime(self, volatility: float, vol_ratio: float) -> str:
        """Classifie le régime de volatilité pour les indices Jump (utilise les seuils optimisés)"""
        # Seuil OPTIMISÉ (hypothèse : indice très volatile)
        if volatility > self.VOLATILITY_HIGH_THRESHOLD and vol_ratio > 1.5:
            return "JUMP_IMMINENT"
        # Seuil OPTIMISÉ
        elif volatility > self.VOLATILITY_MID_THRESHOLD and vol_ratio > 1.2:
            return "HIGH_JUMP_RISK"
        # Seuil OPTIMISÉ
        elif volatility < self.VOLATILITY_CALM_THRESHOLD and vol_ratio < 0.8:
            return "JUMP_CALM"
        elif vol_ratio > 1.3:
            return "JUMP_EXPANSION"
        else:
            return "JUMP_NORMAL"

    def calculate_rsi(self, series: pd.Series, period: int) -> pd.Series:
        """Calcule l'Indice de Force Relative (RSI)"""
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        # Utilisation de ewm pour un RSI classique
        avg_gain = gain.ewm(span=period, adjust=False).mean() 
        avg_loss = loss.ewm(span=period, adjust=False).mean()

        with np.errstate(divide='ignore', invalid='ignore'):
            rs = avg_gain / avg_loss
            
        rs.replace([np.inf, -np.inf], np.nan, inplace=True)
        rs.fillna(1, inplace=True) 
        
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_macd_histogram(self, series: pd.Series) -> pd.Series:
        """Calcule l'histogramme MACD"""
        ema_12 = series.ewm(span=12, adjust=False).mean()
        ema_26 = series.ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal
        return histogram

    def assess_momentum_alignment(self, m1_momentum: Dict, m5_momentum: Dict) -> str:
        """Évalue l'alignement de la direction M1 vs M5"""
        m1_dir = m1_momentum['direction']
        m5_dir = m5_momentum['direction']
        
        if m1_dir == m5_dir and m1_dir != 'RANGING':
            return "ALIGNED"
        else:
            return "DIVERGENT"

    def calculate_momentum_strength(self, m1_momentum: Dict, m5_momentum: Dict) -> float:
        """Calcule une force de momentum agrégée (0 à 1)"""
        # Utilisation de M1 seulement pour la force immédiate
        rsi_strength = (abs(m1_momentum['rsi'] - 50) / 50) * 0.4
        macd_strength = min(abs(m1_momentum['macd_hist']) * 10, 1) * 0.3
        velocity_strength = min(abs(m1_momentum['velocity']) * 10, 1) * 0.3
        
        return rsi_strength + macd_strength + velocity_strength
    
    def assess_trend_continuation(self, m1_momentum: Dict, m5_momentum: Dict) -> bool:
        """Détermine si le trend est en continuation (alignement + force suffisante)"""
        return (self.assess_momentum_alignment(m1_momentum, m5_momentum) == "ALIGNED" and 
                self.calculate_momentum_strength(m1_momentum, m5_momentum) > 0.6)
    
    def analyze_jump_volatility(self, df_m1: pd.DataFrame, df_m5: pd.DataFrame) -> Dict:
        """Analyse la volatilité spécifique aux indices Jump"""
        m1_volatility = self.calculate_volatility(df_m1['close'], 10)
        m5_volatility = self.calculate_volatility(df_m5['close'], 20)
        
        vol_ratio = m1_volatility / m5_volatility if m5_volatility > 0 else 1
        volatility_regime = self.classify_jump_volatility_regime(m1_volatility, vol_ratio)
        
        return {
            'm1_volatility': m1_volatility,
            'm5_volatility': m5_volatility,
            'volatility_ratio': vol_ratio,
            'volatility_regime': volatility_regime,
        }
    
    def calculate_volatility(self, series: pd.Series, window: int) -> float:
        """Calcule la volatilité (écart-type des rendements)"""
        returns = series.pct_change().dropna()
        if len(returns) < window:
            return 0.0
        return returns.rolling(window).std().iloc[-1] * 100
        
    def detect_jumps(self, df_m5: pd.DataFrame, df_m15: pd.DataFrame) -> Dict:
        """Détecte si un jump significatif a eu lieu (à compléter par l'utilisateur)"""
        # Logique de détection de jump (ex: écart-type élevé, mouvement rapide)
        # Ceci est un placeholder, la logique devrait être implémentée ici.
        return {'is_jumping': False, 'direction': 'NONE', 'magnitude': 0.0} 
    
    def analyze_price_structure(self, df: pd.DataFrame) -> Dict:
        """Analyse la structure de prix (à compléter par l'utilisateur)"""
        # Logique d'analyse de structure (ex: sommets/creux, niveaux de support/résistance)
        # Ceci est un placeholder, la logique devrait être implémentée ici.
        return {'structure_type': 'RANGING', 'last_break': None}