import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, time
import json
import logging
# Assurez-vous que PriceActionAnalyzer est importé correctement
from core.price_action import PriceActionAnalyzer # Doit exister dans votre répertoire core

# Les classes MT5Manager et TradeExecutor ne sont pas définies ici, 
# elles doivent être fournies par votre launcher.py (comme dans l'exemple de la réponse précédente)

# ==============================================================================
# STRATÉGIE CRASH/BOOM V5 (Smart Money Reversal)
# ==============================================================================

class CrashBoomStrategy:
    
    def __init__(self, config_path: str = "config/config_symbols_v2.json"):
        self.config = self.load_config(config_path)
        self.gap_threshold = 0.05
        self.extreme_move_threshold = 0.15
        self.performance_history = []
        
        # Initialisation Price Action
        self.pa = PriceActionAnalyzer()
        
    def load_config(self, config_path: str) -> Dict:
        """Charge la configuration des symboles"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logging.warning(f"⚠️ Fichier de configuration {config_path} non trouvé. Utilisation d'une configuration vide.")
            return {}
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calcule l'Average True Range (ATR) sur les données d'entrée."""
        if len(df) < period:
            return pd.Series([0.001] * len(df), index=df.index)
            
        high = df['high']
        low = df['low']
        close = df['close']
        
        # True Range (TR)
        prev_close = close.shift(1)
        tr = pd.DataFrame({
            'h_l': high - low,
            'h_pc': abs(high - prev_close),
            'l_pc': abs(low - prev_close)
        }).max(axis=1)
        
        # ATR (EMA du TR)
        atr = tr.ewm(span=period, adjust=False).mean()
        return atr

    # --- Méthodes de détection (conservées de votre code) ---
    # ... (detect_price_gaps, get_current_gap_status, is_gap_filled, assess_gap_environment,
    # detect_extreme_moves, classify_extreme_volatility, assess_volatility_trend,
    # analyze_crash_boom_volatility, calculate_rolling_volatility, detect_volatility_clusters,
    # classify_crash_boom_regime, detect_crash_boom_patterns, detect_v_shape_pattern,
    # detect_momentum_exhaustion, detect_key_level_break, detect_volume_spikes,
    # calculate_rsi) - Les corps des fonctions sont conservés à la fin.
    
    # [CONSERVATION DES MÉTHODES DE DÉTECTION NON CRITIQUES ICI]
    # (Pour ne pas répéter tout le code, les fonctions utilitaires sont conservées à la fin.)
    
    def analyze_crash_boom_conditions(self, symbol: str, df_m1: pd.DataFrame,
                                      df_m5: pd.DataFrame, df_m15: pd.DataFrame, 
                                      df_h1: pd.DataFrame) -> Dict: 
        """Analyse les conditions spécifiques aux indices Crash/Boom (VERSION V5 SMART MONEY H1)"""
        
        # 1. Détection de gaps
        gap_analysis = self.detect_price_gaps(df_m15, df_m5)
        
        # 2. Mouvements extrêmes
        extreme_moves = self.detect_extreme_moves(df_m5)
        
        # 3. Volatilité (Nécessaire pour le régime et l'ATR)
        volatility_profile = self.analyze_crash_boom_volatility(df_m1, df_m5)
        
        # 4. Patterns classiques
        price_patterns = self.detect_crash_boom_patterns(df_m15)
        
        # --- AJOUT V5 : ANALYSE PRICE ACTION (SMC) ---
        pa_analysis_m15 = self.pa.analyze_price_action(df_m15)
        pa_analysis_m5 = self.pa.analyze_price_action(df_m5)
        pa_analysis_h1 = self.pa.analyze_price_action(df_h1) 
        
        # 5. Opportunité de trading (NOUVELLE MÉTHODE DE SCORING V5)
        # PASSAGE DES DATAFRAMES COMPLÈTES POUR CALCUL D'INDICATEURS SI BESOIN
        trading_opportunity = self.assess_crash_boom_opportunity_v5( 
            symbol, gap_analysis, extreme_moves, volatility_profile,
            price_patterns, pa_analysis_m15, pa_analysis_m5, pa_analysis_h1, 
            df_m5, df_m1, df_m15
        )
        
        return {
            'symbol': symbol,
            'gap_analysis': gap_analysis,
            'extreme_moves': extreme_moves,
            'volatility_profile': volatility_profile,
            'price_patterns': price_patterns,
            'pa_analysis_m15': pa_analysis_m15,
            'pa_analysis_m5': pa_analysis_m5,
            'pa_analysis_h1': pa_analysis_h1,
            'trading_opportunity': trading_opportunity,
            
            # Champs pour l'intégration à l'exécuteur de trade
            'action': trading_opportunity['action'],
            'recommended_action': trading_opportunity['action'],
            'confidence_score': trading_opportunity['confidence'],
            'risk_adjustment': trading_opportunity['risk_adjustment'],
            'timestamp': datetime.now().isoformat()
        }
    
    def assess_crash_boom_opportunity_v5(self, symbol: str, gap_analysis: Dict,
                                         extreme_moves: Dict, volatility_profile: Dict,
                                         price_patterns: Dict, pa_m15: Dict, pa_m5: Dict,
                                         pa_h1: Dict, df_m5: pd.DataFrame, 
                                         df_m1: pd.DataFrame, df_m15: pd.DataFrame) -> Dict:
        """
        Évaluation V5 : Chasse aux Spikes avec Structure M15, FVG M5 & Filtre H1
        (Logique de REVERSAL: Vente sur Boom, Achat sur Crash)
        """
        score = 0
        action = "HOLD"
        
        # -------------------------------------------------------------------------
        # 1. ACTION CIBLÉE (CORRECTION: REVERSAL)
        # -------------------------------------------------------------------------
        is_boom = "BOOM" in symbol.upper()
        # Vendre Boom / Acheter Crash
        target_action = "SELL" if is_boom else "BUY" 
        target_direction = "BEARISH" if is_boom else "BULLISH" 
        
        # Données de base pour le calcul du risque
        atr_m5_series = self.calculate_atr(df_m5, 14) 
        atr_m5 = atr_m5_series.iloc[-1] if not atr_m5_series.empty else 0.001
        current_price = df_m5['close'].iloc[-1]
        
        # --- FILTRE MAJEUR 0 : CONTEXTE H1 (30 points) ---
        h1_structure = pa_h1.get('structure', {}).get('type', 'RANGING')
        
        # 1. Alignement de la Structure H1 (Chercher la structure qui supporte la REVERSAL)
        # NOUVEL ALIGNEMENT SMC POUR LE REVERSAL
        h1_aligned = (is_boom and h1_structure in ["BEARISH_STRUCTURE", "COMPRESSION"]) or \
                     (not is_boom and h1_structure in ["BULLISH_STRUCTURE", "COMPRESSION"]) 
        
        if h1_aligned:
            score += 15
        elif (is_boom and h1_structure == "BULLISH_STRUCTURE") or \
             (not is_boom and h1_structure == "BEARISH_STRUCTURE"):
            score -= 20 # Forte pénalité si on trade contre le trend H1 fort
            
        # 2. Proximité des POI H1 (Fair Value Gaps)
        in_major_zone = False
        h1_fvgs = pa_h1.get('fvgs', [])
        for fvg in h1_fvgs:
             # NOUVEL ALIGNEMENT FVG POUR LE REVERSAL
             is_target_fvg = (is_boom and fvg['type'] == 'BEARISH_FVG') or \
                             (not is_boom and fvg['type'] == 'BULLISH_FVG')
             
             if is_target_fvg and fvg['bottom'] <= current_price <= fvg['top']:
                 in_major_zone = True
                 break
        
        if in_major_zone:
            score += 15 # Boost majeur
            
        # --- PILIER 1 : STRUCTURE DE MARCHÉ M15 (30 points) ---
        structure_m15 = pa_m15.get('structure', {}).get('type', 'RANGING')
        
        # NOUVEL ALIGNEMENT STRUCTURE M15 POUR LE REVERSAL
        if is_boom: # Target SELL -> Chercher Bearish ou Compression
            if structure_m15 == "BEARISH_STRUCTURE": score += 30
            elif structure_m15 == "COMPRESSION": score += 15
        else: # is_crash, Target BUY -> Chercher Bullish ou Compression
            if structure_m15 == "BULLISH_STRUCTURE": score += 30
            elif structure_m15 == "COMPRESSION": score += 15

        # --- PILIER 2 : ZONES D'INTÉRÊT M5 (FVG / Order Blocks) (30 points) ---
        fvgs = pa_m5.get('fvgs', [])
        in_fvg_zone_m5 = False
        
        # NOUVEL ALIGNEMENT FVG M5 POUR LE REVERSAL (Le point d'entrée exact)
        if is_boom: # Target SELL -> Chercher Bearish FVG
            for fvg in fvgs:
                 if fvg['type'] == 'BEARISH_FVG' and fvg['bottom'] <= current_price <= fvg['top']:
                     in_fvg_zone_m5 = True
                     break
        else: # is_crash, Target BUY -> Chercher Bullish FVG
            for fvg in fvgs:
                 if fvg['type'] == 'BULLISH_FVG' and fvg['bottom'] <= current_price <= fvg['top']:
                     in_fvg_zone_m5 = True
                     break
        
        if in_fvg_zone_m5:
            score += 30 
            
        # --- PILIER 3 : TIMING M15 (Divergence/Exhaustion) (10 points) ---
        # NOUVEL ALIGNEMENT DIVERGENCE POUR LE REVERSAL (Confirmation d'épuisement)
        if is_boom and price_patterns.get('momentum_exhaustion', {}).get('bearish_divergence'): # Target SELL -> Chercher Bearish Divergence
            score += 10 
        elif not is_boom and price_patterns.get('momentum_exhaustion', {}).get('bullish_divergence'): # Target BUY -> Chercher Bullish Divergence
            score += 10

        # --- DÉCISION FINALE ET GESTION DU RISQUE ---
        score = max(0, min(100, score))
        risk_adjustment = 0.5 
        
        if score >= 55: 
            action = target_action # Utilisation de l'action de REVERSAL corrigée
            direction = target_direction
            
            if score >= 80:
                risk_adjustment = 1.0 
            elif score >= 65:
                risk_adjustment = 0.8 
                
            # Récupération des paramètres ajustés (SL/TP/TimeStop)
            volatility_regime = volatility_profile['regime']
            adjusted_params = self.get_strategy_parameters(symbol, "SCALPING", volatility_regime)
            
            # Calcul des niveaux d'entrée/sortie
            sl_multiplier = adjusted_params.get("SL_ATR_MULTIPLE", 3.0) * risk_adjustment
            rr_ratio = adjusted_params.get("RR", 1.5)
            
            # Calcul du SL et TP en points (utiliser l'ATR M5 comme base)
            stop_loss_points = atr_m5 * sl_multiplier
            take_profit_points = stop_loss_points * rr_ratio
            
            # Sortie pour l'exécuteur de trade
            return {
                'action': action,
                'direction': direction,
                'confidence': score / 100,
                'risk_adjustment': risk_adjustment,
                'sl_points': stop_loss_points,
                'tp_points': take_profit_points,
                'time_stop_min': adjusted_params.get("TIME_STOP_MIN", 10),
                'risk_percent': adjusted_params.get("RISK_PERCENT", 0.005) * risk_adjustment,
                'reason': f"V5 Score: {score} (H1 R: {target_direction} | M15 S: {structure_m15} | FVG M5: {in_fvg_zone_m5})"
            }
            
        return {
            'action': action,
            'direction': direction,
            'confidence': score / 100,
            'risk_adjustment': 0.0,
            'sl_points': 0.0, 'tp_points': 0.0, 'time_stop_min': 0, 'risk_percent': 0.0,
            'reason': f"Score insuffisant ({score})."
        }
    
    # --- MÉTHODES UTILITAIRES EXISTANTES (COLLEZ LES ICI) ---

    def get_strategy_parameters(self, symbol: str, profile: str, regime: str) -> Dict:
        """Retourne les paramètres stratégiques optimisés pour Crash/Boom"""
        base_config = self.config.get(symbol, {}).get(profile, {})
        
        crash_boom_adjustments = {
            "CRASH_IMMINENT": {
                "SL_ATR_MULTIPLE": base_config.get("SL_ATR_MULTIPLE", 3.0) * 1.5, 
                "RR": base_config.get("RR", 1.5) * 0.7, 
                "TIME_STOP_MIN": base_config.get("TIME_STOP_MIN", 10) * 0.5, 
                "RISK_PERCENT": base_config.get("RISK_PERCENT", 0.005) * 0.4 
            },
            "HIGH_RISK": {
                "SL_ATR_MULTIPLE": base_config.get("SL_ATR_MULTIPLE", 3.0) * 1.3,
                "RR": base_config.get("RR", 1.5) * 0.8,
                "TIME_STOP_MIN": base_config.get("TIME_STOP_MIN", 10) * 0.7,
                "RISK_PERCENT": base_config.get("RISK_PERCENT", 0.005) * 0.6
            },
            "VOLATILITY_EXPANSION": {
                "SL_ATR_MULTIPLE": base_config.get("SL_ATR_MULTIPLE", 3.0) * 1.1,
                "RR": base_config.get("RR", 1.5) * 1.0,
                "TIME_STOP_MIN": base_config.get("TIME_STOP_MIN", 10),
                "RISK_PERCENT": base_config.get("RISK_PERCENT", 0.005) * 0.8
            },
            "LOW_VOL_STABILITY": {
                "SL_ATR_MULTIPLE": base_config.get("SL_ATR_MULTIPLE", 3.0) * 0.9,
                "RR": base_config.get("RR", 1.5) * 1.1,
                "TIME_STOP_MIN": base_config.get("TIME_STOP_MIN", 10) * 1.2,
                "RISK_PERCENT": base_config.get("RISK_PERCENT", 0.005) * 1.0
            }
        }
        
        adjustment = crash_boom_adjustments.get(regime, {})
        
        final_params = {
            "SL_ATR_MULTIPLE": adjustment.get("SL_ATR_MULTIPLE", base_config.get("SL_ATR_MULTIPLE", 3.0)),
            "RR": adjustment.get("RR", base_config.get("RR", 1.5)),
            "TIME_STOP_MIN": adjustment.get("TIME_STOP_MIN", base_config.get("TIME_STOP_MIN", 10)),
            "RISK_PERCENT": adjustment.get("RISK_PERCENT", base_config.get("RISK_PERCENT", 0.005)),
            "MAX_LOT": base_config.get("MAX_LOT", 1.0) 
        }
        
        return final_params

    # COLLES DES AUTRES MÉTHODES UTILES ICI (detect_price_gaps, detect_extreme_moves, etc.)
    # ... (le corps de ces fonctions est le même que dans votre requête)
    
    def detect_price_gaps(self, df_m15: pd.DataFrame, df_m5: pd.DataFrame) -> Dict:
        """Détecte les gaps de prix significatifs"""
        gaps = []
        for i in range(1, min(10, len(df_m15))):
            current = df_m15.iloc[-i]
            previous = df_m15.iloc[-i-1] if len(df_m15) > i+1 else current
            
            gap_up = current['low'] > previous['high']
            gap_down = current['high'] < previous['low']
            
            if gap_up or gap_down:
                gap_size = abs(current['open'] - previous['close']) / previous['close'] * 100
                if gap_size > self.gap_threshold:
                    gaps.append({
                        'timestamp': current.name if hasattr(current, 'name') else datetime.now(),
                        'direction': 'UP' if gap_up else 'DOWN',
                        'size_percent': gap_size,
                        'timeframe': 'M15',
                        'filled': self.is_gap_filled(df_m5, gap_up, current['low'] if gap_up else current['high'])
                    })
        
        current_gap = self.get_current_gap_status(df_m5)
        return {
            'recent_gaps': gaps[:3],
            'current_gap': current_gap,
            'gap_environment': self.assess_gap_environment(gaps)
        }
    
    def get_current_gap_status(self, df: pd.DataFrame) -> Optional[Dict]:
        """Évalue le gap actuel"""
        if len(df) < 2: return None
        current = df.iloc[-1]
        previous = df.iloc[-2]
        gap_up = current['low'] > previous['high']
        gap_down = current['high'] < previous['low']
        
        if gap_up or gap_down:
            gap_size = abs(current['open'] - previous['close']) / previous['close'] * 100
            return {
                'exists': True,
                'direction': 'UP' if gap_up else 'DOWN',
                'size_percent': gap_size,
                'timeframe': 'M5'
            }
        return {'exists': False}
    
    def is_gap_filled(self, df: pd.DataFrame, was_gap_up: bool, gap_level: float) -> bool:
        """Vérifie si un gap a été comblé"""
        if was_gap_up:
            return df['low'].min() <= gap_level
        else:
            return df['high'].max() >= gap_level
    
    def assess_gap_environment(self, gaps: List[Dict]) -> str:
        """Évalue l'environnement de gaps"""
        if not gaps: return "NO_SIGNIFICANT_GAPS"
        recent_gaps = [g for g in gaps if g['size_percent'] > 1.0]
        if len(recent_gaps) >= 3: return "HIGH_GAP_FREQUENCY"
        elif len(recent_gaps) >= 2: return "MODERATE_GAP_FREQUENCY"
        elif any(g['size_percent'] > 3.0 for g in recent_gaps): return "EXTREME_GAP_PRESENT"
        else: return "NORMAL_GAP_ENVIRONMENT"
    
    def detect_extreme_moves(self, df: pd.DataFrame) -> Dict:
        """Détecte les mouvements de prix extrêmes"""
        if len(df) < 20: return {'extreme_moves': [], 'current_volatility': 'NORMAL'}
        returns = df['close'].pct_change().abs() * 100
        extreme_moves = []
        for i in range(1, min(10, len(returns))):
            if returns.iloc[-i] > self.extreme_move_threshold:
                extreme_moves.append({
                    'index': i,
                    'move_percent': returns.iloc[-i],
                    'direction': 'UP' if df['close'].iloc[-i] > df['close'].iloc[-i-1] else 'DOWN'
                })
        current_volatility = returns.tail(5).mean()
        volatility_regime = self.classify_extreme_volatility(current_volatility)
        return {
            'extreme_moves': extreme_moves[:5],
            'current_volatility': current_volatility,
            'volatility_regime': volatility_regime,
            'recent_volatility_trend': self.assess_volatility_trend(returns)
        }
    
    def classify_extreme_volatility(self, volatility: float) -> str:
        """Classifie la volatilité extrême"""
        if volatility > 0.25: return "EXTREME_HIGH"
        elif volatility > 0.15: return "HIGH"
        elif volatility > 0.08: return "ELEVATED"
        else: return "NORMAL"
    
    def assess_volatility_trend(self, returns: pd.Series) -> str:
        """Évalue la tendance de volatilité"""
        if len(returns) < 10: return "UNKNOWN"
        recent_vol = returns.tail(5).mean()
        historical_vol = returns.tail(20).mean()
        if recent_vol > historical_vol * 1.5: return "INCREASING"
        elif recent_vol < historical_vol * 0.7: return "DECREASING"
        else: return "STABLE"
    
    def analyze_crash_boom_volatility(self, df_m1: pd.DataFrame, df_m5: pd.DataFrame) -> Dict:
        """Analyse la volatilité spécifique aux indices Crash/Boom"""
        m1_volatility = self.calculate_rolling_volatility(df_m1['close'], 10)
        m5_volatility = self.calculate_rolling_volatility(df_m5['close'], 20)
        vol_ratio = m1_volatility / m5_volatility if m5_volatility > 0 else 1
        vol_clusters = self.detect_volatility_clusters(df_m5)
        return {
            'm1_volatility': m1_volatility,
            'm5_volatility': m5_volatility,
            'volatility_ratio': vol_ratio,
            'volatility_clusters': vol_clusters,
            'regime': self.classify_crash_boom_regime(m5_volatility, vol_ratio)
        }
    
    def calculate_rolling_volatility(self, series: pd.Series, window: int) -> float:
        returns = series.pct_change().dropna()
        if len(returns) < window: return 0.0
        return returns.rolling(window).std().iloc[-1] * 100
    
    def detect_volatility_clusters(self, df: pd.DataFrame) -> List[Dict]:
        if len(df) < 50: return []
        returns = df['close'].pct_change().abs()
        high_vol_threshold = returns.quantile(0.8)
        clusters = []
        current_cluster = None
        for i in range(len(returns)):
            if returns.iloc[i] > high_vol_threshold:
                if current_cluster is None:
                    current_cluster = {'start': i, 'end': i, 'max_vol': returns.iloc[i]}
                else:
                    current_cluster['end'] = i
                    current_cluster['max_vol'] = max(current_cluster['max_vol'], returns.iloc[i])
            else:
                if current_cluster is not None:
                    clusters.append(current_cluster)
                    current_cluster = None
        if current_cluster is not None: clusters.append(current_cluster)
        recent_clusters = [c for c in clusters if c['end'] >= len(returns) - 10]
        return recent_clusters[:3]
    
    def classify_crash_boom_regime(self, volatility: float, vol_ratio: float) -> str:
        if volatility > 0.2 and vol_ratio > 1.5: return "CRASH_IMMINENT"
        elif volatility > 0.15 and vol_ratio > 1.2: return "HIGH_RISK"
        elif volatility < 0.05 and vol_ratio < 0.8: return "LOW_VOL_STABILITY"
        elif vol_ratio > 1.3: return "VOLATILITY_EXPANSION"
        elif vol_ratio < 0.7: return "VOLATILITY_CONTRACTION"
        else: return "NORMAL_OPERATION"
    
    def detect_crash_boom_patterns(self, df: pd.DataFrame) -> Dict:
        """Détecte les patterns spécifiques Crash/Boom"""
        patterns = {
            'v_shape_recovery': self.detect_v_shape_pattern(df),
            'momentum_exhaustion': self.detect_momentum_exhaustion(df),
            'support_resistance_break': self.detect_key_level_break(df),
            'volume_spike': self.detect_volume_spikes(df)
        }
        return patterns
    
    def detect_v_shape_pattern(self, df: pd.DataFrame) -> Optional[Dict]:
        if len(df) < 10: return {'detected': False}
        
        window = df.iloc[-10:]
        
        lows = window['low']
        min_idx_relative = lows.argmin()
        min_price = lows.iloc[min_idx_relative]
        
        if min_idx_relative >= 2 and min_idx_relative <= 7:
            left_decline = (window['close'].iloc[0] - min_price) / window['close'].iloc[0] * 100
            right_recovery = (window['close'].iloc[-1] - min_price) / min_price * 100
            
            if left_decline > 2 and right_recovery > 1.5:
                return {
                    'detected': True,
                    'depth_percent': left_decline,
                    'recovery_percent': right_recovery,
                    'pattern_strength': min(left_decline, right_recovery) / 10
                }
        return {'detected': False}
    
    def detect_momentum_exhaustion(self, df: pd.DataFrame) -> Dict:
        """Détecte l'épuisement du momentum (Divergences RSI) """
        if len(df) < 20: return {'detected': False, 'bearish_divergence': False, 'bullish_divergence': False}
        close = df['close']
        rsi = self.calculate_rsi(close, 14)
        if rsi.empty: return {'detected': False, 'bearish_divergence': False, 'bullish_divergence': False}
        
        current_rsi = rsi.iloc[-1]
        
        bearish_divergence = (close.iloc[-1] > close.iloc[-5] and current_rsi < rsi.iloc[-5] * 0.9) and current_rsi > 70
        
        bullish_divergence = (close.iloc[-1] < close.iloc[-5] and current_rsi > rsi.iloc[-5] * 1.1) and current_rsi < 30
        
        return {
            'detected': bearish_divergence or bullish_divergence,
            'bearish_divergence': bearish_divergence,
            'bullish_divergence': bullish_divergence,
            'current_rsi': current_rsi,
            'strength': abs(current_rsi - 50) / 50
        }
    
    def detect_key_level_break(self, df: pd.DataFrame) -> Dict:
        """Détecte la cassure de niveaux clés (Support/Résistance)"""
        if len(df) < 30: return {'detected': False}
        support = df['low'].tail(20).min()
        resistance = df['high'].tail(20).max()
        current_price = df['close'].iloc[-1]
        break_above = current_price > resistance
        break_below = current_price < support
        
        volume_confirmation = False
        if 'tick_volume' in df.columns:
            recent_volume = df['tick_volume'].tail(5).mean()
            avg_volume = df['tick_volume'].tail(20).mean()
            volume_confirmation = recent_volume > avg_volume * 1.2
            
        return {
            'detected': break_above or break_below,
            'break_above': break_above,
            'break_below': break_below,
            'level': resistance if break_above else support if break_below else None,
            'volume_confirmation': volume_confirmation,
            'strength': 0.7 if volume_confirmation else 0.4
        }
    
    def detect_volume_spikes(self, df: pd.DataFrame) -> Dict:
        """Détecte les pics de volume"""
        if 'tick_volume' not in df.columns or len(df) < 20: return {'detected': False}
        volume = df['tick_volume']
        current_volume = volume.iloc[-1]
        avg_volume = volume.tail(20).mean()
        volume_spike = current_volume > avg_volume * 2
        volume_trend = volume.tail(5).mean() > volume.tail(20).mean()
        return {
            'detected': volume_spike,
            'current_volume': current_volume,
            'volume_ratio': current_volume / avg_volume if avg_volume > 0 else 1,
            'trend_increasing': volume_trend,
            'strength': min(current_volume / avg_volume, 3) / 3
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
        rs.fillna(1, inplace=True)
        
        rsi = 100 - (100 / (1 + rs))
        return rsi