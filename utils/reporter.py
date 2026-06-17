import pandas as pd
import time
import datetime
from typing import Dict, List, Optional
import json
import os

class AdvancedReporter:
    def __init__(self, data_dir: str = "MonsterMind_int/reports"):
        self.data_dir = data_dir
        self.capital_history = []
        self.performance_metrics = {}
        self.trade_analytics = []
        self.system_health = {}
        
        self._ensure_directory()
    
    def _ensure_directory(self):
        """Crée le répertoire de rapports"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def log_capital_v2(self, balance: float, equity: float, free_margin: float, 
                      additional_metrics: Dict = None):
        """Log les métriques de capital version V2"""
        log_entry = {
            'timestamp': datetime.datetime.now().isoformat(),
            'balance': balance,
            'equity': equity,
            'free_margin': free_margin,
            'margin_used': balance - free_margin,
            'equity_balance_ratio': equity / balance if balance > 0 else 0
        }
        
        if additional_metrics:
            log_entry.update(additional_metrics)
        
        self.capital_history.append(log_entry)
        
        # Sauvegarde périodique
        if len(self.capital_history) % 50 == 0:
            self.save_capital_history()
    
    def log_trade_analytics(self, trade_data: Dict):
        """Log les analytics détaillés d'un trade"""
        analytics_entry = {
            'timestamp': datetime.datetime.now().isoformat(),
            'symbol': trade_data.get('symbol'),
            'direction': trade_data.get('direction'),
            'volume': trade_data.get('volume'),
            'entry_price': trade_data.get('entry_price'),
            'exit_price': trade_data.get('exit_price'),
            'profit': trade_data.get('profit'),
            'pips': trade_data.get('pips'),
            'duration_minutes': trade_data.get('duration_minutes'),
            'risk_reward_ratio': trade_data.get('risk_reward_ratio'),
            'market_regime': trade_data.get('market_regime'),
            'volatility_regime': trade_data.get('volatility_regime'),
            'entry_conditions': trade_data.get('entry_conditions', {}),
            'exit_reason': trade_data.get('exit_reason')
        }
        
        self.trade_analytics.append(analytics_entry)
        
        # Sauvegarde périodique
        if len(self.trade_analytics) % 20 == 0:
            self.save_trade_analytics()
    
    def update_performance_metrics(self, metrics: Dict):
        """Met à jour les métriques de performance"""
        self.performance_metrics.update(metrics)
        self.performance_metrics['last_update'] = datetime.datetime.now().isoformat()
    
    def log_system_health(self, health_data: Dict):
        """Log la santé du système"""
        self.system_health = {
            'timestamp': datetime.datetime.now().isoformat(),
            'mt5_connected': health_data.get('mt5_connected', False),
            'data_quality': health_data.get('data_quality', {}),
            'active_positions': health_data.get('active_positions', 0),
            'memory_usage': health_data.get('memory_usage', 0),
            'cpu_usage': health_data.get('cpu_usage', 0),
            'error_count': health_data.get('error_count', 0),
            'warning_count': health_data.get('warning_count', 0)
        }
    
    def generate_daily_report(self) -> Dict:
        """Génère un rapport quotidien complet"""
        report = {
            'date': datetime.datetime.now().strftime('%Y-%m-%d'),
            'timestamp': datetime.datetime.now().isoformat(),
            'capital_metrics': self.get_capital_metrics(),
            'trading_metrics': self.get_trading_metrics(),
            'system_health': self.system_health,
            'recommendations': self.generate_recommendations(),
            'market_analysis': self.get_market_analysis()
        }
        
        # Sauvegarde du rapport
        self.save_daily_report(report)
        
        return report
    
    def get_capital_metrics(self) -> Dict:
        """Calcule les métriques de capital"""
        if not self.capital_history:
            return {}
        
        df = pd.DataFrame(self.capital_history)
        
        return {
            'current_balance': df['balance'].iloc[-1] if len(df) > 0 else 0,
            'current_equity': df['equity'].iloc[-1] if len(df) > 0 else 0,
            'max_drawdown': self.calculate_drawdown(df),
            'profit_loss_today': self.calculate_daily_pnl(df),
            'sharpe_ratio': self.calculate_sharpe_ratio(df),
            'volatility': df['equity'].pct_change().std() if len(df) > 1 else 0
        }
    
    def get_trading_metrics(self) -> Dict:
        """Calcule les métriques de trading"""
        if not self.trade_analytics:
            return {}
        
        df = pd.DataFrame(self.trade_analytics)
        
        return {
            'total_trades': len(df),
            'winning_trades': len(df[df['profit'] > 0]),
            'losing_trades': len(df[df['profit'] < 0]),
            'win_rate': len(df[df['profit'] > 0]) / len(df) if len(df) > 0 else 0,
            'avg_profit': df['profit'].mean(),
            'total_profit': df['profit'].sum(),
            'profit_factor': self.calculate_profit_factor(df),
            'avg_trade_duration': df['duration_minutes'].mean(),
            'best_trade': df['profit'].max(),
            'worst_trade': df['profit'].min()
        }
    
    def calculate_drawdown(self, df: pd.DataFrame) -> float:
        """Calcule le drawdown maximum"""
        if len(df) == 0:
            return 0.0
        
        equity = df['equity'].values
        peak = equity[0]
        max_drawdown = 0.0
        
        for value in equity:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return max_drawdown
    
    def calculate_daily_pnl(self, df: pd.DataFrame) -> float:
        """Calcule le P&L du jour"""
        if len(df) == 0:
            return 0.0
        
        today = datetime.datetime.now().date()
        today_data = [entry for entry in self.capital_history 
                     if datetime.datetime.fromisoformat(entry['timestamp']).date() == today]
        
        if len(today_data) < 2:
            return 0.0
        
        return today_data[-1]['equity'] - today_data[0]['equity']
    
    def calculate_sharpe_ratio(self, df: pd.DataFrame) -> float:
        """Calcule le ratio de Sharpe simplifié"""
        if len(df) < 2:
            return 0.0
        
        returns = df['equity'].pct_change().dropna()
        if returns.std() == 0:
            return 0.0
        
        return returns.mean() / returns.std()
    
    def calculate_profit_factor(self, df: pd.DataFrame) -> float:
        """Calcule le profit factor"""
        winning_trades = df[df['profit'] > 0]
        losing_trades = df[df['profit'] < 0]
        
        gross_profit = winning_trades['profit'].sum()
        gross_loss = abs(losing_trades['profit'].sum())
        
        return gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    def get_market_analysis(self) -> Dict:
        """Analyse les conditions de marché"""
        # À implémenter avec les données de marché
        return {
            'overall_sentiment': 'NEUTRAL',
            'volatility_regime': 'NORMAL',
            'trend_strength': 'MODERATE',
            'market_phase': 'REGULAR'
        }
    
    def generate_recommendations(self) -> List[str]:
        """Génère des recommandations basées sur les données"""
        recommendations = []
        
        capital_metrics = self.get_capital_metrics()
        trading_metrics = self.get_trading_metrics()
        
        # Recommandation drawdown
        if capital_metrics.get('max_drawdown', 0) > 10:
            recommendations.append("Drawdown élevé - réduire l'exposition au risk")
        
        # Recommandation win rate
        win_rate = trading_metrics.get('win_rate', 0)
        if win_rate < 0.4:
            recommendations.append("Win rate faible - revoir la stratégie d'entrée")
        
        # Recommandation profit factor
        profit_factor = trading_metrics.get('profit_factor', 0)
        if profit_factor < 1.0:
            recommendations.append("Profit factor < 1 - optimiser la gestion des sorties")
        
        return recommendations
    
    def save_capital_history(self):
        """Sauvegarde l'historique du capital"""
        try:
            file_path = os.path.join(self.data_dir, "capital_history.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.capital_history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Erreur sauvegarde historique capital: {e}")
    
    def save_trade_analytics(self):
        """Sauvegarde les analytics de trades"""
        try:
            file_path = os.path.join(self.data_dir, "trade_analytics.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.trade_analytics, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Erreur sauvegarde analytics trades: {e}")
    
    def save_daily_report(self, report: Dict):
        """Sauvegarde le rapport quotidien"""
        try:
            date_str = datetime.datetime.now().strftime('%Y%m%d')
            file_path = os.path.join(self.data_dir, f"daily_report_{date_str}.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Erreur sauvegarde rapport quotidien: {e}")

# Variables globales pour la compatibilité
capital_history = []
bars_count = 0
trades_count = 0

def log_capital(balance, equity, free_margin):
    """Fonction legacy pour la compatibilité"""
    global capital_history
    capital_history.append([datetime.datetime.utcnow(), balance, equity, free_margin])
    
    # Sauvegarde simplifiée
    df = pd.DataFrame(capital_history, columns=["time", "balance", "equity", "free_margin"])
    df.to_csv("capital_history_legacy.csv", index=False)