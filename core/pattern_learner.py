import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json
from collections import defaultdict, deque
import statistics

class PatternLearner:
    def __init__(self, data_dir: str = "MonsterMind_int/patterns"):
        self.data_dir = data_dir
        self.patterns_db = {}
        self.performance_history = deque(maxlen=1000)
        self.market_conditions_db = {}
        self.learning_rate = 0.1
        
        self._ensure_directory()
        self.load_patterns()
    
    def _ensure_directory(self):
        """Crée le répertoire de patterns"""
        import os
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def load_patterns(self):
        """Charge les patterns historiques"""
        try:
            patterns_file = f"{self.data_dir}/patterns_db.json"
            if os.path.exists(patterns_file):
                with open(patterns_file, 'r') as f:
                    self.patterns_db = json.load(f)
                print(f"✅ {len(self.patterns_db)} patterns chargés")
        except Exception as e:
            print(f"❌ Erreur chargement patterns: {e}")
    
    def learn_from_trade(self, trade_data: Dict, outcome: str, market_conditions: Dict):
        """Apprend d'un trade complet"""
        pattern_key = self.extract_pattern_key(trade_data, market_conditions)
        
        if pattern_key not in self.patterns_db:
            self.patterns_db[pattern_key] = {
                'occurrences': 0,
                'successes': 0,
                'total_profit': 0,
                'market_conditions': market_conditions,
                'first_seen': datetime.now().isoformat(),
                'last_seen': datetime.now().isoformat(),
                'recent_outcomes': deque(maxlen=10)
            }
        
        pattern = self.patterns_db[pattern_key]
        pattern['occurrences'] += 1
        pattern['last_seen'] = datetime.now().isoformat()
        pattern['recent_outcomes'].append(outcome)
        
        if outcome == 'win':
            pattern['successes'] += 1
            pattern['total_profit'] += trade_data.get('profit', 0)
        
        # Mise à jour des métriques
        pattern['success_rate'] = pattern['successes'] / pattern['occurrences']
        pattern['avg_profit'] = pattern['total_profit'] / pattern['occurrences']
        
        self.performance_history.append({
            'pattern_key': pattern_key,
            'outcome': outcome,
            'profit': trade_data.get('profit', 0),
            'timestamp': datetime.now().isoformat()
        })
        
        # Sauvegarde périodique
        if pattern['occurrences'] % 10 == 0:
            self.save_patterns()
    
    def extract_pattern_key(self, trade_data: Dict, market_conditions: Dict) -> str:
        """Extrait une clé unique pour le pattern"""
        components = [
            trade_data.get('symbol', 'UNKNOWN'),
            trade_data.get('trade_profile', 'UNKNOWN'),
            market_conditions.get('regime', 'UNKNOWN'),
            market_conditions.get('volatility_regime', 'UNKNOWN'),
            self.quantize_value(trade_data.get('rsi_entry', 50), 10),
            self.quantize_value(trade_data.get('macd_entry', 0), 0.001),
            self.quantize_value(market_conditions.get('adx', 0), 5)
        ]
        
        return "_".join(str(c) for c in components)
    
    def quantize_value(self, value: float, step: float) -> int:
        """Quantifie une valeur pour la classification"""
        if value is None:
            return 0
        return int(round(value / step)) * step
    
    def get_pattern_confidence(self, trade_data: Dict, market_conditions: Dict) -> Dict:
        """Retourne la confiance basée sur les patterns historiques"""
        pattern_key = self.extract_pattern_key(trade_data, market_conditions)
        
        if pattern_key in self.patterns_db:
            pattern = self.patterns_db[pattern_key]
            
            return {
                'pattern_found': True,
                'success_rate': pattern['success_rate'],
                'occurrences': pattern['occurrences'],
                'avg_profit': pattern['avg_profit'],
                'confidence_score': self.calculate_confidence_score(pattern),
                'recommendation': self.get_recommendation(pattern)
            }
        else:
            return {
                'pattern_found': False,
                'confidence_score': 0.5,
                'recommendation': 'UNKNOWN'
            }
    
    def calculate_confidence_score(self, pattern: Dict) -> float:
        """Calcule un score de confiance pour le pattern"""
        base_confidence = pattern['success_rate']
        
        # Ajustement basé sur le nombre d'occurrences
        occurrence_boost = min(pattern['occurrences'] / 10, 1.0) * 0.3
        
        # Ajustement basé sur la profitabilité
        profit_boost = 0.0
        if pattern['avg_profit'] > 0:
            profit_boost = min(pattern['avg_profit'] / 5, 0.2)
        
        final_confidence = base_confidence + occurrence_boost + profit_boost
        return min(final_confidence, 1.0)
    
    def get_recommendation(self, pattern: Dict) -> str:
        """Retourne une recommandation basée sur le pattern"""
        confidence = self.calculate_confidence_score(pattern)
        
        if confidence > 0.7:
            return "STRONG_BUY" if pattern['avg_profit'] > 0 else "STRONG_SELL"
        elif confidence > 0.6:
            return "MODERATE_BUY" if pattern['avg_profit'] > 0 else "MODERATE_SELL"
        elif confidence < 0.4:
            return "AVOID"
        else:
            return "NEUTRAL"
    
    def find_similar_patterns(self, trade_data: Dict, market_conditions: Dict, 
                            max_patterns: int = 5) -> List[Dict]:
        """Trouve des patterns similaires"""
        current_key = self.extract_pattern_key(trade_data, market_conditions)
        similar_patterns = []
        
        for pattern_key, pattern in self.patterns_db.items():
            similarity = self.calculate_pattern_similarity(current_key, pattern_key)
            
            if similarity > 0.6:  # Seuil de similarité
                similar_patterns.append({
                    'pattern_key': pattern_key,
                    'similarity': similarity,
                    'success_rate': pattern['success_rate'],
                    'occurrences': pattern['occurrences'],
                    'avg_profit': pattern['avg_profit']
                })
        
        # Trie par similarité et limite le nombre
        similar_patterns.sort(key=lambda x: x['similarity'], reverse=True)
        return similar_patterns[:max_patterns]
    
    def calculate_pattern_similarity(self, key1: str, key2: str) -> float:
        """Calcule la similarité entre deux patterns"""
        components1 = key1.split('_')
        components2 = key2.split('_')
        
        if len(components1) != len(components2):
            return 0.0
        
        matches = 0
        for c1, c2 in zip(components1, components2):
            if c1 == c2:
                matches += 1
            elif c1.isdigit() and c2.isdigit():
                # Similarité numérique
                num1, num2 = float(c1), float(c2)
                if abs(num1 - num2) <= max(abs(num1), abs(num2)) * 0.2:  # 20% de tolérance
                    matches += 0.5
        
        return matches / len(components1)
    
    def analyze_market_regime_patterns(self, regime: str) -> Dict:
        """Analyse les performances par régime de marché"""
        regime_patterns = {}
        
        for pattern_key, pattern in self.patterns_db.items():
            if regime in pattern_key:
                if regime not in regime_patterns:
                    regime_patterns[regime] = {
                        'total_patterns': 0,
                        'successful_patterns': 0,
                        'total_occurrences': 0,
                        'total_profit': 0
                    }
                
                regime_data = regime_patterns[regime]
                regime_data['total_patterns'] += 1
                regime_data['total_occurrences'] += pattern['occurrences']
                regime_data['total_profit'] += pattern['total_profit']
                
                if pattern['success_rate'] > 0.6:
                    regime_data['successful_patterns'] += 1
        
        return regime_patterns
    
    def get_learning_insights(self) -> Dict:
        """Retourne des insights d'apprentissage"""
        total_patterns = len(self.patterns_db)
        
        if total_patterns == 0:
            return {}
        
        # Patterns les plus performants
        successful_patterns = [p for p in self.patterns_db.values() if p['success_rate'] > 0.7]
        problematic_patterns = [p for p in self.patterns_db.values() if p['success_rate'] < 0.3]
        
        # Analyse par symbole
        symbol_performance = defaultdict(list)
        for pattern_key, pattern in self.patterns_db.items():
            symbol = pattern_key.split('_')[0]
            symbol_performance[symbol].append(pattern['success_rate'])
        
        avg_by_symbol = {}
        for symbol, rates in symbol_performance.items():
            avg_by_symbol[symbol] = statistics.mean(rates)
        
        return {
            'total_patterns_learned': total_patterns,
            'successful_patterns_count': len(successful_patterns),
            'problematic_patterns_count': len(problematic_patterns),
            'overall_success_rate': statistics.mean([p['success_rate'] for p in self.patterns_db.values()]),
            'best_performing_symbols': dict(sorted(avg_by_symbol.items(), key=lambda x: x[1], reverse=True)[:3]),
            'worst_performing_symbols': dict(sorted(avg_by_symbol.items(), key=lambda x: x[1])[:3]),
            'learning_effectiveness': self.calculate_learning_effectiveness()
        }
    
    def calculate_learning_effectiveness(self) -> float:
        """Calcule l'efficacité globale de l'apprentissage"""
        if len(self.performance_history) < 10:
            return 0.0
        
        recent_performance = list(self.performance_history)[-20:]
        recent_wins = len([p for p in recent_performance if p['outcome'] == 'win'])
        
        if len(recent_performance) == 0:
            return 0.0
        
        recent_win_rate = recent_wins / len(recent_performance)
        
        # Comparaison avec les performances initiales
        if len(self.performance_history) >= 40:
            initial_performance = list(self.performance_history)[:20]
            initial_wins = len([p for p in initial_performance if p['outcome'] == 'win'])
            initial_win_rate = initial_wins / len(initial_performance) if initial_performance else 0
            
            improvement = recent_win_rate - initial_win_rate
            effectiveness = 0.5 + (improvement * 2)  # Base 0.5 + amélioration
        else:
            effectiveness = recent_win_rate
        
        return max(0, min(effectiveness, 1.0))
    
    def save_patterns(self):
        """Sauvegarde tous les patterns"""
        try:
            # Convertit les deque en list pour la sérialisation
            for pattern in self.patterns_db.values():
                if 'recent_outcomes' in pattern and isinstance(pattern['recent_outcomes'], deque):
                    pattern['recent_outcomes'] = list(pattern['recent_outcomes'])
            
            patterns_file = f"{self.data_dir}/patterns_db.json"
            with open(patterns_file, 'w', encoding='utf-8') as f:
                json.dump(self.patterns_db, f, indent=2, ensure_ascii=False)
            
            print(f"💾 {len(self.patterns_db)} patterns sauvegardés")
            
        except Exception as e:
            print(f"❌ Erreur sauvegarde patterns: {e}")
    
    def generate_learning_report(self) -> Dict:
        """Génère un rapport complet d'apprentissage"""
        insights = self.get_learning_insights()
        
        return {
            'learning_metrics': insights,
            'total_trades_analyzed': len(self.performance_history),
            'pattern_database_size': len(self.patterns_db),
            'learning_effectiveness': insights.get('learning_effectiveness', 0),
            'timestamp': datetime.now().isoformat(),
            'recommendations': self.generate_recommendations()
        }
    
    def generate_recommendations(self) -> List[str]:
        """Génère des recommandations basées sur l'apprentissage"""
        recommendations = []
        
        insights = self.get_learning_insights()
        
        # Recommandation basée sur les symboles performants
        best_symbols = insights.get('best_performing_symbols', {})
        if best_symbols:
            best_symbol = list(best_symbols.keys())[0]
            recommendations.append(f"Privilégier le trading sur {best_symbol} (performance: {best_symbols[best_symbol]:.1%})")
        
        # Recommandation basée sur les patterns problématiques
        problematic_count = insights.get('problematic_patterns_count', 0)
        if problematic_count > 10:
            recommendations.append(f"Revoir {problematic_count} patterns problématiques identifiés")
        
        # Recommandation générale
        overall_success = insights.get('overall_success_rate', 0)
        if overall_success < 0.5:
            recommendations.append("Envisager une réduction globale du risk")
        elif overall_success > 0.6:
            recommendations.append("Performance bonne - maintenir la stratégie actuelle")
        
        return recommendations