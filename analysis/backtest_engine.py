import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import json
from datetime import datetime, timedelta
import MetaTrader5 as mt5

class BacktestEngine:
    def __init__(self, initial_balance: float = 10000):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.positions = []
        self.trade_history = []
        self.performance_metrics = {}
        
    def run_backtest(self, symbol: str, df: pd.DataFrame, strategy_config: Dict) -> Dict:
        """Exécute un backtest complet pour un symbole"""
        print(f"🔍 Backtest en cours pour {symbol}...")
        
        # Préparation des données
        prepared_data = self.prepare_data(df, strategy_config)
        
        # Exécution de la stratégie
        for i in range(len(prepared_data)):
            current_data = prepared_data.iloc[i]
            
            # Génération du signal
            signal = self.generate_signal(current_data, strategy_config)
            
            # Gestion des positions existantes
            self.manage_existing_positions(current_data, symbol)
            
            # Ouverture de nouvelles positions
            if signal['action'] != 'HOLD' and signal['confidence'] > strategy_config.get('min_confidence', 0.6):
                self.open_position(symbol, current_data, signal, strategy_config)
        
        # Calcul des métriques de performance
        performance = self.calculate_performance_metrics()
        
        return {
            'symbol': symbol,
            'performance': performance,
            'trade_history': self.trade_history,
            'strategy_config': strategy_config
        }
    
    def prepare_data(self, df: pd.DataFrame, strategy_config: Dict) -> pd.DataFrame:
        """Prépare les données pour le backtest"""
        # Ajout des indicateurs techniques
        df = self.add_technical_indicators(df, strategy_config)
        
        # Nettoyage des données
        df = df.dropna()
        
        return df
    
    def add_technical_indicators(self, df: pd.DataFrame, strategy_config: Dict) -> pd.DataFrame:
        """Ajoute les indicateurs techniques nécessaires"""
        # RSI
        df['rsi_14'] = self.calculate_rsi(df['close'], 14)
        
        # MACD
        df['macd'], df['macd_signal'], df['macd_hist'] = self.calculate_macd(df['close'])
        
        # ATR
        df['atr_14'] = self.calculate_atr(df['high'], df['low'], df['close'], 14)
        
        # Moyennes mobiles
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_50'] = df['close'].rolling(50).mean()
        
        # Bollinger Bands
        df['bb_upper'], df['bb_lower'] = self.calculate_bollinger_bands(df['close'], 20)
        
        return df
    
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
    
    def calculate_atr(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
        """Calcule l'ATR"""
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        return atr
    
    def calculate_bollinger_bands(self, series: pd.Series, period: int) -> Tuple[pd.Series, pd.Series]:
        """Calcule les Bollinger Bands"""
        sma = series.rolling(period).mean()
        std = series.rolling(period).std()
        upper_band = sma + (std * 2)
        lower_band = sma - (std * 2)
        return upper_band, lower_band
    
    def generate_signal(self, current_data: pd.Series, strategy_config: Dict) -> Dict:
        """Génère un signal de trading"""
        # Logique de signal de base (à adapter selon la stratégie)
        rsi = current_data['rsi_14']
        macd_hist = current_data['macd_hist']
        
        action = 'HOLD'
        confidence = 0.0
        
        if rsi < 30 and macd_hist > 0:
            action = 'BUY'
            confidence = 0.7
        elif rsi > 70 and macd_hist < 0:
            action = 'SELL'
            confidence = 0.7
        elif 40 < rsi < 60 and abs(macd_hist) < 0.001:
            action = 'HOLD'
            confidence = 0.8
        
        return {
            'action': action,
            'confidence': confidence,
            'timestamp': current_data.name if hasattr(current_data, 'name') else datetime.now()
        }
    
    def manage_existing_positions(self, current_data: pd.Series, symbol: str):
        """Gère les positions existantes"""
        for position in self.positions[:]:
            if position['symbol'] == symbol:
                # Vérifie les stops
                if self.check_stop_loss(position, current_data):
                    self.close_position(position, current_data, 'STOP_LOSS')
                elif self.check_take_profit(position, current_data):
                    self.close_position(position, current_data, 'TAKE_PROFIT')
                elif self.check_time_stop(position, current_data):
                    self.close_position(position, current_data, 'TIME_STOP')
    
    def check_stop_loss(self, position: Dict, current_data: pd.Series) -> bool:
        """Vérifie si le stop loss est atteint"""
        current_price = current_data['close']
        if position['direction'] == 'BUY':
            return current_price <= position['stop_loss']
        else:
            return current_price >= position['stop_loss']
    
    def check_take_profit(self, position: Dict, current_data: pd.Series) -> bool:
        """Vérifie si le take profit est atteint"""
        current_price = current_data['close']
        if position['direction'] == 'BUY':
            return current_price >= position['take_profit']
        else:
            return current_price <= position['take_profit']
    
    def check_time_stop(self, position: Dict, current_data: pd.Series) -> bool:
        """Vérifie si le time stop est atteint"""
        # Implémentation simplifiée
        return False
    
    def open_position(self, symbol: str, current_data: pd.Series, signal: Dict, strategy_config: Dict):
        """Ouvre une nouvelle position"""
        # Calcul du volume basé sur le risk management
        volume = self.calculate_position_size(current_data, strategy_config)
        
        if volume <= 0:
            return
        
        # Niveaux de stop loss et take profit
        stop_loss, take_profit = self.calculate_stop_levels(
            current_data, signal['action'], strategy_config
        )
        
        position = {
            'symbol': symbol,
            'direction': signal['action'],
            'entry_price': current_data['close'],
            'volume': volume,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'entry_time': current_data.name if hasattr(current_data, 'name') else datetime.now(),
            'status': 'OPEN'
        }
        
        self.positions.append(position)
        self.current_balance -= volume * current_data['close'] * 0.01  # Marge simplifiée
    
    def calculate_position_size(self, current_data: pd.Series, strategy_config: Dict) -> float:
        """Calcule la taille de position"""
        risk_per_trade = strategy_config.get('risk_per_trade', 0.02)  # 2% par défaut
        atr = current_data['atr_14']
        
        # Calcul simplifié du volume
        risk_amount = self.current_balance * risk_per_trade
        volume = risk_amount / (atr * strategy_config.get('sl_multiplier', 1.5))
        
        return min(volume, self.current_balance * 0.1)  # Max 10% du capital
    
    def calculate_stop_levels(self, current_data: pd.Series, action: str, strategy_config: Dict) -> Tuple[float, float]:
        """Calcule les niveaux de stop loss et take profit"""
        atr = current_data['atr_14']
        current_price = current_data['close']
        
        sl_multiplier = strategy_config.get('sl_multiplier', 1.5)
        rr_ratio = strategy_config.get('rr_ratio', 1.5)
        
        if action == 'BUY':
            stop_loss = current_price - (atr * sl_multiplier)
            take_profit = current_price + (atr * sl_multiplier * rr_ratio)
        else:
            stop_loss = current_price + (atr * sl_multiplier)
            take_profit = current_price - (atr * sl_multiplier * rr_ratio)
        
        return stop_loss, take_profit
    
    def close_position(self, position: Dict, current_data: pd.Series, close_reason: str):
        """Ferme une position"""
        close_price = current_data['close']
        
        # Calcul du P&L
        if position['direction'] == 'BUY':
            pnl = (close_price - position['entry_price']) * position['volume']
        else:
            pnl = (position['entry_price'] - close_price) * position['volume']
        
        # Mise à jour du solde
        self.current_balance += pnl
        
        # Enregistrement du trade
        trade_record = {
            **position,
            'exit_price': close_price,
            'exit_time': current_data.name if hasattr(current_data, 'name') else datetime.now(),
            'pnl': pnl,
            'close_reason': close_reason,
            'balance_after': self.current_balance
        }
        
        self.trade_history.append(trade_record)
        self.positions.remove(position)
    
    def calculate_performance_metrics(self) -> Dict:
        """Calcule les métriques de performance"""
        if not self.trade_history:
            return {}
        
        trades_df = pd.DataFrame(self.trade_history)
        
        # Métriques de base
        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df['pnl'] > 0])
        losing_trades = len(trades_df[trades_df['pnl'] < 0])
        
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        total_pnl = trades_df['pnl'].sum()
        avg_trade = trades_df['pnl'].mean()
        
        # Drawdown
        balances = [self.initial_balance] + [trade['balance_after'] for trade in self.trade_history]
        cumulative_max = pd.Series(balances).cummax()
        drawdown = (cumulative_max - pd.Series(balances)) / cumulative_max
        max_drawdown = drawdown.max()
        
        # Ratio de Sharpe (simplifié)
        returns = trades_df['pnl'] / self.initial_balance
        sharpe_ratio = returns.mean() / returns.std() if returns.std() > 0 else 0
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'final_balance': self.current_balance,
            'return_percent': (self.current_balance - self.initial_balance) / self.initial_balance * 100,
            'avg_trade_pnl': avg_trade,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'profit_factor': abs(trades_df[trades_df['pnl'] > 0]['pnl'].sum()) / abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum()) if losing_trades > 0 else float('inf')
        }

class StrategyOptimizer:
    def __init__(self):
        self.optimization_results = {}
    
    def optimize_strategy_parameters(self, symbol: str, df: pd.DataFrame, 
                                   base_config: Dict) -> Dict:
        """Optimise les paramètres de stratégie"""
        print(f"🔧 Optimisation des paramètres pour {symbol}...")
        
        best_config = base_config.copy()
        best_performance = -float('inf')
        
        # Grille de paramètres à tester
        param_grid = self.generate_parameter_grid()
        
        for params in param_grid:
            try:
                # Mise à jour de la configuration
                test_config = base_config.copy()
                test_config.update(params)
                
                # Backtest avec ces paramètres
                backtest_engine = BacktestEngine()
                result = backtest_engine.run_backtest(symbol, df, test_config)
                
                # Évaluation de la performance
                performance_score = self.evaluate_performance(result['performance'])
                
                if performance_score > best_performance:
                    best_performance = performance_score
                    best_config = test_config
                    
            except Exception as e:
                print(f"❌ Erreur optimisation paramètres {params}: {e}")
        
        print(f"✅ Meilleurs paramètres pour {symbol}: {best_config}")
        return best_config
    
    def generate_parameter_grid(self) -> List[Dict]:
        """Génère une grille de paramètres à tester"""
        grid = []
        
        # Exemple de grille de paramètres
        rsi_periods = [10, 14, 20]
        macd_fast = [8, 12, 16]
        risk_levels = [0.01, 0.02, 0.03]
        rr_ratios = [1.2, 1.5, 2.0]
        
        for rsi_period in rsi_periods:
            for fast in macd_fast:
                for risk in risk_levels:
                    for rr in rr_ratios:
                        grid.append({
                            'rsi_period': rsi_period,
                            'macd_fast': fast,
                            'risk_per_trade': risk,
                            'rr_ratio': rr
                        })
        
        return grid
    
    def evaluate_performance(self, performance: Dict) -> float:
        """Évalue la performance d'une configuration"""
        if not performance:
            return -float('inf')
        
        # Score composite basé sur plusieurs métriques
        win_rate = performance.get('win_rate', 0)
        sharpe_ratio = performance.get('sharpe_ratio', 0)
        profit_factor = performance.get('profit_factor', 0)
        max_drawdown = performance.get('max_drawdown', 1)
        
        # Pénalité pour drawdown élevé
        drawdown_penalty = max(0, (max_drawdown - 0.1) * 10)  # Pénalise les drawdown > 10%
        
        # Score final
        score = (win_rate * 0.4 + 
                min(sharpe_ratio, 3) * 0.3 +  # Cap Sharpe à 3
                min(profit_factor, 5) * 0.2 -  # Cap profit factor à 5
                drawdown_penalty * 0.1)
        
        return score