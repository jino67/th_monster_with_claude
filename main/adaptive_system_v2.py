import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import statistics
from collections import deque

class AdaptiveTradingSystemV2:
    def __init__(self, data_dir: str = "data_historical/adaptive_data"):
        self.data_dir = data_dir
        self.performance_log = []
        self.error_patterns = {}
        self.adaptive_rules = {}
        self.session_start = datetime.now()
        self.market_regime_history = []
        self.strategy_performance = {}
        self.symbol_analysis = {}
        
        # Système d'apprentissage
        self.learning_rate = 0.1
        self.performance_window = 50
        self.pattern_memory = deque(maxlen=1000)
        
        self._ensure_directory()
        self.load_historical_data()
    
    def _ensure_directory(self):
        """Crée le répertoire de données"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)
            print(f"📁 Dossier Adaptive créé: {self.data_dir}")
    
    def load_historical_data(self):
        """Charge les données historiques d'adaptation"""
        try:
            # Règles adaptatives
            rules_file = os.path.join(self.data_dir, "adaptive_rules_v2.json")
            if os.path.exists(rules_file):
                with open(rules_file, 'r') as f:
                    self.adaptive_rules = json.load(f)
                print("✅ Règles adaptatives historiques chargées")
            
            # Performances historiques
            performance_file = os.path.join(self.data_dir, "performance_history_v2.json")
            if os.path.exists(performance_file):
                with open(performance_file, 'r') as f:
                    self.performance_log = json.load(f)
                print("✅ Historique des performances chargé")
                
        except Exception as e:
            print(f"❌ Erreur chargement données historiques: {e}")
    
    def log_trade_outcome(self, trade_data: Dict, outcome: str, 
                          error_type: Optional[str] = None, 
                          sl_hit: bool = False,
                          market_regime: Optional[str] = None):
        """Enregistre le résultat d'un trade pour l'apprentissage"""
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'symbol': trade_data.get('symbol'),
            'side': trade_data.get('side'),
            'profile': trade_data.get('trade_profile'),
            'outcome': outcome,  # 'win', 'loss', 'error', 'sl_hit'
            'error_type': error_type,
            'sl_hit': sl_hit,
            'market_regime': market_regime,
            'pips': trade_data.get('pips', 0),
            'duration_minutes': trade_data.get('duration', 0),
            'profit': trade_data.get('profit', 0),
            'risk_reward_ratio': trade_data.get('risk_reward_ratio', 0),
            'volatility_regime': trade_data.get('volatility_regime'),
            'entry_conditions': trade_data.get('entry_conditions', {})
        }
        
        self.performance_log.append(log_entry)
        self.pattern_memory.append(log_entry)
        
        # Analyse en temps réel
        self.analyze_trade_patterns()
        self.update_adaptive_rules()
        self.optimize_strategy_parameters()
        
        # Sauvegarde périodique
        if len(self.performance_log) % 10 == 0:
            self.save_adaptive_data()
    
    def analyze_trade_patterns(self):
        """Analyse les patterns de trading pour l'apprentissage"""
        if len(self.performance_log) < 5:
            return
        
        recent_trades = self.get_recent_trades(hours=24)
        
        # Analyse par symbole
        self.analyze_symbol_performance(recent_trades)
        
        # Analyse par profil de trading
        self.analyze_profile_performance(recent_trades)
        
        # Analyse par régime de marché
        self.analyze_market_regime_performance(recent_trades)
        
        # Détection des patterns d'erreur
        self.detect_error_patterns(recent_trades)
        
        # Optimisation des paramètres
        self.optimize_trading_parameters(recent_trades)
    
    def get_recent_trades(self, hours: int = 24) -> List[Dict]:
        """Récupère les trades récents"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [t for t in self.performance_log 
                if datetime.fromisoformat(t['timestamp']) > cutoff_time]
    
    def analyze_symbol_performance(self, recent_trades: List[Dict]):
        """Analyse la performance par symbole"""
        symbol_stats = {}
        
        for trade in recent_trades:
            symbol = trade['symbol']
            if symbol not in symbol_stats:
                symbol_stats[symbol] = {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'total_profit': 0,
                    'total_pips': 0,
                    'error_count': 0,
                    'sl_hit_count': 0,
                    'recent_outcomes': []
                }
            
            stats = symbol_stats[symbol]
            stats['total_trades'] += 1
            stats['recent_outcomes'].append(trade['outcome'])
            
            if trade['outcome'] == 'win':
                stats['winning_trades'] += 1
                stats['total_profit'] += trade.get('profit', 0)
                stats['total_pips'] += trade.get('pips', 0)
            elif trade['outcome'] == 'loss':
                stats['losing_trades'] += 1
                stats['total_profit'] += trade.get('profit', 0)
                stats['total_pips'] += trade.get('pips', 0)
            elif trade['outcome'] == 'error':
                stats['error_count'] += 1
            
            if trade.get('sl_hit'):
                stats['sl_hit_count'] += 1
        
        # Mise à jour des règles par symbole
        for symbol, stats in symbol_stats.items():
            self.update_symbol_rules(symbol, stats)
    
    def update_symbol_rules(self, symbol: str, stats: Dict):
        """Met à jour les règles pour un symbole"""
        total_trades = stats['total_trades']
        if total_trades < 3:
            return
        
        win_rate = stats['winning_trades'] / total_trades
        error_rate = stats['error_count'] / total_trades
        sl_hit_rate = stats['sl_hit_count'] / total_trades
        
        # Règles de trading
        if symbol not in self.adaptive_rules.get('symbol_rules', {}):
            self.adaptive_rules.setdefault('symbol_rules', {})[symbol] = {}
        
        symbol_rules = self.adaptive_rules['symbol_rules'][symbol]
        
        # Ajustement du risk basé sur la performance
        if win_rate < 0.4 or error_rate > 0.3:
            symbol_rules['risk_adjustment'] = 0.5
            symbol_rules['max_daily_trades'] = 2
            symbol_rules['reason'] = f"Performance faible: win_rate={win_rate:.2f}, error_rate={error_rate:.2f}"
        
        elif win_rate > 0.6 and error_rate < 0.1:
            symbol_rules['risk_adjustment'] = 1.2
            symbol_rules['max_daily_trades'] = 8
            symbol_rules['reason'] = f"Performance forte: win_rate={win_rate:.2f}"
        
        else:
            symbol_rules['risk_adjustment'] = 1.0
            symbol_rules['max_daily_trades'] = 5
        
        # Blacklist temporaire pour erreurs répétées
        if error_rate > 0.5 and total_trades >= 5:
            self.adaptive_rules.setdefault('temporary_blacklist', []).append(symbol)
            print(f"🚫 Symbole temporairement blacklisté: {symbol} (taux d'erreur: {error_rate:.2f})")
    
    def analyze_profile_performance(self, recent_trades: List[Dict]):
        """Analyse la performance par profil de trading"""
        profile_stats = {}
        
        for trade in recent_trades:
            profile = trade['profile']
            if profile not in profile_stats:
                profile_stats[profile] = {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'avg_profit': 0,
                    'avg_duration': 0,
                    'success_rate_by_regime': {}
                }
            
            stats = profile_stats[profile]
            stats['total_trades'] += 1
            
            if trade['outcome'] == 'win':
                stats['winning_trades'] += 1
            
            # Statistiques par régime de marché
            regime = trade.get('market_regime', 'UNKNOWN')
            if regime not in stats['success_rate_by_regime']:
                stats['success_rate_by_regime'][regime] = {'wins': 0, 'total': 0}
            
            regime_stats = stats['success_rate_by_regime'][regime]
            regime_stats['total'] += 1
            if trade['outcome'] == 'win':
                regime_stats['wins'] += 1
        
        # Optimisation des paramètres par profil
        for profile, stats in profile_stats.items():
            self.optimize_profile_parameters(profile, stats)
    
    def optimize_profile_parameters(self, profile: str, stats: Dict):
        """Optimise les paramètres pour un profil de trading"""
        total_trades = stats['total_trades']
        if total_trades < 5:
            return
        
        win_rate = stats['winning_trades'] / total_trades
        
        # Ajustement des paramètres de risk
        if profile not in self.adaptive_rules.get('profile_optimizations', {}):
            self.adaptive_rules.setdefault('profile_optimizations', {})[profile] = {}
        
        optimizations = self.adaptive_rules['profile_optimizations'][profile]
        
        # Ajustement du RR ratio
        if win_rate > 0.6:
            optimizations['rr_multiplier'] = 1.1
            optimizations['sl_multiplier'] = 0.9
        elif win_rate < 0.4:
            optimizations['rr_multiplier'] = 0.9
            optimizations['sl_multiplier'] = 1.1
        
        # Optimisation par régime de marché
        regime_success = stats['success_rate_by_regime']
        for regime, regime_stats in regime_success.items():
            if regime_stats['total'] >= 3:
                regime_win_rate = regime_stats['wins'] / regime_stats['total']
                if regime_win_rate < 0.3:
                    optimizations[f'avoid_{regime}'] = True
                elif regime_win_rate > 0.7:
                    optimizations[f'prefer_{regime}'] = True
    
    def analyze_market_regime_performance(self, recent_trades: List[Dict]):
        """Analyse la performance par régime de marché"""
        regime_stats = {}
        
        for trade in recent_trades:
            regime = trade.get('market_regime', 'UNKNOWN')
            if regime not in regime_stats:
                regime_stats[regime] = {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'total_profit': 0,
                    'avg_duration': 0
                }
            
            stats = regime_stats[regime]
            stats['total_trades'] += 1
            
            if trade['outcome'] == 'win':
                stats['winning_trades'] += 1
                stats['total_profit'] += trade.get('profit', 0)
        
        # Mise à jour des préférences de régime
        self.adaptive_rules['regime_preferences'] = {}
        
        for regime, stats in regime_stats.items():
            if stats['total_trades'] >= 3:
                win_rate = stats['winning_trades'] / stats['total_trades']
                self.adaptive_rules['regime_preferences'][regime] = {
                    'win_rate': win_rate,
                    'recommendation': 'STRONG' if win_rate > 0.6 else 'AVOID' if win_rate < 0.3 else 'NEUTRAL'
                }
    
    def detect_error_patterns(self, recent_trades: List[Dict]):
        """Détecte les patterns d'erreur récurrents"""
        error_trades = [t for t in recent_trades if t['outcome'] == 'error']
        
        if not error_trades:
            return
        
        error_patterns = {}
        
        for trade in error_trades:
            error_type = trade.get('error_type', 'UNKNOWN')
            symbol = trade['symbol']
            profile = trade['profile']
            
            key = f"{symbol}_{profile}_{error_type}"
            if key not in error_patterns:
                error_patterns[key] = 0
            error_patterns[key] += 1
        
        # Mise à jour des patterns d'erreur
        for pattern, count in error_patterns.items():
            if count >= 2:  # Pattern répétitif
                self.adaptive_rules.setdefault('error_patterns', {})[pattern] = {
                    'count': count,
                    'last_occurrence': datetime.now().isoformat(),
                    'action': 'REDUCE_RISK' if count < 5 else 'AVOID'
                }
    
    def optimize_trading_parameters(self, recent_trades: List[Dict]):
        """Optimise les paramètres de trading globaux"""
        if len(recent_trades) < 10:
            return
        
        winning_trades = [t for t in recent_trades if t['outcome'] == 'win']
        losing_trades = [t for t in recent_trades if t['outcome'] == 'loss']
        
        if not winning_trades or not losing_trades:
            return
        
        # Analyse des trades gagnants vs perdants
        win_durations = [t.get('duration_minutes', 0) for t in winning_trades]
        loss_durations = [t.get('duration_minutes', 0) for t in losing_trades]
        
        win_pips = [t.get('pips', 0) for t in winning_trades]
        loss_pips = [abs(t.get('pips', 0)) for t in losing_trades]
        
        # Optimisation du time stop
        avg_win_duration = statistics.mean(win_durations) if win_durations else 60
        avg_loss_duration = statistics.mean(loss_durations) if loss_durations else 30
        
        optimal_time_stop = min(avg_win_duration * 0.8, 120)  # Max 2 heures
        
        self.adaptive_rules['optimal_parameters'] = {
            'time_stop_minutes': optimal_time_stop,
            'avg_win_duration': avg_win_duration,
            'avg_loss_duration': avg_loss_duration,
            'avg_win_pips': statistics.mean(win_pips) if win_pips else 0,
            'avg_loss_pips': statistics.mean(loss_pips) if loss_pips else 0
        }
    
    def update_adaptive_rules(self):
        """Met à jour les règles adaptatives globales"""
        # Fusion avec les règles historiques
        historical_rules = self.load_historical_rules()
        
        if historical_rules:
            # Maintient les blacklists historiques
            historical_blacklist = historical_rules.get('historical_blacklist', [])
            current_blacklist = self.adaptive_rules.get('temporary_blacklist', [])
            
            for symbol in current_blacklist:
                if symbol not in historical_blacklist:
                    historical_blacklist.append(symbol)
            
            self.adaptive_rules['historical_blacklist'] = historical_blacklist
            
            # Fusion des optimisations de profil
            historical_optimizations = historical_rules.get('profile_optimizations', {})
            current_optimizations = self.adaptive_rules.get('profile_optimizations', {})
            
            for profile, optimizations in current_optimizations.items():
                if profile in historical_optimizations:
                    # Fusion intelligente des paramètres
                    historical_optimizations[profile].update(optimizations)
                else:
                    historical_optimizations[profile] = optimizations
            
            self.adaptive_rules['profile_optimizations'] = historical_optimizations
        
        # Statistiques de session
        self.update_session_stats()
    
    def load_historical_rules(self) -> Dict:
        """Charge les règles historiques"""
        try:
            rules_file = os.path.join(self.data_dir, "adaptive_rules_v2.json")
            if os.path.exists(rules_file):
                with open(rules_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"❌ Erreur chargement règles historiques: {e}")
        
        return {}
    
    def update_session_stats(self):
        """Met à jour les statistiques de session"""
        recent_trades = self.get_recent_trades(hours=24)
        
        total_trades = len(recent_trades)
        winning_trades = len([t for t in recent_trades if t['outcome'] == 'win'])
        losing_trades = len([t for t in recent_trades if t['outcome'] == 'loss'])
        error_trades = len([t for t in recent_trades if t['outcome'] == 'error'])
        
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        total_profit = sum(t.get('profit', 0) for t in recent_trades)
        avg_profit = total_profit / total_trades if total_trades > 0 else 0
        
        self.adaptive_rules['session_stats'] = {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'error_trades': error_trades,
            'win_rate': win_rate,
            'total_profit': total_profit,
            'avg_profit': avg_profit,
            'session_duration': str(datetime.now() - self.session_start),
            'last_update': datetime.now().isoformat()
        }
    
    def optimize_strategy_parameters(self):
        """Optimise les paramètres stratégiques basés sur la performance"""
        if len(self.performance_log) < 20:
            return
        
        # Analyse des paramètres optimaux par conditions de marché
        self.analyze_optimal_parameters()
        
        # Ajustement des seuils de confiance
        self.adjust_confidence_thresholds()
        
        # Optimisation de la gestion du risk
        self.optimize_risk_management()
    
    def analyze_optimal_parameters(self):
        """Analyse les paramètres optimaux pour différentes conditions"""
        # Groupement des trades par conditions
        regime_trades = {}
        volatility_trades = {}
        
        for trade in self.performance_log[-100:]:  # Derniers 100 trades
            regime = trade.get('market_regime')
            volatility = trade.get('volatility_regime')
            
            if regime:
                if regime not in regime_trades:
                    regime_trades[regime] = []
                regime_trades[regime].append(trade)
            
            if volatility:
                if volatility not in volatility_trades:
                    volatility_trades[volatility] = []
                volatility_trades[volatility].append(trade)
        
        # Calcul des paramètres optimaux par régime
        optimal_params = {}
        
        for regime, trades in regime_trades.items():
            if len(trades) >= 5:
                win_rate = len([t for t in trades if t['outcome'] == 'win']) / len(trades)
                avg_rr = statistics.mean([t.get('risk_reward_ratio', 1.5) for t in trades if t.get('risk_reward_ratio')])
                
                optimal_params[f'regime_{regime}'] = {
                    'recommended_rr': avg_rr * (1.1 if win_rate > 0.5 else 0.9),
                    'risk_adjustment': 1.2 if win_rate > 0.6 else 0.8 if win_rate < 0.4 else 1.0,
                    'win_rate': win_rate
                }
        
        self.adaptive_rules['optimal_parameters_by_regime'] = optimal_params
    
    def adjust_confidence_thresholds(self):
        """Ajuste les seuils de confiance basés sur la performance"""
        recent_trades = self.get_recent_trades(hours=6)
        
        if len(recent_trades) < 10:
            return
        
        # Analyse de la précision des signaux
        high_confidence_trades = [t for t in recent_trades 
                                if t.get('entry_conditions', {}).get('confidence', 0) > 0.7]
        low_confidence_trades = [t for t in recent_trades 
                               if t.get('entry_conditions', {}).get('confidence', 0) <= 0.7]
        
        if high_confidence_trades:
            high_confidence_win_rate = len([t for t in high_confidence_trades if t['outcome'] == 'win']) / len(high_confidence_trades)
        else:
            high_confidence_win_rate = 0
        
        if low_confidence_trades:
            low_confidence_win_rate = len([t for t in low_confidence_trades if t['outcome'] == 'win']) / len(low_confidence_trades)
        else:
            low_confidence_win_rate = 0
        
        # Ajustement du seuil de confiance minimum
        if high_confidence_win_rate > 0.6 and low_confidence_win_rate < 0.4:
            self.adaptive_rules['min_confidence_threshold'] = 0.7
        elif high_confidence_win_rate < 0.5:
            self.adaptive_rules['min_confidence_threshold'] = 0.5
        else:
            self.adaptive_rules['min_confidence_threshold'] = 0.6
    
    def optimize_risk_management(self):
        """Optimise la gestion du risk"""
        recent_trades = self.get_recent_trades(hours=24)
        
        if len(recent_trades) < 15:
            return
        
        # Analyse du drawdown
        equity_curve = []
        current_equity = 0
        
        for trade in sorted(recent_trades, key=lambda x: x['timestamp']):
            current_equity += trade.get('profit', 0)
            equity_curve.append(current_equity)
        
        if equity_curve:
            peak = max(equity_curve)
            current = equity_curve[-1]
            drawdown = (peak - current) / peak * 100 if peak > 0 else 0
            
            # Ajustement agressif en cas de drawdown important
            if drawdown > 10:
                self.adaptive_rules['risk_management'] = {
                    'global_risk_multiplier': 0.5,
                    'max_positions': 3,
                    'reason': f"Drawdown élevé: {drawdown:.1f}%"
                }
            elif drawdown > 5:
                self.adaptive_rules['risk_management'] = {
                    'global_risk_multiplier': 0.8,
                    'max_positions': 5
                }
            else:
                self.adaptive_rules['risk_management'] = {
                    'global_risk_multiplier': 1.0,
                    'max_positions': 8
                }
    
    def should_trade_symbol(self, symbol: str, profile: str) -> Tuple[bool, str]:
        """Vérifie si le trading est autorisé pour ce symbole/profil"""
        
        # Vérification blacklist historique
        historical_blacklist = self.adaptive_rules.get('historical_blacklist', [])
        if symbol in historical_blacklist:
            return False, f"Symbole blacklisté historiquement"
        
        # Vérification blacklist temporaire
        temporary_blacklist = self.adaptive_rules.get('temporary_blacklist', [])
        if symbol in temporary_blacklist:
            return False, f"Symbole temporairement blacklisté"
        
        # Vérification des limites par symbole
        symbol_rules = self.adaptive_rules.get('symbol_rules', {}).get(symbol, {})
        max_daily_trades = symbol_rules.get('max_daily_trades', 5)
        
        # Compte les trades du jour pour ce symbole
        today_trades = [t for t in self.get_recent_trades(hours=24) 
                        if t['symbol'] == symbol]
        
        if len(today_trades) >= max_daily_trades:
            return False, f"Limite quotidienne atteinte: {len(today_trades)}/{max_daily_trades}"
        
        # Vérification des patterns d'erreur
        error_patterns = self.adaptive_rules.get('error_patterns', {})
        for pattern in error_patterns:
            if symbol in pattern and profile in pattern:
                if error_patterns[pattern]['action'] == 'AVOID':
                    return False, f"Pattern d'erreur détecté: {pattern}"
        
        return True, "OK"
    
    def get_risk_adjustment(self, symbol: str, profile: str, market_regime: str) -> float:
        """Retourne le facteur d'ajustement du risk"""
        base_adjustment = 1.0
        
        # Ajustement par symbole
        symbol_rules = self.adaptive_rules.get('symbol_rules', {}).get(symbol, {})
        base_adjustment *= symbol_rules.get('risk_adjustment', 1.0)
        
        # Ajustement par profil
        profile_optimizations = self.adaptive_rules.get('profile_optimizations', {}).get(profile, {})
        base_adjustment *= profile_optimizations.get('risk_multiplier', 1.0)
        
        # Ajustement par régime de marché
        regime_params = self.adaptive_rules.get('optimal_parameters_by_regime', {}).get(f'regime_{market_regime}', {})
        base_adjustment *= regime_params.get('risk_adjustment', 1.0)
        
        # Ajustement global de risk management
        risk_management = self.adaptive_rules.get('risk_management', {})
        base_adjustment *= risk_management.get('global_risk_multiplier', 1.0)
        
        return max(0.1, min(base_adjustment, 2.0))  # Limites 10% à 200%
    
    def get_optimized_parameters(self, symbol: str, profile: str, market_regime: str) -> Dict:
        """Retourne les paramètres optimisés pour le trading"""
        base_params = {
            'rr_multiplier': 1.0,
            'sl_multiplier': 1.0,
            'time_stop_multiplier': 1.0,
            'confidence_threshold': self.adaptive_rules.get('min_confidence_threshold', 0.6)
        }
        
        # Optimisations par profil
        profile_optimizations = self.adaptive_rules.get('profile_optimizations', {}).get(profile, {})
        base_params['rr_multiplier'] *= profile_optimizations.get('rr_multiplier', 1.0)
        base_params['sl_multiplier'] *= profile_optimizations.get('sl_multiplier', 1.0)
        
        # Optimisations par régime
        regime_params = self.adaptive_rules.get('optimal_parameters_by_regime', {}).get(f'regime_{market_regime}', {})
        base_params['rr_multiplier'] *= regime_params.get('recommended_rr', 1.0) / 1.5  # Normalisation
        
        return base_params
    
    def get_market_regime_recommendation(self, regime: str) -> str:
        """Retourne la recommandation pour un régime de marché"""
        preferences = self.adaptive_rules.get('regime_preferences', {}).get(regime, {})
        return preferences.get('recommendation', 'NEUTRAL')
    
    def save_adaptive_data(self):
        """Sauvegarde toutes les données d'adaptation"""
        try:
            # Règles adaptatives
            rules_file = os.path.join(self.data_dir, "adaptive_rules_v2.json")
            with open(rules_file, 'w', encoding='utf-8') as f:
                json.dump(self.adaptive_rules, f, indent=2, ensure_ascii=False)
            
            # Historique des performances
            performance_file = os.path.join(self.data_dir, "performance_history_v2.json")
            with open(performance_file, 'w', encoding='utf-8') as f:
                json.dump(self.performance_log, f, indent=2, ensure_ascii=False)
            
            print("💾 Données adaptatives sauvegardées")
            
        except Exception as e:
            print(f"❌ Erreur sauvegarde données adaptatives: {e}")

    # =========================================================
    # === CORRECTIF V2 : AJOUT DE LA MÉTHODE MANQUANTE ===
    # =========================================================
    def save_session_data(self):
        """Alias pour save_adaptive_data (Compatibilité avec le moteur)"""
        self.save_adaptive_data()