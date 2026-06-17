import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
import ta
from ta.volatility import AverageTrueRange
from ta.trend import ADXIndicator, IchimokuIndicator
from ta.momentum import RSIIndicator, StochasticOscillator

class AdvancedIndicators:
    def __init__(self):
        self.indicators_cache = {}
    
    def calculate_advanced_ichimoku(self, df: pd.DataFrame) -> Dict:
        """Ichimoku avancé avec signaux de confirmation"""
        high, low, close = df['high'], df['low'], df['close']
        
        # Ichimoku standard
        ichimoku = IchimokuIndicator(high=high, low=low)
        
        tenkan_sen = ichimoku.ichimoku_conversion_line()
        kijun_sen = ichimoku.ichimoku_base_line()
        senkou_span_a = ichimoku.ichimoku_a()
        senkou_span_b = ichimoku.ichimoku_b()
      #  chikou_span = ichimoku.ichimoku_chikou_span()
        
        # Dernières valeurs
        current_close = close.iloc[-1]
        current_tenkan = tenkan_sen.iloc[-1]
        current_kijun = kijun_sen.iloc[-1]
        current_senkou_a = senkou_span_a.iloc[-26] if len(senkou_span_a) > 26 else senkou_span_a.iloc[-1]
        current_senkou_b = senkou_span_b.iloc[-26] if len(senkou_span_b) > 26 else senkou_span_b.iloc[-1]
        
        # Calculs avancés
        kumo_thickness = abs(current_senkou_a - current_senkou_b) / current_close * 10000
        tenkan_kijun_distance = (current_tenkan - current_kijun) / current_close * 10000
        
        # Signaux
        is_bullish = current_tenkan > current_kijun
        is_bearish = current_tenkan < current_kijun
        
        price_above_kumo = current_close > max(current_senkou_a, current_senkou_b)
        price_below_kumo = current_close < min(current_senkou_a, current_senkou_b)
        
        # Momentum confirmation
        rsi = RSIIndicator(close=close, window=9).rsi().iloc[-1]
        stoch = StochasticOscillator(high=high, low=low, close=close).stoch_signal().iloc[-1]
        
        momentum_confirmed = (
            (is_bullish and rsi > 45 and stoch > 30) or
            (is_bearish and rsi < 55 and stoch < 70)
        )
        
        # Force du signal
        signal_strength = self.calculate_ichimoku_strength(
            is_bullish, price_above_kumo, kumo_thickness, tenkan_kijun_distance, rsi
        )
        
        return {
            "is_bullish": is_bullish,
            "is_bearish": is_bearish,
            "is_above_kumo": price_above_kumo,
            "is_below_kumo": price_below_kumo,
            "kumo_thickness": float(kumo_thickness),
            "tenkan_kijun_distance": float(tenkan_kijun_distance),
            "momentum_confirmed": momentum_confirmed,
            "signal_strength": signal_strength,
            "rsi_confirmation": float(rsi),
            "stoch_confirmation": float(stoch),
            "tenkan_sen": float(current_tenkan),
            "kijun_sen": float(current_kijun),
            "senkou_span_a": float(current_senkou_a),
            "senkou_span_b": float(current_senkou_b)
        }
    
    def calculate_ichimoku_strength(self, is_bullish: bool, price_above_kumo: bool, 
                                  kumo_thickness: float, tenkan_kijun_distance: float, 
                                  rsi: float) -> float:
        """Calcule la force du signal Ichimoku"""
        strength = 0.0
        
        # Base strength
        if is_bullish:
            strength += 0.3
            if price_above_kumo:
                strength += 0.3
            if rsi > 60:
                strength += 0.2
        else:
            strength += 0.3
            if not price_above_kumo:
                strength += 0.3
            if rsi < 40:
                strength += 0.2
        
        # Kumo thickness adjustment (thin kumo = stronger signal)
        if kumo_thickness < 20:  # Kumo mince
            strength += 0.1
        elif kumo_thickness > 50:  # Kumo épais
            strength -= 0.1
        
        # Tenkan-Kijun distance
        if abs(tenkan_kijun_distance) > 10:  # Écart significatif
            strength += 0.1
        
        return min(max(strength, 0.0), 1.0)
    
    def calculate_advanced_momentum(self, df: pd.DataFrame) -> Dict:
        """Indicateurs de momentum avancés"""
        close, high, low = df['close'], df['high'], df['low']
        
        # RSI multiples
        rsi_7 = RSIIndicator(close=close, window=7).rsi().iloc[-1]
        rsi_14 = RSIIndicator(close=close, window=14).rsi().iloc[-1]
        rsi_21 = RSIIndicator(close=close, window=21).rsi().iloc[-1]
        
        # MACD avancé
        macd_line = ta.trend.MACD(close=close).macd()
        macd_signal = ta.trend.MACD(close=close).macd_signal()
        macd_histogram = ta.trend.MACD(close=close).macd_diff()
        
        # Stochastique
        stoch_k = ta.momentum.StochasticOscillator(high=high, low=low, close=close).stoch()
        stoch_d = ta.momentum.StochasticOscillator(high=high, low=low, close=close).stoch_signal()
        
        # Williams %R
        williams_r = ta.momentum.WilliamsRIndicator(high=high, low=low, close=close).williams_r()
        
        # Momentum composite
        momentum_score = self.calculate_momentum_score(
            rsi_14, macd_histogram.iloc[-1], stoch_k.iloc[-1], williams_r.iloc[-1]
        )
        
        return {
            "rsi_7": float(rsi_7),
            "rsi_14": float(rsi_14),
            "rsi_21": float(rsi_21),
            "macd_line": float(macd_line.iloc[-1]),
            "macd_signal": float(macd_signal.iloc[-1]),
            "macd_histogram": float(macd_histogram.iloc[-1]),
            "stoch_k": float(stoch_k.iloc[-1]),
            "stoch_d": float(stoch_d.iloc[-1]),
            "williams_r": float(williams_r.iloc[-1]),
            "momentum_score": momentum_score,
            "momentum_trend": "BULLISH" if momentum_score > 0.6 else "BEARISH" if momentum_score < 0.4 else "NEUTRAL"
        }
    
    def calculate_momentum_score(self, rsi: float, macd_hist: float, stoch_k: float, williams_r: float) -> float:
        """Calcule un score de momentum composite"""
        score = 0.0
        
        # RSI contribution
        if rsi > 70:
            score += 0.3
        elif rsi > 60:
            score += 0.2
        elif rsi > 50:
            score += 0.1
        elif rsi < 30:
            score += 0.0
        elif rsi < 40:
            score += 0.1
        else:
            score += 0.15
        
        # MACD contribution
        if macd_hist > 0:
            score += 0.3
        else:
            score += 0.1
        
        # Stochastic contribution
        if stoch_k > 80:
            score += 0.2
        elif stoch_k > 50:
            score += 0.15
        elif stoch_k > 20:
            score += 0.1
        else:
            score += 0.05
        
        # Williams %R contribution
        if williams_r > -20:
            score += 0.2
        elif williams_r > -50:
            score += 0.15
        else:
            score += 0.1
        
        return score / 1.0  # Normalize to 0-1
    
    def calculate_volatility_metrics(self, df: pd.DataFrame) -> Dict:
        """Métriques de volatilité avancées"""
        high, low, close = df['high'], df['low'], df['close']
        
        # ATR multiples
        atr_14 = AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range().iloc[-1]
        atr_21 = AverageTrueRange(high=high, low=low, close=close, window=21).average_true_range().iloc[-1]
        
        # Bollinger Bands
        bb_20 = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
        bb_50 = ta.volatility.BollingerBands(close=close, window=50, window_dev=2)
        
        bb_20_upper = bb_20.bollinger_hband().iloc[-1]
        bb_20_lower = bb_20.bollinger_lband().iloc[-1]
        bb_50_upper = bb_50.bollinger_hband().iloc[-1]
        bb_50_lower = bb_50.bollinger_lband().iloc[-1]
        
        # Bandwidth et position
        bb_20_bandwidth = (bb_20_upper - bb_20_lower) / close.iloc[-1] * 100
        bb_50_bandwidth = (bb_50_upper - bb_50_lower) / close.iloc[-1] * 100
        
        current_price = close.iloc[-1]
        bb_20_position = (current_price - bb_20_lower) / (bb_20_upper - bb_20_lower) * 100
        bb_50_position = (current_price - bb_50_lower) / (bb_50_upper - bb_50_lower) * 100
        
        # Volatility ratio
        volatility_ratio = atr_14 / atr_21 if atr_21 > 0 else 1.0
        
        # Volatility regime
        volatility_regime = self.classify_volatility_regime(atr_14, current_price, bb_20_bandwidth)
        
        return {
            "atr_14": float(atr_14),
            "atr_21": float(atr_21),
            "bb_20_bandwidth": float(bb_20_bandwidth),
            "bb_50_bandwidth": float(bb_50_bandwidth),
            "bb_20_position": float(bb_20_position),
            "bb_50_position": float(bb_50_position),
            "volatility_ratio": float(volatility_ratio),
            "volatility_regime": volatility_regime,
            "current_price": float(current_price)
        }
    
    def classify_volatility_regime(self, atr: float, price: float, bb_bandwidth: float) -> str:
        """Classifie le régime de volatilité"""
        atr_percent = (atr / price) * 10000  # en pips
        
        if atr_percent > 15 or bb_bandwidth > 8:
            return "HIGH_VOLATILITY"
        elif atr_percent < 5 or bb_bandwidth < 3:
            return "LOW_VOLATILITY"
        else:
            return "NORMAL_VOLATILITY"
    
    def calculate_support_resistance(self, df: pd.DataFrame, lookback: int = 100) -> Dict:
        """Détecte les niveaux de support et résistance"""
        high, low, close = df['high'], df['low'], df['close']
        
        # Points pivots
        recent_high = high.tail(lookback).max()
        recent_low = low.tail(lookback).min()
        current_price = close.iloc[-1]
        
        # Niveaux Fibonacci
        fib_levels = self.calculate_fibonacci_levels(recent_low, recent_high)
        
        # Détection des clusters de prix
        price_levels = self.detect_price_clusters(df, lookback)
        
        # Force des niveaux
        support_strength = self.calculate_level_strength(price_levels['supports'], current_price, False)
        resistance_strength = self.calculate_level_strength(price_levels['resistances'], current_price, True)
        
        return {
            "recent_high": float(recent_high),
            "recent_low": float(recent_low),
            "fib_levels": fib_levels,
            "supports": price_levels['supports'],
            "resistances": price_levels['resistances'],
            "support_strength": support_strength,
            "resistance_strength": resistance_strength,
            "distance_to_support": float(current_price - min(price_levels['supports'])) if price_levels['supports'] else 0,
            "distance_to_resistance": float(max(price_levels['resistances']) - current_price) if price_levels['resistances'] else 0
        }
    
    def calculate_fibonacci_levels(self, low: float, high: float) -> Dict:
        """Calcule les niveaux Fibonacci"""
        diff = high - low
        return {
            "0.0": float(low),
            "0.236": float(high - diff * 0.236),
            "0.382": float(high - diff * 0.382),
            "0.5": float(high - diff * 0.5),
            "0.618": float(high - diff * 0.618),
            "0.786": float(high - diff * 0.786),
            "1.0": float(high)
        }
    
    def detect_price_clusters(self, df: pd.DataFrame, lookback: int) -> Dict:
        """Détecte les clusters de prix pour supports/résistances"""
        high = df['high'].tail(lookback)
        low = df['low'].tail(lookback)
        close = df['close'].tail(lookback)
        
        # Combine tous les points de prix significatifs
        all_prices = pd.concat([high, low, close])
        
        # Utilise K-means simplifié pour trouver les clusters
        from sklearn.cluster import KMeans
        import numpy as np
        
        prices_array = all_prices.values.reshape(-1, 1)
        
        # Trouve 5 clusters principaux
        kmeans = KMeans(n_clusters=5, random_state=42)
        kmeans.fit(prices_array)
        
        clusters = kmeans.cluster_centers_.flatten()
        clusters.sort()
        
        current_price = close.iloc[-1]
        
        # Sépare supports et résistances
        supports = [float(c) for c in clusters if c < current_price]
        resistances = [float(c) for c in clusters if c > current_price]
        
        return {
            "supports": supports[-3:] if len(supports) > 3 else supports,  # 3 plus proches
            "resistances": resistances[:3] if len(resistances) > 3 else resistances  # 3 plus proches
        }
    
    def calculate_level_strength(self, levels: List[float], current_price: float, is_resistance: bool) -> float:
        """Calcule la force d'un niveau de support/résistance"""
        if not levels:
            return 0.0
        
        # Plus le niveau est proche, plus il est fort
        if is_resistance:
            closest_level = min(levels)
            distance = closest_level - current_price
        else:
            closest_level = max(levels)
            distance = current_price - closest_level
        
        # Normalise la distance (0-100 pips = force maximale)
        normalized_distance = max(0, 1 - (abs(distance) * 10000 / 100))
        
        return min(normalized_distance, 1.0)

    def calculate_comprehensive_analysis(self, df_m1: pd.DataFrame, df_m5: pd.DataFrame, df_m15: pd.DataFrame) -> Dict[str, Any]:
        """
        Calcule une analyse complète sur plusieurs timeframes
        """
        try:
            # Vérification des données
            if df_m1 is None or len(df_m1) == 0:
                return self._get_empty_analysis()
            
            # Analyses sur les différentes timeframes
            analysis_m1 = self._analyze_single_timeframe(df_m1)
            analysis_m5 = self._analyze_single_timeframe(df_m5) if df_m5 is not None and len(df_m5) > 0 else analysis_m1
            analysis_m15 = self._analyze_single_timeframe(df_m15) if df_m15 is not None and len(df_m15) > 0 else analysis_m1
            
            # Score composite multi-timeframe
            composite_score = self._calculate_composite_score(analysis_m1, analysis_m5, analysis_m15)
            
            # Signal de trading
            action, confidence = self._generate_trading_signal(composite_score, analysis_m1)
            
            return {
                'composite_score': composite_score,
                'action': action,
                'confidence': confidence,
                'timeframe_scores': {
                    'm1': analysis_m1['momentum_score'],
                    'm5': analysis_m5['momentum_score'], 
                    'm15': analysis_m15['momentum_score']
                },
                'momentum_score': analysis_m1['momentum_score'],
                'trend_score': analysis_m1['trend_score'],
                'volatility_score': analysis_m1['volatility_score'],
                'indicators': {
                    'rsi': analysis_m1['rsi_14'],
                    'macd': analysis_m1['macd_histogram'],
                    'stoch': analysis_m1['stoch_k'],
                    'atr': analysis_m1['atr_14'],
                    'ichimoku_strength': analysis_m1['ichimoku_strength']
                },
                'timestamp': pd.Timestamp.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Erreur analyse complète: {e}")
            return self._get_empty_analysis()

    def _analyze_single_timeframe(self, df: pd.DataFrame) -> Dict:
        """Analyse une timeframe unique"""
        try:
            # Utilise vos méthodes existantes
            ichimoku = self.calculate_advanced_ichimoku(df)
            momentum = self.calculate_advanced_momentum(df)
            volatility = self.calculate_volatility_metrics(df)
            
            # Scores normalisés
            momentum_score = momentum['momentum_score']
            trend_score = ichimoku['signal_strength']
            volatility_score = 0.8 if volatility['volatility_regime'] == 'HIGH_VOLATILITY' else 0.5
            
            return {
                'momentum_score': momentum_score,
                'trend_score': trend_score,
                'volatility_score': volatility_score,
                'rsi_14': momentum['rsi_14'],
                'macd_histogram': momentum['macd_histogram'],
                'stoch_k': momentum['stoch_k'],
                'atr_14': volatility['atr_14'],
                'ichimoku_strength': ichimoku['signal_strength']
            }
        except Exception as e:
            print(f"❌ Erreur analyse timeframe: {e}")
            return self._get_default_timeframe_analysis()

    def _calculate_composite_score(self, m1: Dict, m5: Dict, m15: Dict) -> float:
        """Calcule un score composite multi-timeframe"""
        try:
            # Poids différents selon la timeframe
            weights = {'m1': 0.4, 'm5': 0.35, 'm15': 0.25}
            
            # Cohérence des signaux
            momentum_scores = [m1['momentum_score'], m5['momentum_score'], m15['momentum_score']]
            trend_scores = [m1['trend_score'], m5['trend_score'], m15['trend_score']]
            
            # Score pondéré
            composite = (
                np.average(momentum_scores, weights=[0.4, 0.35, 0.25]) * 0.6 +
                np.average(trend_scores, weights=[0.4, 0.35, 0.25]) * 0.4
            )
            
            return float(composite)
        except Exception:
            return 0.5

    def _generate_trading_signal(self, composite_score: float, m1_analysis: Dict) -> tuple:
        """Génère un signal de trading basé sur le score composite"""
        try:
            rsi = m1_analysis['rsi_14']
            macd = m1_analysis['macd_histogram']
            
            if composite_score > 0.7:
                if rsi > 45 and macd > 0:
                    return "BUY", composite_score
                elif rsi < 55 and macd < 0:
                    return "SELL", composite_score
            
            elif composite_score < 0.3:
                # Contre-tendance
                if rsi > 70 and macd > 0:
                    return "SELL", 0.6
                elif rsi < 30 and macd < 0:
                    return "BUY", 0.6
            
            return "HOLD", 0.1
            
        except Exception:
            return "HOLD", 0.0

    def _get_empty_analysis(self) -> Dict:
        """Retourne une analyse vide en cas d'erreur"""
        return {
            'composite_score': 0.5,
            'action': 'HOLD',
            'confidence': 0.0,
            'timeframe_scores': {'m1': 0.5, 'm5': 0.5, 'm15': 0.5},
            'momentum_score': 0.5,
            'trend_score': 0.5,
            'volatility_score': 0.5,
            'indicators': {
                'rsi': 50,
                'macd': 0,
                'stoch': 50,
                'atr': 0,
                'ichimoku_strength': 0.5
            },
            'timestamp': pd.Timestamp.now().isoformat()
        }

    def _get_default_timeframe_analysis(self) -> Dict:
        """Retourne une analyse par défaut"""
        return {
            'momentum_score': 0.5,
            'trend_score': 0.5,
            'volatility_score': 0.5,
            'rsi_14': 50,
            'macd_histogram': 0,
            'stoch_k': 50,
            'atr_14': 0,
            'ichimoku_strength': 0.5
        }