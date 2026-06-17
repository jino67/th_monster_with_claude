import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import json
from datetime import datetime, timedelta
from scipy.stats import pearsonr, spearmanr
import warnings
warnings.filterwarnings('ignore')

class CorrelationAnalyzer:
    def __init__(self, data_dir: str = "MonsterMind_int/correlations"):
        self.data_dir = data_dir
        self.correlation_data = {}
        self.symbol_pairs = []
        
        self._ensure_directory()
        self.load_correlation_data()
    
    def _ensure_directory(self):
        """Crée le répertoire de corrélations"""
        import os
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def load_correlation_data(self):
        """Charge les données de corrélation"""
        try:
            data_file = f"{self.data_dir}/correlation_data.json"
            if os.path.exists(data_file):
                with open(data_file, 'r') as f:
                    self.correlation_data = json.load(f)
                print("✅ Données de corrélation chargées")
        except Exception as e:
            print(f"❌ Erreur chargement corrélations: {e}")
    
    def analyze_symbol_correlations(self, symbols: List[str], 
                                  price_data: Dict[str, pd.DataFrame],
                                  lookback_days: int = 30) -> Dict:
        """Analyse les corrélations entre symboles"""
        correlations = {}
        
        for i, sym1 in enumerate(symbols):
            for sym2 in symbols[i+1:]:
                if sym1 in price_data and sym2 in price_data:
                    correlation = self.calculate_pair_correlation(
                        sym1, sym2, price_data[sym1], price_data[sym2], lookback_days
                    )
                    pair_key = f"{sym1}_{sym2}"
                    correlations[pair_key] = correlation
        
        # Mise à jour des données
        self.update_correlation_database(correlations)
        
        return correlations
    
    def calculate_pair_correlation(self, sym1: str, sym2: str,
                                 df1: pd.DataFrame, df2: pd.DataFrame,
                                 lookback_days: int) -> Dict:
        """Calcule la corrélation entre une paire de symboles"""
        # Alignement des données
        merged_df = self.align_price_data(df1, df2, lookback_days)
        
        if merged_df is None or len(merged_df) < 10:
            return {'correlation': 0, 'confidence': 0, 'data_points': 0}
        
        # Calcul des returns
        returns1 = merged_df[f'{sym1}_close'].pct_change().dropna()
        returns2 = merged_df[f'{sym2}_close'].pct_change().dropna()
        
        # Corrélation Pearson
        pearson_corr, pearson_p = pearsonr(returns1, returns2)
        
        # Corrélation Spearman (non-linéaire)
        spearman_corr, spearman_p = spearmanr(returns1, returns2)
        
        # Confidence basée sur la p-value et le nombre de points
        confidence = self.calculate_correlation_confidence(
            min(pearson_p, spearman_p), len(returns1)
        )
        
        return {
            'pearson_correlation': pearson_corr,
            'spearman_correlation': spearman_corr,
            'confidence': confidence,
            'data_points': len(returns1),
            'last_updated': datetime.now().isoformat(),
            'trend': self.analyze_correlation_trend(sym1, sym2, pearson_corr)
        }
    
    def align_price_data(self, df1: pd.DataFrame, df2: pd.DataFrame,
                        lookback_days: int) -> Optional[pd.DataFrame]:
        """Aligne les données de prix de deux symboles"""
        try:
            # Assure que les DataFrames ont les colonnes nécessaires
            if 'close' not in df1.columns or 'close' not in df2.columns:
                return None
            
            # Renomme les colonnes
            df1_aligned = df1[['close']].copy()
            df2_aligned = df2[['close']].copy()
            
            df1_aligned.columns = [f'{df1_aligned.columns[0]}_close']
            df2_aligned.columns = [f'{df2_aligned.columns[0]}_close']
            
            # Fusion sur l'index (timestamp)
            merged_df = pd.merge(df1_aligned, df2_aligned, 
                               left_index=True, right_index=True, how='inner')
            
            # Limite au lookback
            if lookback_days > 0:
                cutoff_date = datetime.now() - timedelta(days=lookback_days)
                merged_df = merged_df[merged_df.index >= cutoff_date]
            
            return merged_df.dropna()
            
        except Exception as e:
            print(f"❌ Erreur alignement données {e}")
            return None
    
    def calculate_correlation_confidence(self, p_value: float, data_points: int) -> float:
        """Calcule la confiance de la corrélation"""
        # Confiance basée sur la p-value
        p_confidence = 1 - min(p_value * 10, 1.0)  # p < 0.1 → confiance élevée
        
        # Confiance basée sur le nombre de points
        points_confidence = min(data_points / 50, 1.0)  # 50 points = confiance max
        
        return (p_confidence + points_confidence) / 2
    
    def analyze_correlation_trend(self, sym1: str, sym2: str, 
                                current_correlation: float) -> str:
        """Analyse la tendance de la corrélation"""
        pair_key = f"{sym1}_{sym2}"
        
        if pair_key in self.correlation_data:
            historical_corrs = [
                data['pearson_correlation'] 
                for data in self.correlation_data[pair_key][-5:]  # 5 dernières mesures
                if 'pearson_correlation' in data
            ]
            
            if len(historical_corrs) >= 3:
                avg_historical = sum(historical_corrs) / len(historical_corrs)
                
                if current_correlation > avg_historical + 0.1:
                    return "INCREASING"
                elif current_correlation < avg_historical - 0.1:
                    return "DECREASING"
        
        return "STABLE"
    
    def update_correlation_database(self, new_correlations: Dict):
        """Met à jour la base de données de corrélation"""
        for pair_key, correlation_data in new_correlations.items():
            if pair_key not in self.correlation_data:
                self.correlation_data[pair_key] = []
            
            self.correlation_data[pair_key].append(correlation_data)
            
            # Garde seulement les 100 dernières entrées
            self.correlation_data[pair_key] = self.correlation_data[pair_key][-100:]
        
        # Sauvegarde périodique
        self.save_correlation_data()
    
    def identify_hedging_opportunities(self, symbols: List[str],
                                     correlation_threshold: float = 0.7) -> List[Dict]:
        """Identifie les opportunités de hedging"""
        hedging_pairs = []
        
        for pair_key, correlation_history in self.correlation_data.items():
            if not correlation_history:
                continue
            
            latest_corr = correlation_history[-1]
            current_corr = latest_corr.get('pearson_correlation', 0)
            confidence = latest_corr.get('confidence', 0)
            
            # Paires fortement corrélées (potentiel hedging)
            if abs(current_corr) > correlation_threshold and confidence > 0.7:
                sym1, sym2 = pair_key.split('_')
                
                hedging_pairs.append({
                    'pair': pair_key,
                    'symbol1': sym1,
                    'symbol2': sym2,
                    'correlation': current_corr,
                    'confidence': confidence,
                    'trend': latest_corr.get('trend', 'UNKNOWN'),
                    'hedging_potential': self.calculate_hedging_potential(current_corr)
                })
        
        return sorted(hedging_pairs, key=lambda x: abs(x['correlation']), reverse=True)
    
    def calculate_hedging_potential(self, correlation: float) -> float:
        """Calcule le potentiel de hedging"""
        # Potentiel maximum pour corrélation ≈ 1 ou -1
        return min(abs(correlation) * 1.2, 1.0)
    
    def analyze_market_regime_correlations(self, symbols: List[str],
                                         regime_data: Dict) -> Dict:
        """Analyse les corrélations par régime de marché"""
        regime_correlations = {}
        
        for regime in regime_data.get('regimes', []):
            # Filtre les données par régime
            regime_symbols = self.get_symbols_by_regime(symbols, regime, regime_data)
            
            if len(regime_symbols) >= 2:
                # Analyse des corrélations pour ce régime
                regime_correlations[regime] = self.analyze_symbol_correlations(
                    regime_symbols, self.get_price_data_for_regime(regime)
                )
        
        return regime_correlations
    
    def get_symbols_by_regime(self, symbols: List[str], regime: str,
                            regime_data: Dict) -> List[str]:
        """Filtre les symboles par régime"""
        # Implémentation simplifiée
        return symbols  # À adapter selon la structure des données de régime
    
    def get_price_data_for_regime(self, regime: str) -> Dict:
        """Récupère les données de prix pour un régime"""
        # Implémentation à compléter selon la source de données
        return {}
    
    def generate_correlation_report(self, symbols: List[str]) -> Dict:
        """Génère un rapport de corrélation complet"""
        # Analyse actuelle
        current_correlations = self.analyze_symbol_correlations(symbols, self.get_current_price_data())
        
        # Opportunités de hedging
        hedging_opportunities = self.identify_hedging_opportunities(symbols)
        
        # Tendances
        correlation_trends = self.analyze_correlation_trends(symbols)
        
        return {
            'current_correlations': current_correlations,
            'hedging_opportunities': hedging_opportunities,
            'correlation_trends': correlation_trends,
            'summary_metrics': self.calculate_summary_metrics(current_correlations),
            'timestamp': datetime.now().isoformat(),
            'recommendations': self.generate_correlation_recommendations(hedging_opportunities)
        }
    
    def get_current_price_data(self) -> Dict:
        """Récupère les données de prix actuelles"""
        # À implémenter selon la source de données
        return {}
    
    def analyze_correlation_trends(self, symbols: List[str]) -> Dict:
        """Analyse les tendances des corrélations"""
        trends = {}
        
        for pair_key in self.correlation_data:
            if len(self.correlation_data[pair_key]) >= 5:
                recent_corrs = [c['pearson_correlation'] for c in self.correlation_data[pair_key][-5:]]
                trend = self.calculate_trend_direction(recent_corrs)
                trends[pair_key] = trend
        
        return trends
    
    def calculate_trend_direction(self, values: List[float]) -> str:
        """Calcule la direction de la tendance"""
        if len(values) < 2:
            return "UNKNOWN"
        
        # Régression linéaire simple
        x = np.arange(len(values))
        slope = np.polyfit(x, values, 1)[0]
        
        if slope > 0.01:
            return "INCREASING"
        elif slope < -0.01:
            return "DECREASING"
        else:
            return "STABLE"
    
    def calculate_summary_metrics(self, correlations: Dict) -> Dict:
        """Calcule des métriques récapitulatives"""
        if not correlations:
            return {}
        
        all_correlations = [c['pearson_correlation'] for c in correlations.values()]
        
        return {
            'average_correlation': statistics.mean(all_correlations),
            'correlation_std': statistics.stdev(all_correlations) if len(all_correlations) > 1 else 0,
            'high_correlation_pairs': len([c for c in all_correlations if abs(c) > 0.7]),
            'low_correlation_pairs': len([c for c in all_correlations if abs(c) < 0.3]),
            'most_correlated_pair': max(correlations.items(), key=lambda x: abs(x[1]['pearson_correlation']))[0] if correlations else "N/A"
        }
    
    def generate_correlation_recommendations(self, hedging_opportunities: List[Dict]) -> List[str]:
        """Génère des recommandations basées sur les corrélations"""
        recommendations = []
        
        # Recommandations de hedging
        strong_hedging = [h for h in hedging_opportunities if h['hedging_potential'] > 0.8]
        if strong_hedging:
            best_hedge = strong_hedging[0]
            recommendations.append(
                f"Hedging fort: {best_hedge['symbol1']} vs {best_hedge['symbol2']} "
                f"(corrélation: {best_hedge['correlation']:.2f})"
            )
        
        # Recommandation diversification
        if len(hedging_opportunities) < 3:
            recommendations.append("Opportunités de hedging limitées - diversifier le portefeuille")
        
        return recommendations
    
    def save_correlation_data(self):
        """Sauvegarde les données de corrélation"""
        try:
            data_file = f"{self.data_dir}/correlation_data.json"
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(self.correlation_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Erreur sauvegarde corrélations: {e}")