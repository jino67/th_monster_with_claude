import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime

class MultiTimeframeEngine:
    def __init__(self):
        self.timeframe_weights = {
            'M1': 0.15,   # Court terme - réactivité
            'M5': 0.25,   # Moyen terme - équilibre
            'M15': 0.35,  # Long terme - tendance
            'H1': 0.25    # Très long terme - contexte
        }
        self.signal_cache = {}
        
    def analyze_multi_timeframe(self, symbol: str, data_dict: Dict) -> Dict:
        """Analyse multi-timeframe complète"""
        print(f"🔍 Analyse multi-timeframe pour {symbol}...")
        
        # Validation des données
        if not self.validate_timeframe_data(data_dict):
            return {'error': 'Données de timeframe incomplètes'}
        
        # Analyse individuelle par timeframe
        timeframe_analyses = {}
        for tf, df in data_dict.items():
            timeframe_analyses[tf] = self.analyze_single_timeframe(df, tf)
        
        # Fusion des analyses
        composite_analysis = self.merge_timeframe_analyses(timeframe_analyses)
        
        # Génération du signal composite
        composite_signal = self.generate_composite_signal(composite_analysis)
        
        # Confirmation du signal
        signal_confidence = self.assess_signal_confidence(composite_analysis)
        
        result = {
            'symbol': symbol,
            'timeframe_analyses': timeframe_analyses,
            'composite_analysis': composite_analysis,
            'composite_signal': composite_signal,
            'signal_confidence': signal_confidence,
            'recommended_action': composite_signal['action'],
            'timestamp': datetime.now().isoformat()
        }
        
        self.signal_cache[symbol] = result
        return result
    
    def validate_timeframe_data(self, data_dict: Dict) -> bool:
        """Valide les données de timeframe"""
        required_timeframes = ['M1', 'M5', 'M15']
        
        for tf in required_timeframes:
            if tf not in data_dict or data_dict[tf] is None or len(data_dict[tf]) < 10:
                print(f"⚠️ Données insuffisantes pour le timeframe {tf}")
                return False
        
        return True
    
    def analyze_single_timeframe(self, df: pd.DataFrame, timeframe: str) -> Dict:
        """Analyse un timeframe individuel"""
        if df is None or len(df) < 10:
            return self.get_default_analysis(timeframe)
        
        close = df['close']
        high = df['high']
        low = df['low']
        
        # Tendances multiples
        trend_analysis = self.analyze_trends(close, timeframe)
        
        # Momentum
        momentum_analysis = self.analyze_momentum(close, high, low, timeframe)
        
        # Volatilité
        volatility_analysis = self.analyze_volatility(close, high, low, timeframe)
        
        # Support/Résistance
        support_resistance = self.identify_support_resistance(high, low, close, timeframe)
        
        # Signal individuel
        individual_signal = self.generate_individual_signal(
            trend_analysis, momentum_analysis, volatility_analysis, support_resistance
        )
        
        return {
            'timeframe': timeframe,
            'trend_analysis': trend_analysis,
            'momentum_analysis': momentum_analysis,
            'volatility_analysis': volatility_analysis,
            'support_resistance': support_resistance,
            'individual_signal': individual_signal,
            'data_quality': self.assess_data_quality(df),
            'current_price': close.iloc[-1]
        }
    
    def analyze_trends(self, close: pd.Series, timeframe: str) -> Dict:
        """Analyse les tendances sur différents horizons"""
        trends = {}
        
        # Court terme (5-10 bougies)
        if len(close) >= 10:
            trends['short_term'] = self.assess_trend_direction(close.tail(10))
            trends['short_term_strength'] = self.calculate_trend_strength(close.tail(10))
        
        # Moyen terme (20-30 bougies)
        if len(close) >= 30:
            trends['medium_term'] = self.assess_trend_direction(close.tail(30))
            trends['medium_term_strength'] = self.calculate_trend_strength(close.tail(30))
        
        # Long terme (50-100 bougies)
        if len(close) >= 100:
            trends['long_term'] = self.assess_trend_direction(close.tail(100))
            trends['long_term_strength'] = self.calculate_trend_strength(close.tail(100))
        
        # Tendance dominante
        trends['dominant_trend'] = self.determine_dominant_trend(trends)
        
        # Alignement des tendances
        trends['alignment'] = self.assess_trend_alignment(trends)
        
        return trends
    
    def assess_trend_direction(self, prices: pd.Series) -> str:
        """Évalue la direction de la tendance"""
        if len(prices) < 5:
            return "SIDEWAYS"
        
        # Régression linéaire
        x = np.arange(len(prices))
        slope, _ = np.polyfit(x, prices.values, 1)
        
        # Pourcentage de changement
        price_change = (prices.iloc[-1] - prices.iloc[0]) / prices.iloc[0] * 100
        
        if slope > 0 and price_change > 1.0:
            return "BULLISH"
        elif slope < 0 and price_change < -1.0:
            return "BEARISH"
        else:
            return "SIDEWAYS"
    
    def calculate_trend_strength(self, prices: pd.Series) -> float:
        """Calcule la force de la tendance"""
        if len(prices) < 5:
            return 0.0
        
        # R-carré de la régression linéaire
        x = np.arange(len(prices))
        slope, intercept = np.polyfit(x, prices.values, 1)
        y_pred = slope * x + intercept
        ss_res = np.sum((prices.values - y_pred) ** 2)
        ss_tot = np.sum((prices.values - np.mean(prices.values)) ** 2)
        
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        return min(r_squared * 100, 100)  # Normalisé 0-100
    
    def determine_dominant_trend(self, trends: Dict) -> str:
        """Détermine la tendance dominante"""
        trend_strengths = {}
        
        for period, direction in [('short_term', 'short_term_strength'),
                                ('medium_term', 'medium_term_strength'),
                                ('long_term', 'long_term_strength')]:
            if period in trends and direction in trends:
                trend_dir = trends[period]
                strength = trends[direction]
                
                if trend_dir not in trend_strengths:
                    trend_strengths[trend_dir] = 0
                trend_strengths[trend_dir] += strength
        
        if not trend_strengths:
            return "SIDEWAYS"
        
        return max(trend_strengths.items(), key=lambda x: x[1])[0]
    
    def assess_trend_alignment(self, trends: Dict) -> str:
        """Évalue l'alignement des tendances"""
        trend_directions = []
        
        for period in ['short_term', 'medium_term', 'long_term']:
            if period in trends:
                trend_directions.append(trends[period])
        
        if not trend_directions:
            return "UNKNOWN"
        
        unique_directions = set(trend_directions)
        
        if len(unique_directions) == 1:
            return "PERFECT_ALIGNMENT"
        elif len(unique_directions) == 2 and "SIDEWAYS" in unique_directions:
            return "PARTIAL_ALIGNMENT"
        else:
            return "MIXED"
    
    def analyze_momentum(self, close: pd.Series, high: pd.Series, low: pd.Series, timeframe: str) -> Dict:
        """Analyse le momentum"""
        momentum = {}
        
        # RSI multiples
        for period in [7, 14, 21]:
            if len(close) >= period:
                rsi = self.calculate_rsi(close, period)
                momentum[f'rsi_{period}'] = rsi.iloc[-1] if not rsi.empty else 50
        
        # MACD
        if len(close) >= 26:
            macd_line, macd_signal, macd_hist = self.calculate_macd(close)
            momentum['macd_histogram'] = macd_hist.iloc[-1] if not macd_hist.empty else 0
        
        # Stochastic
        if len(close) >= 14:
            stoch_k, stoch_d = self.calculate_stochastic(high, low, close, 14)
            momentum['stoch_k'] = stoch_k
            momentum['stoch_d'] = stoch_d
        
        # Momentum composite
        momentum['composite_score'] = self.calculate_momentum_composite_score(momentum)
        momentum['direction'] = "BULLISH" if momentum['composite_score'] > 0.6 else "BEARISH" if momentum['composite_score'] < 0.4 else "NEUTRAL"
        
        return momentum
    
    def calculate_rsi(self, series: pd.Series, period: int) -> pd.Series:
        """Calcule le RSI"""
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_macd(self, series: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calcule le MACD"""
        ema_12 = series.ewm(span=12).mean()
        ema_26 = series.ewm(span=26).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9).mean()
        histogram = macd - signal
        return macd, signal, histogram
    
    def calculate_stochastic(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> Tuple[float, float]:
        """Calcule le stochastique"""
        lowest_low = low.rolling(period).min()
        highest_high = high.rolling(period).max()
        k = 100 * (close - lowest_low) / (highest_high - lowest_low)
        d = k.rolling(3).mean()
        return k.iloc[-1] if not k.empty else 50, d.iloc[-1] if not d.empty else 50
    
    def calculate_momentum_composite_score(self, momentum: Dict) -> float:
        """Calcule un score de momentum composite"""
        score = 0.0
        factors = 0
        
        # RSI contribution
        if 'rsi_14' in momentum:
            rsi_score = (momentum['rsi_14'] - 50) / 50  # -1 to 1
            score += rsi_score * 0.4
            factors += 0.4
        
        # MACD contribution
        if 'macd_histogram' in momentum:
            macd_score = np.tanh(momentum['macd_histogram'] * 10)  # Normalisé -1 to 1
            score += macd_score * 0.3
            factors += 0.3
        
        # Stochastic contribution
        if 'stoch_k' in momentum and 'stoch_d' in momentum:
            stoch_score = ((momentum['stoch_k'] - 50) / 50) * 0.3
            score += stoch_score
            factors += 0.3
        
        # Normalise le score final
        if factors > 0:
            final_score = (score / factors + 1) / 2  # 0 to 1
            return final_score
        
        return 0.5
    
    def analyze_volatility(self, close: pd.Series, high: pd.Series, low: pd.Series, timeframe: str) -> Dict:
        """Analyse la volatilité"""
        volatility = {}
        
        # ATR
        if len(close) >= 14:
            atr = self.calculate_atr(high, low, close, 14)
            volatility['atr_14'] = atr
            volatility['atr_percent'] = (atr / close.iloc[-1]) * 100
        
        # Bollinger Bands width
        if len(close) >= 20:
            bb_width = self.calculate_bb_width(close, 20)
            volatility['bb_width'] = bb_width
        
        # Volatilité historique
        if len(close) >= 20:
            returns = close.pct_change().dropna()
            hist_volatility = returns.rolling(20).std().iloc[-1] * np.sqrt(252) * 100
            volatility['historical_volatility'] = hist_volatility
        
        # Régime de volatilité
        volatility['regime'] = self.classify_volatility_regime(volatility)
        
        return volatility
    
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
    
    def classify_volatility_regime(self, volatility: Dict) -> str:
        """Classifie le régime de volatilité"""
        atr_percent = volatility.get('atr_percent', 0)
        bb_width = volatility.get('bb_width', 0)
        
        if atr_percent > 1.0 or bb_width > 8:
            return "HIGH_VOLATILITY"
        elif atr_percent < 0.3 or bb_width < 3:
            return "LOW_VOLATILITY"
        else:
            return "NORMAL_VOLATILITY"
    
    def identify_support_resistance(self, high: pd.Series, low: pd.Series, close: pd.Series, timeframe: str) -> Dict:
        """Identifie les niveaux de support et résistance"""
        if len(high) < 20:
            return {'supports': [], 'resistances': []}
        
        current_price = close.iloc[-1]
        
        # Niveaux récents
        recent_high = high.tail(20).max()
        recent_low = low.tail(20).min()
        
        # Niveaux psychologiques
        psychological_levels = self.calculate_psychological_levels(current_price)
        
        supports = []
        resistances = []
        
        # Support récent
        if recent_low < current_price:
            supports.append({
                'price': recent_low,
                'strength': 0.8,
                'type': 'RECENT_LOW'
            })
        
        # Résistance récente
        if recent_high > current_price:
            resistances.append({
                'price': recent_high,
                'strength': 0.8,
                'type': 'RECENT_HIGH'
            })
        
        # Niveaux psychologiques
        for level in psychological_levels:
            if level < current_price:
                supports.append({
                    'price': level,
                    'strength': 0.6,
                    'type': 'PSYCHOLOGICAL'
                })
            else:
                resistances.append({
                    'price': level,
                    'strength': 0.6,
                    'type': 'PSYCHOLOGICAL'
                })
        
        return {
            'supports': sorted(supports, key=lambda x: x['price'], reverse=True),
            'resistances': sorted(resistances, key=lambda x: x['price']),
            'current_price': current_price
        }
    
    def calculate_psychological_levels(self, price: float) -> List[float]:
        """Calcule les niveaux psychologiques"""
        base = round(price, 2)
        levels = []
        
        # Niveaux autour du prix actuel
        for offset in [-0.10, -0.05, -0.02, 0.02, 0.05, 0.10]:
            levels.append(base + offset)
        
        return levels
    
    def generate_individual_signal(self, trend_analysis: Dict, momentum_analysis: Dict,
                                 volatility_analysis: Dict, support_resistance: Dict) -> Dict:
        """Génère un signal individuel pour le timeframe"""
        action = "HOLD"
        confidence = 0.0
        
        # Logique de signal basique
        dominant_trend = trend_analysis.get('dominant_trend', 'SIDEWAYS')
        momentum_direction = momentum_analysis.get('direction', 'NEUTRAL')
        momentum_score = momentum_analysis.get('composite_score', 0.5)
        
        # Tendance bullish avec momentum confirmé
        if (dominant_trend == "BULLISH" and momentum_direction == "BULLISH" and
            momentum_score > 0.6):
            action = "BUY"
            confidence = momentum_score
        
        # Tendance bearish avec momentum confirmé
        elif (dominant_trend == "BEARISH" and momentum_direction == "BEARISH" and
              momentum_score < 0.4):
            action = "SELL"
            confidence = 1 - momentum_score
        
        return {
            'action': action,
            'confidence': confidence,
            'trend_alignment': trend_analysis.get('alignment', 'UNKNOWN'),
            'momentum_strength': momentum_score
        }
    
    def assess_data_quality(self, df: pd.DataFrame) -> float:
        """Évalue la qualité des données"""
        if df is None or len(df) == 0:
            return 0.0
        
        # Complétude des données
        completeness = 1 - (df.isnull().sum().sum() / df.size)
        
        # Cohérence des prix
        price_consistency = self.check_price_consistency(df)
        
        return (completeness + price_consistency) / 2
    
    def check_price_consistency(self, df: pd.DataFrame) -> float:
        """Vérifie la cohérence des prix"""
        try:
            # Vérifie que high >= low et high >= close >= low
            valid_high_low = (df['high'] >= df['low']).all()
            valid_close = ((df['close'] >= df['low']) & (df['close'] <= df['high'])).all()
            
            consistency_score = 0.0
            if valid_high_low:
                consistency_score += 0.5
            if valid_close:
                consistency_score += 0.5
                
            return consistency_score
            
        except Exception:
            return 0.0
    
    def get_default_analysis(self, timeframe: str) -> Dict:
        """Retourne une analyse par défaut"""
        return {
            'timeframe': timeframe,
            'trend_analysis': {'dominant_trend': 'SIDEWAYS', 'alignment': 'UNKNOWN'},
            'momentum_analysis': {'direction': 'NEUTRAL', 'composite_score': 0.5},
            'volatility_analysis': {'regime': 'NORMAL_VOLATILITY'},
            'support_resistance': {'supports': [], 'resistances': []},
            'individual_signal': {'action': 'HOLD', 'confidence': 0.0},
            'data_quality': 0.0,
            'current_price': 0
        }
    
    def merge_timeframe_analyses(self, timeframe_analyses: Dict) -> Dict:
        """Fusionne les analyses de tous les timeframes"""
        composite = {
            'weighted_signals': [],
            'trend_alignment_summary': {},
            'momentum_summary': {},
            'volatility_summary': {},
            'consensus_score': 0.0
        }
        
        total_weight = 0
        weighted_action_scores = {'BUY': 0, 'SELL': 0, 'HOLD': 0}
        
        for tf, analysis in timeframe_analyses.items():
            weight = self.timeframe_weights.get(tf, 0.1)
            signal = analysis['individual_signal']
            
            # Score pondéré par action
            action = signal['action']
            confidence = signal['confidence']
            weighted_action_scores[action] += confidence * weight
            
            total_weight += weight
            
            # Stocke le signal pondéré
            composite['weighted_signals'].append({
                'timeframe': tf,
                'action': action,
                'confidence': confidence,
                'weight': weight,
                'weighted_confidence': confidence * weight
            })
        
        # Calcule le consensus
        if total_weight > 0:
            for action in weighted_action_scores:
                weighted_action_scores[action] /= total_weight
        
        # Détermine l'action consensus
        consensus_action = max(weighted_action_scores.items(), key=lambda x: x[1])[0]
        composite['consensus_score'] = weighted_action_scores[consensus_action]
        composite['consensus_action'] = consensus_action
        
        # Résumé des tendances
        composite['trend_alignment_summary'] = self.summarize_trend_alignment(timeframe_analyses)
        
        # Résumé du momentum
        composite['momentum_summary'] = self.summarize_momentum(timeframe_analyses)
        
        # Résumé de la volatilité
        composite['volatility_summary'] = self.summarize_volatility(timeframe_analyses)
        
        return composite
    
    def summarize_trend_alignment(self, timeframe_analyses: Dict) -> Dict:
        """Résume l'alignement des tendances"""
        trend_directions = []
        alignment_statuses = []
        
        for tf, analysis in timeframe_analyses.items():
            trend_analysis = analysis['trend_analysis']
            if 'dominant_trend' in trend_analysis:
                trend_directions.append(trend_analysis['dominant_trend'])
            if 'alignment' in trend_analysis:
                alignment_statuses.append(trend_analysis['alignment'])
        
        return {
            'trend_directions': trend_directions,
            'alignment_statuses': alignment_statuses,
            'bullish_count': trend_directions.count('BULLISH'),
            'bearish_count': trend_directions.count('BEARISH'),
            'sideways_count': trend_directions.count('SIDEWAYS'),
            'perfect_alignment_count': alignment_statuses.count('PERFECT_ALIGNMENT')
        }
    
    def summarize_momentum(self, timeframe_analyses: Dict) -> Dict:
        """Résume le momentum"""
        momentum_scores = []
        momentum_directions = []
        
        for tf, analysis in timeframe_analyses.items():
            momentum_analysis = analysis['momentum_analysis']
            if 'composite_score' in momentum_analysis:
                momentum_scores.append(momentum_analysis['composite_score'])
            if 'direction' in momentum_analysis:
                momentum_directions.append(momentum_analysis['direction'])
        
        if momentum_scores:
            avg_momentum = sum(momentum_scores) / len(momentum_scores)
        else:
            avg_momentum = 0.5
        
        return {
            'average_momentum_score': avg_momentum,
            'momentum_directions': momentum_directions,
            'bullish_momentum_count': momentum_directions.count('BULLISH'),
            'bearish_momentum_count': momentum_directions.count('BEARISH')
        }
    
    def summarize_volatility(self, timeframe_analyses: Dict) -> Dict:
        """Résume la volatilité"""
        volatility_regimes = []
        
        for tf, analysis in timeframe_analyses.items():
            volatility_analysis = analysis['volatility_analysis']
            if 'regime' in volatility_analysis:
                volatility_regimes.append(volatility_analysis['regime'])
        
        return {
            'volatility_regimes': volatility_regimes,
            'high_volatility_count': volatility_regimes.count('HIGH_VOLATILITY'),
            'low_volatility_count': volatility_regimes.count('LOW_VOLATILITY'),
            'dominant_regime': max(set(volatility_regimes), key=volatility_regimes.count) if volatility_regimes else 'UNKNOWN'
        }
    
    def generate_composite_signal(self, composite_analysis: Dict) -> Dict:
        """Génère un signal composite"""
        consensus_action = composite_analysis['consensus_action']
        consensus_score = composite_analysis['consensus_score']
        
        # Analyse de la confirmation
        confirmation_analysis = self.assess_signal_confirmation(composite_analysis)
        
        # Score de confiance final
        final_confidence = self.calculate_final_confidence(consensus_score, confirmation_analysis)
        
        return {
            'action': consensus_action,
            'confidence': final_confidence,
            'consensus_score': consensus_score,
            'confirmation_analysis': confirmation_analysis,
            'recommendation': self.get_recommendation_level(final_confidence)
        }
    
    def assess_signal_confirmation(self, composite_analysis: Dict) -> Dict:
        """Évalue la confirmation du signal"""
        trend_summary = composite_analysis['trend_alignment_summary']
        momentum_summary = composite_analysis['momentum_summary']
        
        # Confirmation par les tendances
        trend_confirmation = trend_summary['perfect_alignment_count'] / len(self.timeframe_weights)
        
        # Confirmation par le momentum
        momentum_bullish_ratio = momentum_summary['bullish_momentum_count'] / len(self.timeframe_weights)
        momentum_bearish_ratio = momentum_summary['bearish_momentum_count'] / len(self.timeframe_weights)
        momentum_confirmation = max(momentum_bullish_ratio, momentum_bearish_ratio)
        
        # Score de confirmation composite
        composite_confirmation = (trend_confirmation * 0.6 + momentum_confirmation * 0.4)
        
        return {
            'trend_confirmation': trend_confirmation,
            'momentum_confirmation': momentum_confirmation,
            'composite_confirmation': composite_confirmation,
            'is_confirmed': composite_confirmation > 0.7
        }
    
    def calculate_final_confidence(self, consensus_score: float, confirmation_analysis: Dict) -> float:
        """Calcule la confiance finale du signal"""
        base_confidence = consensus_score
        confirmation_bonus = confirmation_analysis['composite_confirmation'] * 0.3
        
        final_confidence = base_confidence + confirmation_bonus
        return min(final_confidence, 1.0)
    
    def get_recommendation_level(self, confidence: float) -> str:
        """Retourne le niveau de recommandation"""
        if confidence > 0.8:
            return "STRONG"
        elif confidence > 0.65:
            return "MODERATE"
        elif confidence > 0.5:
            return "WEAK"
        else:
            return "AVOID"
    
    def assess_signal_confidence(self, composite_analysis: Dict) -> Dict:
        """Évalue la confiance globale du signal"""
        signal = composite_analysis['composite_signal']
        
        return {
            'final_confidence': signal['confidence'],
            'recommendation_level': signal['recommendation'],
            'confirmation_status': composite_analysis['composite_signal']['confirmation_analysis']['is_confirmed'],
            'timeframe_agreement': self.calculate_timeframe_agreement(composite_analysis),
            'quality_score': self.calculate_quality_score(composite_analysis)
        }
    
    def calculate_timeframe_agreement(self, composite_analysis: Dict) -> float:
        """Calcule le niveau d'accord entre les timeframes"""
        signals = composite_analysis['weighted_signals']
        if not signals:
            return 0.0
        
        actions = [s['action'] for s in signals]
        most_common_action = max(set(actions), key=actions.count)
        agreement_ratio = actions.count(most_common_action) / len(actions)
        
        return agreement_ratio
    
    def calculate_quality_score(self, composite_analysis: Dict) -> float:
        """Calcule un score de qualité global"""
        quality_scores = []
        
        for signal in composite_analysis['weighted_signals']:
            # Le score de qualité est basé sur la confiance et le poids du timeframe
            quality_score = signal['weighted_confidence'] * signal['weight']
            quality_scores.append(quality_score)
        
        if quality_scores:
            return sum(quality_scores) / len(quality_scores)
        return 0.0