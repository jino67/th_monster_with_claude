import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import json
from datetime import datetime, timedelta
import statistics
import matplotlib.pyplot as plt
import seaborn as sns

class PerformanceAnalyzer:
    def __init__(self, data_dir: str = "MonsterMind_int/performance"):
        self.data_dir = data_dir
        self.trade_history = []
        self.performance_metrics = {}
        self.equity_curve = []
        
        self._ensure_directory()
        self.load_trade_history()
    
    def _ensure_directory(self):
        """Crée le répertoire de performance"""
        import os
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def load_trade_history(self):
        """Charge l'historique des trades"""
        try:
            history_file = f"{self.data_dir}/trade_history.json"
            if os.path.exists(history_file):
                with open(history_file, 'r') as f:
                    self.trade_history = json.load(f)
                print(f"✅ {len(self.trade_history)} trades chargés")
        except Exception as e:
            print(f"❌ Erreur chargement historique: {e}")
    
    def add_trade(self, trade_data: Dict):
        """Ajoute un trade à l'historique"""
        self.trade_history.append(trade_data)
        
        # Sauvegarde périodique
        if len(self.trade_history) % 10 == 0:
            self.save_trade_history()
            self.update_performance_metrics()
    
    def update_performance_metrics(self):
        """Met à jour toutes les métriques de performance"""
        if not self.trade_history:
            return
        
        df = pd.DataFrame(self.trade_history)
        
        # Métriques de base
        self.performance_metrics['basic'] = self.calculate_basic_metrics(df)
        
        # Métriques avancées
        self.performance_metrics['advanced'] = self.calculate_advanced_metrics(df)
        
        # Analyse par symbole
        self.performance_metrics['by_symbol'] = self.analyze_by_symbol(df)
        
        # Analyse par timeframe
        self.performance_metrics['by_timeframe'] = self.analyze_by_timeframe(df)
        
        # Courbe de equity
        self.update_equity_curve(df)
    
    def calculate_basic_metrics(self, df: pd.DataFrame) -> Dict:
        """Calcule les métriques de base"""
        total_trades = len(df)
        winning_trades = len(df[df['outcome'] == 'win'])
        losing_trades = len(df[df['outcome'] == 'loss'])
        
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        total_profit = df['profit'].sum()
        avg_profit = df['profit'].mean()
        avg_win = df[df['outcome'] == 'win']['profit'].mean() if winning_trades > 0 else 0
        avg_loss = df[df['outcome'] == 'loss']['profit'].mean() if losing_trades > 0 else 0
        
        profit_factor = abs(avg_win * winning_trades) / abs(avg_loss * losing_trades) if losing_trades > 0 else float('inf')
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_profit': total_profit,
            'avg_profit': avg_profit,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor
        }
    
    def calculate_advanced_metrics(self, df: pd.DataFrame) -> Dict:
        """Calcule les métriques avancées"""
        # Drawdown
        equity_curve = self.calculate_equity_curve(df)
        drawdown = self.calculate_drawdown(equity_curve)
        
        # Sharpe Ratio (simplifié)
        returns = df['profit'].pct_change().dropna()
        sharpe_ratio = returns.mean() / returns.std() if returns.std() > 0 else 0
        
        # Recovery Factor
        recovery_factor = self.calculate_recovery_factor(df)
        
        # Expectancy
        expectancy = self.calculate_expectancy(df)
        
        # Consistance
        consistency = self.calculate_consistency(df)
        
        return {
            'max_drawdown': drawdown['max_drawdown'],
            'max_drawdown_percent': drawdown['max_drawdown_percent'],
            'sharpe_ratio': sharpe_ratio,
            'recovery_factor': recovery_factor,
            'expectancy': expectancy,
            'consistency_score': consistency,
            'avg_trade_duration': df['duration_minutes'].mean() if 'duration_minutes' in df.columns else 0
        }
    
    def calculate_equity_curve(self, df: pd.DataFrame) -> List[float]:
        """Calcule la courbe de equity"""
        equity = 0
        curve = []
        
        for _, trade in df.iterrows():
            equity += trade['profit']
            curve.append(equity)
        
        return curve
    
    def calculate_drawdown(self, equity_curve: List[float]) -> Dict:
        """Calcule le drawdown"""
        if not equity_curve:
            return {'max_drawdown': 0, 'max_drawdown_percent': 0}
        
        peak = equity_curve[0]
        max_drawdown = 0
        max_drawdown_percent = 0
        
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            
            drawdown = peak - equity
            drawdown_percent = (drawdown / peak) * 100 if peak > 0 else 0
            
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_drawdown_percent = drawdown_percent
        
        return {
            'max_drawdown': max_drawdown,
            'max_drawdown_percent': max_drawdown_percent
        }
    
    def calculate_recovery_factor(self, df: pd.DataFrame) -> float:
        """Calcule le recovery factor"""
        if not self.performance_metrics.get('advanced', {}).get('max_drawdown', 0):
            return 0
        
        total_profit = self.performance_metrics['basic']['total_profit']
        max_drawdown = self.performance_metrics['advanced']['max_drawdown']
        
        return total_profit / max_drawdown if max_drawdown > 0 else float('inf')
    
    def calculate_expectancy(self, df: pd.DataFrame) -> float:
        """Calcule l'expectancy"""
        basic = self.performance_metrics['basic']
        
        win_rate = basic['win_rate']
        avg_win = basic['avg_win']
        avg_loss = basic['avg_loss']
        
        return (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))
    
    def calculate_consistency(self, df: pd.DataFrame) -> float:
        """Calcule le score de consistance"""
        if len(df) < 5:
            return 0.0
        
        # Regroupe les trades par lots de 5
        chunks = [df[i:i+5] for i in range(0, len(df), 5)]
        win_rates = []
        
        for chunk in chunks:
            if len(chunk) >= 3:  # Au moins 3 trades dans le chunk
                win_rate = len(chunk[chunk['outcome'] == 'win']) / len(chunk)
                win_rates.append(win_rate)
        
        if not win_rates:
            return 0.0
        
        # La consistance est l'inverse de l'écart-type
        std_dev = statistics.stdev(win_rates)
        consistency = 1 - min(std_dev, 1.0)  # Normalisé 0-1
        
        return consistency
    
    def analyze_by_symbol(self, df: pd.DataFrame) -> Dict:
        """Analyse la performance par symbole"""
        symbol_metrics = {}
        
        for symbol in df['symbol'].unique():
            symbol_data = df[df['symbol'] == symbol]
            
            symbol_metrics[symbol] = {
                'total_trades': len(symbol_data),
                'win_rate': len(symbol_data[symbol_data['outcome'] == 'win']) / len(symbol_data),
                'total_profit': symbol_data['profit'].sum(),
                'avg_profit': symbol_data['profit'].mean(),
                'profit_factor': self.calculate_profit_factor(symbol_data)
            }
        
        return symbol_metrics
    
    def analyze_by_timeframe(self, df: pd.DataFrame) -> Dict:
        """Analyse la performance par timeframe"""
        timeframe_metrics = {}
        
        if 'timeframe' not in df.columns:
            return {}
        
        for timeframe in df['timeframe'].unique():
            tf_data = df[df['timeframe'] == timeframe]
            
            timeframe_metrics[timeframe] = {
                'total_trades': len(tf_data),
                'win_rate': len(tf_data[tf_data['outcome'] == 'win']) / len(tf_data),
                'total_profit': tf_data['profit'].sum(),
                'avg_trade_duration': tf_data['duration_minutes'].mean() if 'duration_minutes' in tf_data.columns else 0
            }
        
        return timeframe_metrics
    
    def calculate_profit_factor(self, df: pd.DataFrame) -> float:
        """Calcule le profit factor"""
        winning_trades = df[df['outcome'] == 'win']
        losing_trades = df[df['outcome'] == 'loss']
        
        gross_profit = winning_trades['profit'].sum()
        gross_loss = abs(losing_trades['profit'].sum())
        
        return gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    def update_equity_curve(self, df: pd.DataFrame):
        """Met à jour la courbe de equity"""
        self.equity_curve = self.calculate_equity_curve(df)
    
    def generate_performance_report(self) -> Dict:
        """Génère un rapport de performance complet"""
        self.update_performance_metrics()
        
        return {
            'summary': self.performance_metrics['basic'],
            'advanced_metrics': self.performance_metrics['advanced'],
            'symbol_analysis': self.performance_metrics['by_symbol'],
            'timeframe_analysis': self.performance_metrics['by_timeframe'],
            'timestamp': datetime.now().isoformat(),
            'recommendations': self.generate_performance_recommendations()
        }
    
    def generate_performance_recommendations(self) -> List[str]:
        """Génère des recommandations basées sur la performance"""
        recommendations = []
        basic = self.performance_metrics['basic']
        advanced = self.performance_metrics['advanced']
        
        # Recommandation win rate
        win_rate = basic['win_rate']
        if win_rate < 0.4:
            recommendations.append("Win rate faible - revoir la stratégie d'entrée")
        elif win_rate > 0.6:
            recommendations.append("Win rate excellent - maintenir la stratégie")
        
        # Recommandation profit factor
        profit_factor = basic['profit_factor']
        if profit_factor < 1.0:
            recommendations.append("Profit factor < 1 - optimiser la gestion des sorties")
        
        # Recommandation drawdown
        max_drawdown = advanced['max_drawdown_percent']
        if max_drawdown > 10:
            recommendations.append(f"Drawdown élevé ({max_drawdown:.1f}%) - réduire le risk")
        
        # Recommandation consistance
        consistency = advanced['consistency_score']
        if consistency < 0.7:
            recommendations.append("Faible consistance - uniformiser les performances")
        
        return recommendations
    
    def save_trade_history(self):
        """Sauvegarde l'historique des trades"""
        try:
            history_file = f"{self.data_dir}/trade_history.json"
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(self.trade_history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Erreur sauvegarde historique: {e}")
    
    def plot_equity_curve(self, save_path: Optional[str] = None):
        """Génère un graphique de la courbe de equity"""
        if not self.equity_curve:
            return
        
        plt.figure(figsize=(12, 6))
        plt.plot(self.equity_curve, linewidth=2)
        plt.title('Courbe de Equity')
        plt.xlabel('Nombre de Trades')
        plt.ylabel('Equity')
        plt.grid(True, alpha=0.3)
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        plt.show()
    
    def plot_performance_by_symbol(self, save_path: Optional[str] = None):
        """Génère un graphique des performances par symbole"""
        if not self.performance_metrics.get('by_symbol'):
            return
        
        symbols = list(self.performance_metrics['by_symbol'].keys())
        win_rates = [self.performance_metrics['by_symbol'][s]['win_rate'] for s in symbols]
        profits = [self.performance_metrics['by_symbol'][s]['total_profit'] for s in symbols]
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        # Graphique win rate
        ax1.bar(symbols, win_rates, color='skyblue')
        ax1.set_title('Win Rate par Symbole')
        ax1.set_ylabel('Win Rate')
        ax1.tick_params(axis='x', rotation=45)
        
        # Graphique profits
        colors = ['green' if p >= 0 else 'red' for p in profits]
        ax2.bar(symbols, profits, color=colors)
        ax2.set_title('Profit Total par Symbole')
        ax2.set_ylabel('Profit')
        ax2.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        plt.show()