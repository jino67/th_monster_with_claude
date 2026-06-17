import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import json
import os

class MarketRegimeDetector:
    def __init__(self, data_dir: str = "data_historical/market_regimes"):
        self.data_dir = data_dir
        self.regime_cache = {}
        self.regime_history = []
        
    def detect_current_regime(self, symbol: str, df_m1: pd.DataFrame, 
                            df_m5: pd.DataFrame, df_m15: pd.DataFrame) -> Dict:
        """Détecte le régime de marché actuel pour un symbole"""
        
        # Analyse multi-timeframe
        m1_metrics = self.analyze_timeframe_metrics(df_m1, "M1")
        m5_metrics = self.analyze_timeframe_metrics(df_m5, "M5")
        m15_metrics = self.analyze_timeframe_metrics(df_m15, "M15")
        
        # Régime composite
        composite_regime = self.calculate_composite_regime(m1_metrics, m5_metrics, m15_metrics)
        
        # Confidence score
        confidence = self.calculate_regime_confidence(m1_metrics, m5_metrics, m15_metrics)
        
        # Implications trading
        trading_implications = self.get_trading_implications(composite_regime, symbol)
        
        regime_data = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'composite_regime': composite_regime,
            'confidence': confidence,
            'm1_metrics': m1_metrics,
            'm5_metrics': m5_metrics,
            'm15_metrics': m15_metrics,
            'trading_implications': trading_implications,
            'recommended_strategy': trading_implications['recommended_strategy']
        }
        
        # Mettre en cache
        self.regime_cache[symbol] = regime_data
        self.regime_history.append(regime_data)
        
        return regime_data
    
    def analyze_timeframe_metrics(self, df: pd.DataFrame, timeframe: str) -> Dict:
        """Analyse les métriques pour un timeframe spécifique"""
        if len(df) < 50:
            return self.get_default_metrics(timeframe)
        
        close = df['close']
        high = df['high']
        low = df['low']
        
        # Volatility metrics
        volatility = self.calculate_volatility_metrics(close, high, low)
        
        # Trend metrics
        trend = self.calculate_trend_metrics(close)
        
        # Momentum metrics
        momentum = self.calculate_momentum_metrics(close, high, low)
        
        # Volume analysis (si disponible)
        volume = self.calculate_volume_metrics(df)
        
        # Market regime classification
        regime = self.classify_timeframe_regime(volatility, trend, momentum)
        
        return {
            'timeframe': timeframe,
            'volatility': volatility,
            'trend': trend,
            'momentum': momentum,
            'volume': volume,
            'regime': regime,
            'current_price': close.iloc[-1],
            'timestamp': datetime.now().isoformat()
        }
    
    def calculate_volatility_metrics(self, close: pd.Series, high: pd.Series, low: pd.Series) -> Dict:
        """Calcule les métriques de volatilité"""
        # ATR
        atr_14 = self.calculate_atr(high, low, close, 14)
        atr_50 = self.calculate_atr(high, low, close, 50)
        
        # Volatility ratio
        volatility_ratio = atr_14 / atr_50 if atr_50 > 0 else 1.0
        
        # Bollinger Band width
        bb_width = self.calculate_bb_width(close, 20)
        
        # Historical volatility
        returns = close.pct_change().dropna()
        hist_volatility_20 = returns.rolling(20).std().iloc[-1] * np.sqrt(252) * 100  # Annualized %
        
        return {
            'atr_14': atr_14,
            'atr_50': atr_50,
            'volatility_ratio': volatility_ratio,
            'bb_width': bb_width,
            'hist_volatility_20': hist_volatility_20,
            'volatility_regime': self.classify_volatility_regime(atr_14, close.iloc[-1])
        }
    
    def calculate_atr(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> float:
        """Calcule l'ATR"""
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]
    
    def calculate_bb_width(self, close: pd.Series, period: int) -> float:
        """Calcule la largeur des Bollinger Bands"""
        sma = close.rolling(period).mean()
        std = close.rolling(period).std()
        upper_band = sma + (std * 2)
        lower_band = sma - (std * 2)
        bb_width = (upper_band - lower_band) / sma * 100
        return bb_width.iloc[-1]
    
    def classify_volatility_regime(self, atr: float, price: float) -> str:
        """Classifie le régime de volatilité"""
        atr_percent = (atr / price) * 10000  # en pips
        
        if atr_percent > 15:
            return "EXTREME_HIGH_VOL"
        elif atr_percent > 10:
            return "HIGH_VOL"
        elif atr_percent > 5:
            return "MODERATE_VOL"
        elif atr_percent > 2:
            return "LOW_VOL"
        else:
            return "EXTREME_LOW_VOL"
    
    def calculate_trend_metrics(self, close: pd.Series) -> Dict:
        """Calcule les métriques de tendance"""
        # Tendances multiples
        trend_10 = self.assess_trend_strength(close, 10)
        trend_20 = self.assess_trend_strength(close, 20)
        trend_50 = self.assess_trend_strength(close, 50)
        
        # ADX-like trend strength
        trend_strength = self.calculate_trend_strength(close, 14)
        
        # Moving average alignment
        ma_alignment = self.assess_ma_alignment(close)
        
        return {
            'trend_10': trend_10,
            'trend_20': trend_20,
            'trend_50': trend_50,
            'trend_strength': trend_strength,
            'ma_alignment': ma_alignment,
            'dominant_trend': self.get_dominant_trend(trend_10, trend_20, trend_50)
        }
    
    def assess_trend_strength(self, prices: pd.Series, period: int) -> Dict:
        """Évalue la force et direction de la tendance"""
        if len(prices) < period:
            return {'direction': 'SIDEWAYS', 'strength': 0, 'slope': 0}
        
        window = prices.tail(period)
        x = np.arange(len(window))
        slope, intercept = np.polyfit(x, window.values, 1)
        
        # Calcul du R-squared pour la force
        y_pred = slope * x + intercept
        ss_res = np.sum((window.values - y_pred) ** 2)
        ss_tot = np.sum((window.values - np.mean(window.values)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        
        direction = "BULLISH" if slope > 0 else "BEARISH" if slope < 0 else "SIDEWAYS"
        strength = min(r_squared * 100, 100)  # Normalisé 0-100
        
        return {
            'direction': direction,
            'strength': strength,
            'slope': slope,
            'price_change_pct': (window.iloc[-1] - window.iloc[0]) / window.iloc[0] * 100
        }
    
    def calculate_trend_strength(self, close: pd.Series, period: int) -> float:
        """Calcule la force de tendance (similaire ADX)"""
        high, low = close, close  # Simplified for this implementation
        plus_dm = high.diff()
        minus_dm = -low.diff()
        
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        tr = self.calculate_atr(high, low, close, period)
        plus_di = 100 * (plus_dm.rolling(period).mean() / tr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / tr)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(period).mean()
        
        return adx.iloc[-1] if not adx.empty else 0
    
    def assess_ma_alignment(self, close: pd.Series) -> str:
        """Évalue l'alignement des moyennes mobiles"""
        if len(close) < 50:
            return "UNKNOWN"
        
        ma_10 = close.rolling(10).mean().iloc[-1]
        ma_20 = close.rolling(20).mean().iloc[-1]
        ma_50 = close.rolling(50).mean().iloc[-1]
        current_price = close.iloc[-1]
        
        # Vérification de l'alignement bullish
        if current_price > ma_10 > ma_20 > ma_50:
            return "STRONG_BULLISH"
        elif current_price > ma_10 > ma_20:
            return "BULLISH"
        # Vérification de l'alignement bearish
        elif current_price < ma_10 < ma_20 < ma_50:
            return "STRONG_BEARISH"
        elif current_price < ma_10 < ma_20:
            return "BEARISH"
        else:
            return "MIXED"
    
    def get_dominant_trend(self, trend_10: Dict, trend_20: Dict, trend_50: Dict) -> str:
        """Détermine la tendance dominante"""
        trends = [trend_10, trend_20, trend_50]
        directions = [t['direction'] for t in trends]
        strengths = [t['strength'] for t in trends]
        
        bullish_count = directions.count('BULLISH')
        bearish_count = directions.count('BEARISH')
        
        if bullish_count >= 2 and np.mean(strengths) > 30:
            return "BULLISH"
        elif bearish_count >= 2 and np.mean(strengths) > 30:
            return "BEARISH"
        else:
            return "SIDEWAYS"
    
    def calculate_momentum_metrics(self, close: pd.Series, high: pd.Series, low: pd.Series) -> Dict:
        """Calcule les métriques de momentum"""
        # RSI multiples
        rsi_14 = self.calculate_rsi(close, 14)
        rsi_28 = self.calculate_rsi(close, 28)
        
        # MACD
        macd_hist = self.calculate_macd_histogram(close)
        
        # Stochastic
        stoch = self.calculate_stochastic(high, low, close, 14)
        
        # Momentum oscillators
        momentum_oscillators = self.calculate_momentum_oscillators(close)
        
        return {
            'rsi_14': rsi_14,
            'rsi_28': rsi_28,
            'macd_hist': macd_hist,
            'stoch_k': stoch['k'],
            'stoch_d': stoch['d'],
            'momentum_score': momentum_oscillators['composite_score'],
            'momentum_regime': momentum_oscillators['regime']
        }
    
    def calculate_rsi(self, series: pd.Series, period: int) -> float:
        """Calcule le RSI"""
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not rsi.empty else 50
    
    def calculate_macd_histogram(self, series: pd.Series) -> float:
        """Calcule l'histogramme MACD"""
        ema_12 = series.ewm(span=12).mean()
        ema_26 = series.ewm(span=26).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9).mean()
        histogram = macd - signal
        return histogram.iloc[-1] if not histogram.empty else 0
    
    def calculate_stochastic(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> Dict:
        """Calcule le stochastique"""
        lowest_low = low.rolling(period).min()
        highest_high = high.rolling(period).max()
        k = 100 * (close - lowest_low) / (highest_high - lowest_low)
        d = k.rolling(3).mean()
        return {
            'k': k.iloc[-1] if not k.empty else 50,
            'd': d.iloc[-1] if not d.empty else 50
        }
    
    def calculate_momentum_oscillators(self, close: pd.Series) -> Dict:
        """Calcule les oscillateurs de momentum composites"""
        # Rate of Change
        roc_10 = (close.iloc[-1] - close.iloc[-10]) / close.iloc[-10] * 100
        roc_20 = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] * 100
        
        # Williams %R simplifié
        highest_14 = close.tail(14).max()
        lowest_14 = close.tail(14).min()
        williams_r = -100 * (highest_14 - close.iloc[-1]) / (highest_14 - lowest_14) if highest_14 != lowest_14 else -50
        
        # Score composite
        composite_score = (
            (self.calculate_rsi(close, 14) / 100) * 0.3 +
            (min(max(roc_10 / 10, -1), 1) + 1) / 2 * 0.3 +
            (min(max(williams_r / -100, 0), 1)) * 0.4
        )
        
        # Régime de momentum
        if composite_score > 0.7:
            regime = "STRONG_BULLISH"
        elif composite_score > 0.6:
            regime = "BULLISH"
        elif composite_score < 0.3:
            regime = "STRONG_BEARISH"
        elif composite_score < 0.4:
            regime = "BEARISH"
        else:
            regime = "NEUTRAL"
        
        return {
            'composite_score': composite_score,
            'regime': regime,
            'roc_10': roc_10,
            'roc_20': roc_20,
            'williams_r': williams_r
        }
    
    def calculate_volume_metrics(self, df: pd.DataFrame) -> Dict:
        """Calcule les métriques de volume"""
        if 'tick_volume' not in df.columns:
            return {'volume_available': False}
        
        volume = df['tick_volume']
        if len(volume) < 20:
            return {'volume_available': False}
        
        # Volume SMA
        volume_sma_20 = volume.rolling(20).mean().iloc[-1]
        current_volume = volume.iloc[-1]
        volume_ratio = current_volume / volume_sma_20 if volume_sma_20 > 0 else 1
        
        # Volume trend
        volume_trend = self.assess_volume_trend(volume)
        
        return {
            'volume_available': True,
            'volume_ratio': volume_ratio,
            'volume_trend': volume_trend,
            'current_volume': current_volume,
            'avg_volume_20': volume_sma_20
        }
    
    def assess_volume_trend(self, volume: pd.Series) -> str:
        """Évalue la tendance du volume"""
        if len(volume) < 10:
            return "UNKNOWN"
        
        recent_volume = volume.tail(5).mean()
        historical_volume = volume.tail(20).mean()
        
        if recent_volume > historical_volume * 1.2:
            return "INCREASING"
        elif recent_volume < historical_volume * 0.8:
            return "DECREASING"
        else:
            return "STABLE"
    
    def classify_timeframe_regime(self, volatility: Dict, trend: Dict, momentum: Dict) -> str:
        """Classifie le régime pour un timeframe spécifique"""
        # Combinaison des métriques pour déterminer le régime
        volatility_score = self.map_volatility_to_score(volatility['volatility_regime'])
        trend_score = trend['trend_strength'] / 100  # Normalisé 0-1
        momentum_score = momentum['momentum_score']
        
        # Score composite
        composite_score = (
            volatility_score * 0.3 +
            trend_score * 0.4 +
            momentum_score * 0.3
        )
        
        # Classification finale
        if composite_score > 0.7:
            return "TRENDING_STRONG"
        elif composite_score > 0.6:
            return "TRENDING_MODERATE"
        elif composite_score < 0.4:
            return "RANGING_CONSOLIDATION"
        elif volatility_score > 0.7:
            return "VOLATILE_RANGING"
        else:
            return "NEUTRAL"


    
    def map_volatility_to_score(self, volatility_regime: str) -> float:
        """Convertit le régime de volatilité en score numérique"""
        volatility_scores = {
            "EXTREME_HIGH_VOL": 0.9,
            "HIGH_VOL": 0.7,
            "MODERATE_VOL": 0.5,
            "LOW_VOL": 0.3,
            "EXTREME_LOW_VOL": 0.1
        }
        return volatility_scores.get(volatility_regime, 0.5)
    
    def calculate_composite_regime(self, m1_metrics: Dict, m5_metrics: Dict, m15_metrics: Dict) -> str:
        """Calcule le régime composite multi-timeframe"""
        regimes = [m1_metrics['regime'], m5_metrics['regime'], m15_metrics['regime']]
        
        # Priorité aux régimes de tendance
        trending_regimes = [r for r in regimes if "TRENDING" in r]
        volatile_regimes = [r for r in regimes if "VOLATILE" in r]
        
        if len(trending_regimes) >= 2:
            return "TRENDING_MARKET"
        elif len(volatile_regimes) >= 2:
            return "VOLATILE_MARKET"
        elif all("RANGING" in r for r in regimes):
            return "RANGING_MARKET"
        elif all("NEUTRAL" in r for r in regimes):
            return "NEUTRAL_MARKET"
        else:
            return "MIXED_MARKET"
    
    def calculate_regime_confidence(self, m1_metrics: Dict, m5_metrics: Dict, m15_metrics: Dict) -> float:
        """Calcule le score de confiance du régime"""
        # Cohérence entre timeframes
        regimes = [m1_metrics['regime'], m5_metrics['regime'], m15_metrics['regime']]
        unique_regimes = len(set(regimes))
        
        if unique_regimes == 1:
            consistency_score = 0.9
        elif unique_regimes == 2:
            consistency_score = 0.6
        else:
            consistency_score = 0.3
        
        # Force des signaux individuels
        strength_scores = [
            m1_metrics['trend']['trend_strength'] / 100,
            m5_metrics['trend']['trend_strength'] / 100,
            m15_metrics['trend']['trend_strength'] / 100
        ]
        avg_strength = np.mean(strength_scores)
        
        return (consistency_score * 0.6 + avg_strength * 0.4)
    
    def get_trading_implications(self, composite_regime: str, symbol: str) -> Dict:
        """Retourne les implications trading pour le régime détecté"""
        implications = {
            "TRENDING_MARKET": {
                "recommended_strategy": "TREND_FOLLOWING",
                "risk_adjustment": 1.0,
                "position_holding": "MEDIUM_TO_LONG",
                "entry_approach": "PULLBACK_ENTRY",
                "stop_placement": "BELOW_SUPPORT_ABOVE_RESISTANCE"
            },
            "VOLATILE_MARKET": {
                "recommended_strategy": "BREAKOUT_MOMENTUM",
                "risk_adjustment": 0.7,
                "position_holding": "SHORT",
                "entry_approach": "BREAKOUT_CONFIRMATION",
                "stop_placement": "ATR_BASED_WIDE"
            },
            "RANGING_MARKET": {
                "recommended_strategy": "MEAN_REVERSION",
                "risk_adjustment": 0.8,
                "position_holding": "SHORT",
                "entry_approach": "EXTREMES_FADING",
                "stop_placement": "OUTSIDE_RANGE"
            },
            "NEUTRAL_MARKET": {
                "recommended_strategy": "SCALPING",
                "risk_adjustment": 0.9,
                "position_holding": "VERY_SHORT",
                "entry_approach": "MICRO_MOVEMENTS",
                "stop_placement": "TIGHT_ATR"
            },
            "MIXED_MARKET": {
                "recommended_strategy": "ADAPTIVE_MIXED",
                "risk_adjustment": 0.6,
                "position_holding": "SHORT",
                "entry_approach": "CONFIRMATION_REQUIRED",
                "stop_placement": "CONSERVATIVE_ATR"
            }
        }
        
        return implications.get(composite_regime, implications["MIXED_MARKET"])
    
    def save_regime_history(self):
        """Sauvegarde l'historique des régimes"""
        if not self.regime_history:
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"regime_history_{timestamp}.json"
        filepath = os.path.join(self.data_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.regime_history, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Historique des régimes sauvegardé: {filename}")


    def get_default_metrics(self, timeframe: str = "M5") -> Dict:
        """Retourne les métriques par défaut - MÉTHODE MANQUANTE"""
        return {
            'timeframe': timeframe,
            'volatility': {
                'atr_14': 0.0,
                'atr_50': 0.0,
                'volatility_ratio': 1.0,
                'bb_width': 0.0,
                'hist_volatility_20': 0.0,
                'volatility_regime': 'MODERATE_VOL'
            },
            'trend': {
                'trend_10': {'direction': 'SIDEWAYS', 'strength': 0, 'slope': 0},
                'trend_20': {'direction': 'SIDEWAYS', 'strength': 0, 'slope': 0},
                'trend_50': {'direction': 'SIDEWAYS', 'strength': 0, 'slope': 0},
                'trend_strength': 0.0,
                'ma_alignment': 'UNKNOWN',
                'dominant_trend': 'SIDEWAYS'
            },
            'momentum': {
                'rsi_14': 50.0,
                'rsi_28': 50.0,
                'macd_hist': 0.0,
                'stoch_k': 50.0,
                'stoch_d': 50.0,
                'momentum_score': 0.5,
                'momentum_regime': 'NEUTRAL'
            },
            'volume': {
                'volume_available': False,
                'volume_ratio': 1.0,
                'volume_trend': 'UNKNOWN',
                'current_volume': 0,
                'avg_volume_20': 0
            },
            'regime': 'NEUTRAL',
            'current_price': 0.0,
            'timestamp': datetime.now().isoformat()
        }