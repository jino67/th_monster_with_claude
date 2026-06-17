import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import json
# IMPORT DU NOUVEAU CERVEAU SMART MONEY
from core.price_action import PriceActionAnalyzer

class JumpStrategy:
    def __init__(self, config_path: str = "config/config_symbols_v2.json"):
        self.config = self.load_config(config_path)
        self.jump_threshold = 0.08  # 8% pour détecter un jump
        self.retracement_threshold = 0.03  # 3% pour la confirmation
        self.performance_history = []
        
        # Initialisation de l'analyseur Price Action
        self.pa = PriceActionAnalyzer()
        
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
                                df_h1: pd.DataFrame) -> Dict: # <--- AJOUT du df_h1
        """Analyse les conditions spécifiques aux indices Jump (VERSION V5 SMART MONEY H1)"""
        
        # 1. Détection des jumps (Classique)
        jump_analysis = self.detect_jumps(df_m5, df_m15)
        
        # 2. Momentum post-jump (Classique)
        momentum_analysis = self.analyze_post_jump_momentum(df_m1, df_m5)
        
        # 3. Structure de prix M15 (Classique + Niveaux) - Utile pour le contexte
        price_structure = self.analyze_price_structure(df_m15)
        
        # 4. Volatilité (Classique)
        volatility_profile = self.analyze_jump_volatility(df_m1, df_m5)
        
        # --- AJOUT V5 : ANALYSE PRICE ACTION (SMC) ---
        pa_analysis_m5 = self.pa.analyze_price_action(df_m5)
        pa_analysis_h1 = self.pa.analyze_price_action(df_h1) # <--- NOUVELLE ANALYSE H1
        
        # 5. Opportunité de trading (NOUVELLE MÉTHODE DE SCORING V5)
        trading_opportunity = self.assess_jump_opportunity_v5( # <--- RENOMMAGE V5
            symbol, jump_analysis, momentum_analysis, price_structure, 
            volatility_profile, pa_analysis_m5, pa_analysis_h1, df_m1, df_m5 # <--- AJOUT pa_analysis_h1
        )
        
        return {
            'symbol': symbol,
            'jump_analysis': jump_analysis,
            'momentum_analysis': momentum_analysis,
            'price_structure': price_structure,
            'volatility_profile': volatility_profile,
            'pa_analysis_m5': pa_analysis_m5,
            'pa_analysis_h1': pa_analysis_h1, # Ajout pour debug
            'trading_opportunity': trading_opportunity,
            
            # Champs pour compatibilité avec l'engine
            'action': trading_opportunity['action'],            
            'recommended_action': trading_opportunity['action'], 
            'confidence_score': trading_opportunity['confidence'],
            'risk_adjustment': trading_opportunity['risk_adjustment'],
            'timestamp': datetime.now().isoformat()
        }
    
    def assess_jump_opportunity_v5(self, symbol: str, jump_analysis: Dict,
                                   momentum_analysis: Dict, price_structure: Dict,
                                   volatility_profile: Dict, pa_m5: Dict, 
                                   pa_h1: Dict, # <--- NOUVEL ARGUMENT H1
                                   df_m1: pd.DataFrame, df_m5: pd.DataFrame) -> Dict:
        """
        Évaluation V5 : Hybride Momentum M5 + Smart Money H1/M5
        """
        score = 0
        
        # La direction est dictée par le Momentum M5 (Pilier 1)
        direction = momentum_analysis['m5_momentum']['direction'] 
        
        # --- PILIER 0 : FILTRE H1 (30 points) ---
        h1_structure = pa_h1.get('structure', {}).get('type', 'RANGING')
        
        # 1. Alignement de la Structure H1
        h1_aligned = False
        if direction == "BULLISH":
            if h1_structure in ["BULLISH_STRUCTURE", "RANGING"]: # La 'RANGING' est tolérée
                h1_aligned = True
            elif h1_structure == "BEARISH_STRUCTURE":
                score -= 30 # Pénalité majeure si on achète contre la forte structure H1
        
        elif direction == "BEARISH":
            if h1_structure in ["BEARISH_STRUCTURE", "RANGING"]:
                h1_aligned = True
            elif h1_structure == "BULLISH_STRUCTURE":
                score -= 30 # Pénalité majeure si on vend contre la forte structure H1

        if h1_aligned:
             score += 30 # Base pour la bonne direction
             
        # --- PILIER 1 : MOMENTUM M5/M1 (40 points, ajusté) ---
        mom_strength = momentum_analysis['momentum_strength']
        if mom_strength > 0.6: score += 40
        elif mom_strength > 0.4: score += 25
        
        if momentum_analysis['momentum_alignment'] == "ALIGNED":
            score += 5 # Bonus léger pour l'alignement M1/M5 (timing fin)

        # --- PILIER 2 : PRICE ACTION M5 (Structure & VWAP) (20 points, ajusté) ---
        structure_type_m5 = pa_m5.get('structure', {}).get('type', 'UNKNOWN')
        
        # Confirmation Structurelle M5
        if direction == "BULLISH":
            if structure_type_m5 == "BULLISH_STRUCTURE": score += 10
            # VWAP Filter (On achète au-dessus du VWAP pour suivre la force)
            if pa_m5.get('vwap_signal') == "BULLISH": score += 10
            
        elif direction == "BEARISH":
            if structure_type_m5 == "BEARISH_STRUCTURE": score += 10
            # VWAP Filter (On vend en-dessous du VWAP)
            if pa_m5.get('vwap_signal') == "BEARISH": score += 10

        # --- PILIER 3 : VOLATILITÉ (10 points, ajusté) ---
        volatility_profile = self.analyze_jump_volatility(df_m1, df_m5)
        vol_regime = volatility_profile.get('volatility_regime', 'JUMP_NORMAL')
        
        if vol_regime in ["JUMP_EXPANSION", "JUMP_NORMAL"]:
            score += 10
        elif vol_regime == "JUMP_CALM":
            score -= 5 
        elif vol_regime in ["JUMP_IMMINENT", "HIGH_JUMP_RISK"]:
            score -= 10 

        # --- DÉCISION FINALE ---
        score = max(0, min(100, score)) # Borner 0-100
        action = "HOLD"
        risk_adjustment = 0.0
        
        if score >= 60: # Seuil d'entrée remonté légèrement car le H1 donne plus de confiance
            action = "BUY" if direction == "BULLISH" else "SELL"
            
            # Gestion du risque intelligente
            if score >= 90:
                risk_adjustment = 1.0     # H1 Alignement parfait + Momentum/VWAP fort
            elif score >= 75:
                risk_adjustment = 0.75    # H1 Alignement + Bon Momentum M5
            else:
                risk_adjustment = 0.5     # Entrée spéculative, mais direction H1 ok

        return {
            'action': action,
            'direction': direction,
            'confidence': score / 100,
            'risk_adjustment': risk_adjustment,
            'reason': f"V5 Score: {score} (H1 Struct: {h1_structure} | M5 Struct: {structure_type_m5} | Mom: {mom_strength:.2f})"
        }

    # --- MÉTHODES UTILITAIRES EXISTANTES (INCHANGÉES) ---
    
    def detect_jumps(self, df_m5: pd.DataFrame, df_m15: pd.DataFrame) -> Dict:
        """Détecte les jumps significatifs"""
        jumps = []
        
        # Analyse M15 pour les jumps majeurs
        for i in range(1, min(20, len(df_m15))):
            current = df_m15.iloc[-i]
            previous = df_m15.iloc[-i-1] if len(df_m15) > i+1 else current
            
            price_change = abs(current['close'] - previous['close']) / previous['close'] * 100
            
            if price_change > self.jump_threshold:
                direction = 'UP' if current['close'] > previous['close'] else 'DOWN'
                jump_strength = price_change / self.jump_threshold
                
                jumps.append({
                    'timestamp': current.name if hasattr(current, 'name') else datetime.now(),
                    'direction': direction,
                    'magnitude': price_change,
                    'strength': jump_strength,
                    'timeframe': 'M15',
                    'retraced': False # Simplifié pour la structure
                })
        
        # Jump actuel
        current_jump = self.get_current_jump_status(df_m5)
        
        return {
            'recent_jumps': jumps[:5],  # 5 derniers jumps
            'current_jump': current_jump,
            'jump_environment': self.assess_jump_environment(jumps),
            'jump_frequency': self.calculate_jump_frequency(jumps)
        }
    
    def get_current_jump_status(self, df: pd.DataFrame) -> Optional[Dict]:
        """Évalue le jump actuel"""
        if len(df) < 10:
            return None
        
        # Regarde les 5 dernières bougies pour détecter un jump
        recent_data = df.tail(5)
        price_changes = []
        
        for i in range(1, len(recent_data)):
            change = abs(recent_data['close'].iloc[i] - recent_data['close'].iloc[i-1]) / recent_data['close'].iloc[i-1] * 100
            price_changes.append(change)
        
        max_change = max(price_changes) if price_changes else 0
        max_change_idx = price_changes.index(max_change) if price_changes else -1
        
        if max_change > self.jump_threshold:
            direction = 'UP' if recent_data['close'].iloc[max_change_idx+1] > recent_data['close'].iloc[max_change_idx] else 'DOWN'
            
            return {
                'exists': True,
                'direction': direction,
                'magnitude': max_change,
                'timeframe': 'M5',
                'age_bars': len(price_changes) - max_change_idx
            }
        
        return {'exists': False}

    def assess_jump_environment(self, jumps: List[Dict]) -> str:
        """Évalue l'environnement de jumps"""
        if not jumps:
            return "CALM"
        
        strong_jumps = [j for j in jumps if j['magnitude'] > 15]  
        
        if len(strong_jumps) >= 2:
            return "EXTREME_VOLATILITY"
        elif any(j['magnitude'] > 20 for j in jumps):
            return "MEGA_JUMP_PRESENT"
        else:
            return "MODERATE_JUMPING"
    
    def calculate_jump_frequency(self, jumps: List[Dict]) -> float:
        """Calcule la fréquence des jumps (Simplifié)"""
        return 0.5

    def analyze_post_jump_momentum(self, df_m1: pd.DataFrame, df_m5: pd.DataFrame) -> Dict:
        """Analyse le momentum après un jump"""
        # Momentum à très court terme (M1)
        m1_momentum = self.calculate_momentum(df_m1, 10)
        
        # Momentum à court terme (M5)
        m5_momentum = self.calculate_momentum(df_m5, 20)
        
        # Convergence/divergence de momentum
        momentum_alignment = self.assess_momentum_alignment(m1_momentum, m5_momentum)
        
        # Force du momentum
        momentum_strength = self.calculate_momentum_strength(m1_momentum, m5_momentum)
        
        return {
            'm1_momentum': m1_momentum,
            'm5_momentum': m5_momentum,
            'momentum_alignment': momentum_alignment,
            'momentum_strength': momentum_strength,
            'trend_continuation': self.assess_trend_continuation(m1_momentum, m5_momentum)
        }
    
    def calculate_momentum(self, df: pd.DataFrame, lookback: int) -> Dict:
        """Calcule les indicateurs de momentum"""
        if len(df) < lookback:
            return {'rsi': 50, 'macd_hist': 0, 'velocity': 0, 'direction': 'RANGING'}
        
        close = df['close']
        
        # RSI
        rsi = self.calculate_rsi(close, 14).iloc[-1] if len(close) >= 14 else 50
        
        # MACD Histogram
        macd_hist = self.calculate_macd_histogram(close).iloc[-1] if len(close) >= 26 else 0
        
        # Velocity (taux de changement)
        price_change = (close.iloc[-1] - close.iloc[-lookback]) / close.iloc[-lookback] * 100
        velocity = price_change / lookback  #% change par bougie
        
        return {
            'rsi': rsi,
            'macd_hist': macd_hist,
            'velocity': velocity,
            'direction': 'BULLISH' if velocity > 0 else 'BEARISH'
        }
    
    def calculate_rsi(self, series: pd.Series, period: int) -> pd.Series:
        """Calcule le RSI"""
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        
        with np.errstate(divide='ignore', invalid='ignore'):
            rs = avg_gain / avg_loss
            
        rs.replace([np.inf, -np.inf], np.nan, inplace=True)
        rs.fillna(1, inplace=True) # Évite la division par zéro (RSI 50)
        
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
        """Évalue l'alignement du momentum"""
        m1_dir = m1_momentum['direction']
        m5_dir = m5_momentum['direction']
        
        if m1_dir == m5_dir:
            return "ALIGNED"
        else:
            return "DIVERGENT"
    
    def calculate_momentum_strength(self, m1_momentum: Dict, m5_momentum: Dict) -> float:
        """Calcule la force du momentum composite"""
        # Score basé sur RSI
        rsi_strength = (abs(m1_momentum['rsi'] - 50) / 50) * 0.4
        
        # Score basé sur MACD (simplifié)
        # On normalise le MACD pour qu'il soit entre 0 et 1 (approximation)
        macd_strength = min(abs(m1_momentum['macd_hist']) * 10, 1) * 0.3
        
        # Score basé sur velocity
        velocity_strength = min(abs(m1_momentum['velocity']) * 10, 1) * 0.3
        
        return rsi_strength + macd_strength + velocity_strength
    
    def assess_trend_continuation(self, m1_momentum: Dict, m5_momentum: Dict) -> bool:
        """Évalue si la tendance est susceptible de continuer"""
        # Tendances alignées et momentum fort
        return (self.assess_momentum_alignment(m1_momentum, m5_momentum) == "ALIGNED" and 
                self.calculate_momentum_strength(m1_momentum, m5_momentum) > 0.6)
    
    def analyze_price_structure(self, df: pd.DataFrame) -> Dict:
        """Analyse la structure des prix (simplifié)"""
        if len(df) < 30:
            return {'structure': 'UNKNOWN', 'key_levels': []}
        
        close = df['close']
        
        # Structure de tendance
        trend_structure = self.analyze_trend_structure(close)
        
        return {
            'structure': trend_structure,
            'key_levels': [], # Placeholder
        }
    
    def analyze_trend_structure(self, close: pd.Series) -> str:
        """Analyse la structure de tendance (simplifié)"""
        if len(close) < 10:
            return "UNKNOWN"
        
        recent_highs = close.rolling(5).max().tail(3)
        recent_lows = close.rolling(5).min().tail(3)
        
        if recent_highs.iloc[-1] > recent_highs.iloc[-2] and recent_lows.iloc[-1] > recent_lows.iloc[-2]:
            return "UPTREND"
        elif recent_highs.iloc[-1] < recent_highs.iloc[-2] and recent_lows.iloc[-1] < recent_lows.iloc[-2]:
            return "DOWNTREND"
        else:
            return "RANGING"
    
    def analyze_jump_volatility(self, df_m1: pd.DataFrame, df_m5: pd.DataFrame) -> Dict:
        """Analyse la volatilité spécifique aux indices Jump"""
        # Volatilité à très court terme
        m1_volatility = self.calculate_volatility(df_m1['close'], 10)
        m5_volatility = self.calculate_volatility(df_m5['close'], 20)
        
        # Ratio de volatilité
        vol_ratio = m1_volatility / m5_volatility if m5_volatility > 0 else 1
        
        # Régime de volatilité
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
        return returns.rolling(window).std().iloc[-1] * 100  # En pourcentage
    
    def classify_jump_volatility_regime(self, volatility: float, vol_ratio: float) -> str:
        """Classifie le régime de volatilité pour les indices Jump"""
        if volatility > 0.25 and vol_ratio > 1.5:
            return "JUMP_IMMINENT"
        elif volatility > 0.15 and vol_ratio > 1.2:
            return "HIGH_JUMP_RISK"
        elif volatility < 0.05 and vol_ratio < 0.8:
            return "JUMP_CALM"
        elif vol_ratio > 1.3:
            return "JUMP_EXPANSION"
        else:
            return "JUMP_NORMAL"

    def get_strategy_parameters(self, symbol: str, profile: str, regime: str) -> Dict:
        """Retourne les paramètres stratégiques optimisés pour les indices Jump"""
        base_config = self.config.get(symbol, {}).get(profile, {})
        
        # Ajustements spécifiques Jump basés sur le régime de volatilité
        jump_adjustments = {
            "JUMP_IMMINENT": {
                "SL_ATR_MULTIPLE": base_config.get("SL_ATR_MULTIPLE", 1.0) * 1.3,
                "RR": base_config.get("RR", 1.5) * 0.8,
                "RISK_PERCENT": base_config.get("RISK_PERCENT", 0.02) * 0.5
            },
            "HIGH_JUMP_RISK": {
                "SL_ATR_MULTIPLE": base_config.get("SL_ATR_MULTIPLE", 1.0) * 1.2,
                "RR": base_config.get("RR", 1.5) * 0.9,
                "RISK_PERCENT": base_config.get("RISK_PERCENT", 0.02) * 0.7
            },
            "JUMP_EXPANSION": {
                "SL_ATR_MULTIPLE": base_config.get("SL_ATR_MULTIPLE", 1.0) * 1.1,
                "RR": base_config.get("RR", 1.5) * 1.0,
                "RISK_PERCENT": base_config.get("RISK_PERCENT", 0.02) * 0.9
            },
            "JUMP_CALM": {
                "SL_ATR_MULTIPLE": base_config.get("SL_ATR_MULTIPLE", 1.0) * 0.9,
                "RR": base_config.get("RR", 1.5) * 1.2,
                "RISK_PERCENT": base_config.get("RISK_PERCENT", 0.02) * 1.1
            }
        }
        
        return jump_adjustments.get(regime, base_config)