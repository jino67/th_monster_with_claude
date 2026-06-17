import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import json
from datetime import datetime

class StrategyOptimizer:
    def __init__(self, config_path: str = "config/config_symbols_v2.json"):
        self.config = self.load_config(config_path)
        self.optimization_history = []
        
    def load_config(self, config_path: str) -> Dict:
        """Charge la configuration"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def optimize_parameters(self, symbol: str, historical_data: Dict, 
                          performance_data: List[Dict]) -> Dict:
        """Optimise les paramètres pour un symbole"""
        print(f"🔧 Optimisation des paramètres pour {symbol}...")
        
        # Analyse des performances historiques
        performance_analysis = self.analyze_performance(performance_data)
        
        # Analyse des conditions de marché
        market_analysis = self.analyze_market_conditions(historical_data)
        
        # Optimisation des paramètres
        optimized_params = self.calculate_optimized_parameters(
            symbol, performance_analysis, market_analysis
        )
        
        # Validation des paramètres
        validated_params = self.validate_parameters(optimized_params, symbol)
        
        # Enregistrement de l'optimisation
        self.record_optimization(symbol, validated_params, performance_analysis)
        
        return validated_params
    
    def analyze_performance(self, performance_data: List[Dict]) -> Dict:
        """Analyse les performances historiques"""
        if not performance_data:
            return {}
        
        df = pd.DataFrame(performance_data)
        
        # Métriques de base
        total_trades = len(df)
        winning_trades = len(df[df['outcome'] == 'win'])
        losing_trades = len(df[df['outcome'] == 'loss'])
        
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        avg_profit = df['profit'].mean() if 'profit' in df.columns else 0
        avg_pips = df['pips'].mean() if 'pips' in df.columns else 0
        
        # Analyse par profil
        profile_performance = {}
        if 'profile' in df.columns:
            for profile in df['profile'].unique():
                profile_data = df[df['profile'] == profile]
                profile_win_rate = len(profile_data[profile_data['outcome'] == 'win']) / len(profile_data)
                profile_performance[profile] = {
                    'win_rate': profile_win_rate,
                    'avg_profit': profile_data['profit'].mean(),
                    'trade_count': len(profile_data)
                }
        
        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'avg_pips': avg_pips,
            'profile_performance': profile_performance,
            'recent_trend': self.analyze_recent_trend(performance_data)
        }
    
    def analyze_recent_trend(self, performance_data: List[Dict]) -> str:
        """Analyse la tendance récente des performances"""
        if len(performance_data) < 5:
            return "NEUTRAL"
        
        recent_data = performance_data[-5:]
        recent_wins = len([t for t in recent_data if t['outcome'] == 'win'])
        recent_win_rate = recent_wins / len(recent_data)
        
        if recent_win_rate > 0.7:
            return "IMPROVING"
        elif recent_win_rate < 0.3:
            return "DETERIORATING"
        else:
            return "STABLE"
    
    def analyze_market_conditions(self, historical_data: Dict) -> Dict:
        """Analyse les conditions de marché historiques"""
        # Implémentation simplifiée
        return {
            'volatility_regime': 'NORMAL',
            'trend_regime': 'MIXED',
            'market_phase': 'UNKNOWN'
        }
    
    def calculate_optimized_parameters(self, symbol: str, performance: Dict, 
                                    market_conditions: Dict) -> Dict:
        """Calcule les paramètres optimisés"""
        base_config = self.config.get(symbol, {})
        optimized = {}
        
        for profile in ['SCALPING', 'SWING', 'TREND_FOLLOW']:
            if profile in base_config:
                profile_config = base_config[profile].copy()
                
                # Ajustements basés sur la performance
                profile_perf = performance.get('profile_performance', {}).get(profile, {})
                profile_win_rate = profile_perf.get('win_rate', 0.5)
                
                # Optimisation du RR ratio
                if profile_win_rate > 0.6:
                    profile_config['RR'] *= 1.1
                elif profile_win_rate < 0.4:
                    profile_config['RR'] *= 0.9
                
                # Optimisation du SL
                if performance.get('recent_trend') == 'DETERIORATING':
                    profile_config['SL_ATR_MULTIPLE'] *= 1.2
                elif performance.get('recent_trend') == 'IMPROVING':
                    profile_config['SL_ATR_MULTIPLE'] *= 0.9
                
                optimized[profile] = profile_config
        
        return optimized
    
    def validate_parameters(self, params: Dict, symbol: str) -> Dict:
        """Valide les paramètres optimisés"""
        validated = params.copy()
        
        for profile, config in validated.items():
            # Contraintes sur le RR ratio
            config['RR'] = max(1.1, min(config['RR'], 5.0))
            
            # Contraintes sur le SL
            config['SL_ATR_MULTIPLE'] = max(0.5, min(config['SL_ATR_MULTIPLE'], 3.0))
            
            # Contraintes sur le risk
            config['RISK_PERCENT'] = max(0.005, min(config['RISK_PERCENT'], 0.1))
        
        return validated
    
    def record_optimization(self, symbol: str, params: Dict, performance: Dict):
        """Enregistre l'optimisation"""
        record = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'optimized_parameters': params,
            'performance_metrics': performance,
            'optimization_version': 'v2'
        }
        
        self.optimization_history.append(record)
        
        # Garde seulement les 100 dernières optimisations
        self.optimization_history = self.optimization_history[-100:]