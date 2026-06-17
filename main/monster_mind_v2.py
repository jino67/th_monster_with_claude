import time
import json
import csv
import MetaTrader5 as mt5
import os
from typing import Dict
import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import sys

# Configuration robuste des imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

# Import des modules V2
try:
    from core.historical_miner import HistoricalDataMiner
    from core.advanced_indicators import AdvancedIndicators
    from core.market_regime_detector import MarketRegimeDetector
    from core.multi_timeframe_engine import MultiTimeframeEngine
    from strategies.volatility_strategy import VolatilityStrategy
    from strategies.crash_boom_strategy import CrashBoomStrategy
    from strategies.jump_strategy import JumpStrategy
    from strategies.strategy_optimizer import StrategyOptimizer
    from main.adaptive_system_v2 import AdaptiveTradingSystemV2
    from main.position_corrector_v2 import SmartPositionCorrectorV2
except ImportError as e:
    print(f"❌ Erreur import modules V2: {e}")
    # Fallback: ajout explicite des chemins
    sys.path.insert(0, os.path.join(project_root, 'core'))
    sys.path.insert(0, os.path.join(project_root, 'strategies'))
    from core.historical_miner import HistoricalDataMiner
    from core.advanced_indicators import AdvancedIndicators
    from core.market_regime_detector import MarketRegimeDetector
    from core.multi_timeframe_engine import MultiTimeframeEngine
    from strategies.volatility_strategy import VolatilityStrategy
    from strategies.crash_boom_strategy import CrashBoomStrategy
    from strategies.jump_strategy import JumpStrategy
    from strategies.strategy_optimizer import StrategyOptimizer
    from main.adaptive_system_v2 import AdaptiveTradingSystemV2
    from main.position_corrector_v2 import SmartPositionCorrectorV2

# Import des modules Utils
try:
    utils_path = os.path.join(project_root, 'utils')
    if utils_path not in sys.path:
        sys.path.insert(0, utils_path)
    
    from market_data_mt5 import fetch_m1, fetch_m5, fetch_m15, fetch_h1
    from risk_manager_mt5 import calculate_stake, get_tick_value
    from mt5_initializer import initialize_mt5, shutdown_mt5
    
    try:
        from indicators import rsi, macd_hist, in_trend, atr, adx, ichimoku
    except ImportError:
        pass 

    print("✅ TOUS les modules utils chargés - MODE RÉEL ACTIVÉ ⚠️")
    
except ImportError as e:
    print(f"❌ Erreur critique import modules utils: {e}")
    sys.exit(1)

# Variables Globales (maintenues pour la compatibilité avec l'ancien code)
active_trades = []
INITIAL_EQUITY = 0.0

# =========================================================================
# === CLASSE BROADCASTER POUR LE DASHBOARD ===
# =========================================================================
class DataBroadcaster:
    """Enregistre l'état du bot pour le Dashboard en temps réel"""
    def __init__(self):
        self.state_file = "dashboard_live_state.json"
        
    def broadcast(self, account_info, open_positions, recent_trades):
        """Écrit l'état complet dans un JSON écrasé à chaque fois"""
        positions_list = []
        if open_positions:
            for p in open_positions:
                positions_list.append({
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": "BUY" if p.type == 0 else "SELL",
                    "volume": float(p.volume),
                    "price_open": float(p.price_open),
                    "price_current": float(p.price_current),
                    "profit": float(p.profit),
                    "time": datetime.fromtimestamp(p.time).isoformat()
                })

        state = {
            "last_update": datetime.now().isoformat(),
            "account": {
                "balance": float(account_info.get('balance', 0)),
                "equity": float(account_info.get('equity', 0)),
                "margin": float(account_info.get('margin', 0))
            },
            "open_positions": positions_list,
            # On prend les 50 trades les plus récents de l'activité.
            "recent_history": recent_trades[-50:] if recent_trades else [] 
        }
        
        try:
            temp_file = self.state_file + ".tmp"
            with open(temp_file, 'w') as f:
                json.dump(state, f, indent=2)
            # Utilisation de os.replace pour une opération atomique sur différents OS
            os.replace(temp_file, self.state_file)
        except Exception:
            pass

# =========================================================================
# === AUDITEUR D'HISTORIQUE (POUR LES PROFITS RÉELS) ===
# =========================================================================
class HistoryAuditor:
    """Surveille les trades fermés pour mettre à jour le CSV avec le vrai profit"""
    def __init__(self, csv_path):
        self.csv_path = csv_path
        self.last_check = datetime.now()
        # Stocke les tickets des DEALS (transactions de clôture) connus
        self.known_deals = set()
        
        # AJOUT CRITIQUE: Crée le répertoire si le chemin du fichier n'existe pas
        log_dir = os.path.dirname(self.csv_path)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
                print(f"✅ Répertoire de log créé: {log_dir}")
            except Exception as e:
                print(f"❌ Erreur critique lors de la création du répertoire: {e}")
                
    def scan_and_log(self):
        """Scanne l'historique MT5 pour les nouvelles fermetures"""
        try:
            # On regarde l'historique depuis la dernière vérification (plus un buffer)
            from_date = self.last_check - timedelta(minutes=5)  # Utilisation d'un buffer de 5 minutes
            
            # Utiliser le temps du serveur MT5 si possible pour une meilleure précision
            to_date = datetime.now() + timedelta(minutes=1) 
            
            deals = mt5.history_deals_get(date_from=from_date, date_to=to_date)
            
            if deals:
                for deal in deals:
                    # On cherche les sorties (ENTRY_OUT ou ENTRY_OUT_BY)
                    # et que le DEAL n'a pas déjà été loggué (vérification par deal.ticket)
                    if deal.entry in [mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY] and deal.ticket not in self.known_deals:
                        self.known_deals.add(deal.ticket)
                        # C'est un trade fermé ! On l'ajoute au CSV
                        self._write_closure_to_csv(deal)
            
            self.last_check = datetime.now()
            
        except Exception as e:
            # print(f"⚠️ Erreur Audit: {e}") # Désactivé pour alléger la console
            pass

    def _write_closure_to_csv(self, deal):
        """
        Récupère l'ordre d'ouverture et ÉCRIT la ligne de clôture pour s'assurer 
        que le P/L est bien là.
        """
        try:
            # 1. Récupérer l'ordre d'ouverture MT5 (c'est l'identifiant du trade)
            orders = mt5.history_orders_get(ticket_from=deal.order, ticket_to=deal.order)
            if not orders:
                # Ceci peut arriver si l'ordre est très vieux et n'est plus en cache
                print(f"⚠️ Ordre d'ouverture introuvable pour le ticket: {deal.order}")
                return

            order = orders[0]
            
            # Calcul du VRAI Profit total (Profit + Coûts)
            profit = deal.profit + deal.swap + deal.commission
            
            # Déterminer la direction de l'OUVERTURE
            open_direction = "BUY" if order.type in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_BUY_LIMIT] else "SELL"
            
            # Déterminer le statut de clôture
            # Utilisation d'une petite tolérance (1e-5) pour la comparaison de prix
            TOLERANCE = 1e-5 
            
            is_sl = order.sl != 0.0 and abs(order.sl - deal.price) < TOLERANCE
            is_tp = order.tp != 0.0 and abs(order.tp - deal.price) < TOLERANCE
            
            if is_sl:
                 status = "SL"
            elif is_tp:
                 status = "TP"
            else:
                 status = "CLOSED" # Clôturé manuellement ou par time-stop
                
            
            # Vérifier si le fichier existe pour l'entête
            file_exists = os.path.isfile(self.csv_path)
            
            # --- Écriture de la Ligne ---
            with open(self.csv_path, mode='a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                if not file_exists:
                    writer.writerow(['ticket', 'symbol', 'direction', 'volume', 'price', 'sl', 'tp', 'profile', 'status', 'timestamp', 'profit', 'score'])
                
                # Écrire la ligne de clôture complète
                writer.writerow([
                    deal.order,                                              # Ticket de l'ORDRE (identifiant unique du trade)
                    deal.symbol,                                             # Symbol
                    open_direction,                                          # Direction réelle du trade (BUY ou SELL)
                    order.volume_initial,                                    # Volume initial
                    order.price_open,                                        # Prix d'Ouverture
                    order.sl,                                                # SL initial (ou modifié)
                    order.tp,                                                # TP initial (ou modifié)
                    "AUDITOR",                                               # Profile (pour différencier de l'ouverture)
                    status,                                                  # Status: SL/TP/CLOSED
                    datetime.fromtimestamp(deal.time).isoformat(),           # Time de la CLÔTURE
                    round(profit, 2),                                        # VRAI PROFIT FINAL (le gain ou la perte)
                    0.0                                                      # Score
                ])
                
                # Ajout d'un indicateur de gain/perte
                result_msg = "GAIN" if profit > 0 else "PERTE" if profit < 0 else "NUL"
                print(f"💰 TRADE COMPLET ENREGISTRÉ: {deal.symbol} | Résultat: {result_msg} | P/L: {profit:.2f} $")
                
        except Exception as e: 
            # Imprimer l'erreur pour le débogage si le fichier n'est toujours pas créé
            print(f"❌ Erreur critique HistoryAuditor._write_closure_to_csv: {e}")
            pass
# =========================================================================
# === CŒUR DU SYSTÈME ===
# =========================================================================

class MonsterMindV2:
    def __init__(self):
        self.load_configurations()
        self.initialize_systems()
        self.setup_global_variables()
        
    def load_configurations(self):
        try:
            config_dir = os.path.join(project_root, "config")
            with open(os.path.join(config_dir, "config_symbols_v2.json")) as f:
                self.symbol_config = json.load(f)
            with open(os.path.join(config_dir, "config_global_v2.json")) as f:
                self.global_config = json.load(f)
            print("✅ Configurations V2 chargées avec succès")
        except FileNotFoundError as e:
            print(f"❌ Erreur chargement configurations: {e}")
            raise
        
        self.SYMBOLS = [s for s in self.symbol_config.keys() if s not in ["REGIME_BASED_ADJUSTMENTS", "GLOBAL_SETTINGS"]]
        trading_settings = self.global_config["TRADING_SETTINGS"]
        data_settings = self.global_config["DATA_SETTINGS"]
        
        self.SLEEP_SEC = trading_settings["SLEEP_SEC"]
        self.MAX_OPEN_POSITIONS = trading_settings["MAX_OPEN_POSITIONS"]
        self.MAX_POSITIONS_PER_SYMBOL = trading_settings["MAX_POSITIONS_PER_SYMBOL"]
        self.MAX_DAILY_LOSS_PERCENT = trading_settings["MAX_DAILY_LOSS_PERCENT"]
        self.MAGIC_NUMBER = 999666
        
        self.HIST_M1 = data_settings["HIST_M1"]
        self.HIST_M5 = data_settings["HIST_M5"]
        self.HIST_M15 = data_settings["HIST_M15"]
        self.HIST_H1 = data_settings["HIST_H1"]
        
        self.TRADE_LOG_FILE = self.global_config["REPORTING_SETTINGS"]["TRADES_CSV_PATH"]
        self.RISK_MODE = self.global_config["RISK_MANAGEMENT"]["DEFAULT_RISK_MODE"]
        
    def initialize_systems(self):
        print("🚀 Initialisation des systèmes MonsterMind V2...")
        self.historical_miner = HistoricalDataMiner()
        self.advanced_indicators = AdvancedIndicators()
        self.regime_detector = MarketRegimeDetector()
        self.multi_tf_engine = MultiTimeframeEngine()
        self.volatility_strategy = VolatilityStrategy()
        self.crash_boom_strategy = CrashBoomStrategy()
        self.jump_strategy = JumpStrategy()
        self.strategy_optimizer = StrategyOptimizer()
        self.adaptive_system = AdaptiveTradingSystemV2()
        self.position_corrector = SmartPositionCorrectorV2(self.adaptive_system)
        print("✅ Tous les systèmes V2 initialisés")
    
    def setup_global_variables(self):
        global active_trades, INITIAL_EQUITY
        active_trades = []
        # Supprimé: SYMBOL_REJECTION_LOG n'est pas utilisé dans le code actuel
        account = mt5.account_info()
        INITIAL_EQUITY = account.equity if account else 0.0
        self.MAX_REJECTION_ATTEMPTS = 3

    def run_historical_analysis(self):
        if self.global_config["DATA_SETTINGS"]["ENABLE_HISTORICAL_ANALYSIS"]:
            print("📊 Démarrage de l'analyse historique OPTIMISÉE...")
            try:
                print("🔍 Vérification de l'état des données...")
                self.historical_miner.quick_data_check(self.SYMBOLS)
                print("🔄 Collecte incrémentale en cours...")
                insights = self.historical_miner.collect_comprehensive_data(self.SYMBOLS)
                if insights is None:
                    insights = self.historical_miner.generate_market_insights(self.SYMBOLS)
                print("✅ Analyse historique OPTIMISÉE terminée")
                return insights
            except Exception as e:
                print(f"❌ Erreur analyse historique optimisée: {e}")
                return self.fallback_historical_analysis()
        return None

    def fallback_historical_analysis(self):
        try:
            print("🔄 Tentative de collecte standard...")
            insights = self.historical_miner.collect_comprehensive_data(self.SYMBOLS)
            print("✅ Analyse historique (fallback) terminée")
            return insights
        except Exception as e:
            print(f"❌ Erreur même en fallback: {e}")
            return None

    def run_initial_analysis_period(self, duration_minutes: int = 15):
        print(f"🔍 Analyse de marché initiale ({duration_minutes} minutes)...")
        start_time = time.time()
        market_analysis = {}
        for minute in range(duration_minutes):
            print(f"📈 Analyse en cours... ({minute + 1}/{duration_minutes})")
            for symbol in self.SYMBOLS:
                try:
                    df_m1 = fetch_m1(symbol, self.HIST_M1)
                    df_m5 = fetch_m5(symbol, self.HIST_M5)
                    df_m15 = fetch_m15(symbol, self.HIST_M15)
                    if df_m1 is not None and len(df_m1) > 0:
                        regime_analysis = self.regime_detector.detect_current_regime(symbol, df_m1, df_m5, df_m15)
                        if symbol not in market_analysis: market_analysis[symbol] = []
                        market_analysis[symbol].append({'regime_analysis': regime_analysis, 'timestamp': datetime.now().isoformat()})
                except Exception: pass
            elapsed = time.time() - start_time
            # Calcule le temps restant jusqu'à la prochaine minute (pour une synchronisation propre)
            remaining = max(0, 60 - (elapsed % 60)) 
            if minute < duration_minutes - 1: time.sleep(remaining)
        print("✅ Analyse de marché initiale terminée")
        return market_analysis

class AdvancedTradingEngine:
    def __init__(self, monster_mind: MonsterMindV2):
        self.monster_mind = monster_mind
        self.config = monster_mind.global_config
        self.performance_stats = {'total_trades': 0, 'winning_trades': 0, 'losing_trades': 0}
        
    def execute_trading_cycle(self):
        self.correct_existing_positions()
        market_analysis = self.analyze_current_market()
        trading_signals = self.find_trading_signals(market_analysis)
        executed_trades = self.execute_trading_signals(trading_signals)
        self.update_performance_stats(executed_trades)
        return executed_trades
    
    def correct_existing_positions(self):
        if self.config["TRADING_SETTINGS"]["AUTO_POSITION_CORRECTION"]:
            corrections = self.monster_mind.position_corrector.monitor_and_correct_positions()
            if corrections:
                print(f"🔧 Corrections: {len(corrections)} pos")
    
    def analyze_current_market(self) -> Dict:
        market_analysis = {}
        for symbol in self.monster_mind.SYMBOLS:
            try:
                df_m1 = fetch_m1(symbol, self.monster_mind.HIST_M1)
                df_m5 = fetch_m5(symbol, self.monster_mind.HIST_M5)
                df_m15 = fetch_m15(symbol, self.monster_mind.HIST_M15)
                
                if df_m1 is None or len(df_m1) == 0:
                    market_analysis[symbol] = {'error': 'Données manquantes'}
                    continue
                
                regime_analysis = self.monster_mind.regime_detector.detect_current_regime(symbol, df_m1, df_m5, df_m15)
                
                # Sélection dynamique de la stratégie
                if "Volatility" in symbol:
                    strategy_analysis = self.monster_mind.volatility_strategy.analyze_volatility_conditions(symbol, df_m1, df_m5, df_m15)
                elif "Crash" in symbol or "Boom" in symbol:
                    strategy_analysis = self.monster_mind.crash_boom_strategy.analyze_crash_boom_conditions(symbol, df_m1, df_m5, df_m15)
                elif "Jump" in symbol:
                    strategy_analysis = self.monster_mind.jump_strategy.analyze_jump_conditions(symbol, df_m1, df_m5, df_m15)
                else:
                    strategy_analysis = {'action': 'HOLD', 'confidence': 0, 'reason': 'No strategy match'}
                
                market_analysis[symbol] = {'regime': regime_analysis, 'strategy': strategy_analysis, 'data_quality': 'GOOD', 'timestamp': datetime.now().isoformat()}
            except Exception as e:
                market_analysis[symbol] = {'error': str(e)}
        return market_analysis
    
    def find_trading_signals(self, market_analysis: Dict) -> List[Dict]:
        trading_signals = []
        min_confidence = self.config["STRATEGY_SETTINGS"]["MIN_CONFIDENCE_SCORE"]

        for symbol, analysis in market_analysis.items():
            if 'error' in analysis: continue
            strategy_analysis = analysis['strategy']
            
            current_action = strategy_analysis.get('action', 'HOLD')
            if current_action == 'HOLD': current_action = strategy_analysis.get('recommended_action', 'HOLD')

            confidence = strategy_analysis.get('confidence_score', 0)
            if confidence == 0: confidence = strategy_analysis.get('confidence', 0)
            
            if current_action == "HOLD": continue
            if confidence < min_confidence: continue
            if not self.check_position_limits(symbol): continue
            if not self.check_adaptive_rules(symbol, strategy_analysis): continue
            
            signal = {
                'symbol': symbol,
                'action': current_action,
                'direction': strategy_analysis.get('direction', 'BULLISH' if current_action == 'BUY' else 'BEARISH'),
                'profile': strategy_analysis.get('profile', 'SCALPING'),
                'confidence': confidence,
                'risk_adjustment': strategy_analysis.get('risk_adjustment', 1.0),
                'reason': strategy_analysis.get('reason', 'Signal V4 Validated'),
                'regime': analysis['regime'].get('composite_regime', 'UNKNOWN'),
                'timestamp': datetime.now().isoformat()
            }
            print(f"✅ SIGNAL VALIDÉ V4: {symbol} {current_action} (Score: {confidence:.2f})")
            trading_signals.append(signal)
            
        return trading_signals
    
    def check_position_limits(self, symbol: str) -> bool:
        try:
            total_positions = mt5.positions_total()
            if total_positions is None: return False 
            if total_positions >= self.monster_mind.MAX_OPEN_POSITIONS: 
                # print("Rejet: Max positions atteint")
                return False
            symbol_positions = mt5.positions_get(symbol=symbol)
            if symbol_positions and len(symbol_positions) >= self.monster_mind.MAX_POSITIONS_PER_SYMBOL: 
                # print(f"Rejet: Max positions pour {symbol} atteint")
                return False
            return True
        except Exception: return False 
    
    def check_adaptive_rules(self, symbol: str, strategy_analysis: Dict) -> bool:
        try:
            profile = strategy_analysis.get('profile', 'SCALPING')
            can_trade, reason = self.monster_mind.adaptive_system.should_trade_symbol(symbol, profile)
            if not can_trade: 
                # print(f"Rejet Adaptatif: {reason}")
                return False
            return True
        except Exception: return True 
    
    def execute_trading_signals(self, trading_signals: List[Dict]) -> List[Dict]:
        executed_trades = []
        for signal in trading_signals:
            try:
                trade_result = self.execute_single_trade(signal)
                if trade_result:
                    trade_result['score'] = signal.get('confidence', 0)
                    trade_result['profit'] = 0.0
                    self.log_trade_to_csv(trade_result)
                    executed_trades.append(trade_result)
            except Exception as e:
                print(f"❌ Erreur exécution {signal['symbol']}: {e}")
        return executed_trades



    def log_trade_to_csv(self, trade: Dict):
        """
        Enregistre les détails d'un trade (souvent à l'ouverture) dans le fichier log CSV.
        La création du répertoire est assurée.
        """
        file_path = self.monster_mind.TRADE_LOG_FILE
        
        # --- CRITIQUE: Assurer l'existence du répertoire ---
        log_dir = os.path.dirname(file_path)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
            except Exception as e:
                # S'il y a un problème de permission ou autre, on log l'erreur et on quitte
                print(f"❌ Impossible de créer le répertoire de log ({log_dir}): {e}")
                return # Arrêter la fonction si on ne peut pas créer le dossier

        file_exists = os.path.isfile(file_path)
        
        try:
            with open(file_path, mode='a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                
                # Écriture de l'en-tête (seulement si le fichier vient d'être créé)
                if not file_exists:
                    writer.writerow([
                        'ticket', 'symbol', 'direction', 'volume', 'price', 'sl', 'tp', 
                        'profile', 'status', 'timestamp', 'profit', 'score'
                    ])
                    
                # Écriture des données du trade
                writer.writerow([
                    trade['ticket'], 
                    trade['symbol'], 
                    trade['direction'], 
                    trade['volume'], 
                    trade['price'], 
                    trade['sl'], 
                    trade['tp'], 
                    trade['profile'], 
                    trade['status'], 
                    trade['timestamp'], # Assumer que le timestamp est donné à l'ouverture
                    trade.get('profit', 0.0), 
                    trade.get('score', 0.0)
                ])
                
        except Exception as e: 
            # Remplacer le 'pass' silencieux par un print pour le débogage
            print(f"❌ Erreur lors de l'écriture du trade dans le CSV: {e}") 
            # Conserver un 'pass' final si vous ne voulez pas que le bot soit interrompu
            pass
    
    def execute_single_trade(self, signal: Dict) -> Optional[Dict]:
        symbol = signal['symbol']
        direction = signal['direction'] 
        profile = signal['profile']
        
        order_type = None
        if direction in ["BULLISH", "BUY", "Buy", "buy"]:
            direction = "BUY"
            order_type = mt5.ORDER_TYPE_BUY
        elif direction in ["BEARISH", "SELL", "Sell", "sell"]:
            direction = "SELL"
            order_type = mt5.ORDER_TYPE_SELL
        else: return None

        try:
            # 1. Préparation du symbole
            if not mt5.symbol_info(symbol).visible:
                if not mt5.symbol_select(symbol, True): return None

            # 2. Données et ATR
            df_m1 = fetch_m1(symbol, self.monster_mind.HIST_M1)
            if df_m1 is None or len(df_m1) == 0: return None
            # Calcul ATR pour SL dynamique
            atr_m1 = atr(df_m1["close"], df_m1["high"], df_m1["low"]).iloc[-1]
            
            # 3. Calcul du Lot (Stake) basé sur le risque
            risk_adjustment = signal.get('risk_adjustment', 1.0)
            symbol_profile_cfg = self.monster_mind.symbol_config.get(symbol, {}).get(profile, {})
            # Fallback si config de profil manquante
            if not symbol_profile_cfg: symbol_profile_cfg = {"RISK_PERCENT": 0.01, "SL_ATR_MULTIPLE": 3.0, "RR": 1.5, "MAX_LOT": 0.01}

            adjusted_risk_percent = symbol_profile_cfg.get("RISK_PERCENT", 0.01) * risk_adjustment
            adjusted_sl_multiple = symbol_profile_cfg.get("SL_ATR_MULTIPLE", 3.0)
            
            account_info = self.get_account_info()
            stake = calculate_stake(
                balance=account_info["balance"],
                symbol=symbol,
                risk_mode=self.monster_mind.RISK_MODE,
                risk_value=adjusted_risk_percent * 100,  # Convertir en pourcentage
                atr=atr_m1,
                atr_multiplier=adjusted_sl_multiple,
                verbose=False
            )
            
            # 4. --- CORRECTION VOLUME ET STEP (CODE 10014) ---
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None: return None
            
            step_vol = symbol_info.volume_step
            min_vol = symbol_info.volume_min
            max_vol = symbol_info.volume_max
            
            # 1. Arrondir au "Step"
            if step_vol > 0:
                # Utiliser round sur le résultat pour une meilleure précision
                stake = round(stake / step_vol) * step_vol 
                # Déterminer le nombre de décimales à partir du step
                decimals = len(str(step_vol).split('.')[-1]) if '.' in str(step_vol) else 0
                stake = round(stake, decimals)

            # 2. Forcer les limites MT5
            if stake < min_vol: stake = min_vol 
            if stake > max_vol: stake = max_vol

            # 3. Limite Utilisateur JSON
            max_allowed = symbol_profile_cfg.get("MAX_LOT", 100.0)
            if stake > max_allowed: stake = max_allowed
            
            # Vérification finale (peut être 0 si balance faible et min_vol élevé)
            if stake < min_vol: 
                print(f"⚠️ Rejet: {symbol} Lot trop faible ({stake} < {min_vol})")
                return None
            
            # 5. Calcul des Prix SL et TP (VERSION BLINDÉE)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None: return None
            
            min_dist_points = symbol_info.trade_stops_level
            point_size = symbol_info.point
            spread_points = (tick.ask - tick.bid) / point_size
            
            # Distance minimale de sécurité (distance min broker, 2x spread, ou 50 points mini)
            safe_dist_points = max(min_dist_points, spread_points * 2, 50) 
            min_dist_price = safe_dist_points * point_size
            
            sl_dist = atr_m1 * adjusted_sl_multiple
            tp_dist = sl_dist * symbol_profile_cfg.get("RR", 1.5)
            
            # Assurer que les distances sont supérieures à la distance minimale du broker
            if sl_dist < min_dist_price: sl_dist = min_dist_price
            if tp_dist < min_dist_price: tp_dist = min_dist_price

            if direction == "BUY":
                price = tick.ask
                sl = price - sl_dist
                tp = price + tp_dist
            elif direction == "SELL":
                price = tick.bid
                sl = price + sl_dist
                tp = price - tp_dist
            
            # Arrondir SL/TP au tick size du symbole
            # Non implémenté ici pour laisser MT5 gérer l'arrondi, mais c'est une amélioration possible.
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(stake),
                "type": order_type,
                "price": price,
                "sl": sl,
                "tp": tp,
                "deviation": 50, # Deviation en points
                "magic": self.monster_mind.MAGIC_NUMBER,
                "comment": f"MM_V4_{profile}", 
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK, # Fill or Kill, très strict
            }
            
            # Check Marge
            margin_check = mt5.order_calc_margin(order_type, symbol, stake, price)
            if margin_check and margin_check > account_info['equity']:
                print(f"❌ Marge insuffisante {symbol} ({stake} lots)")
                return None
            
            print(f"🚀 EXECUTION {direction} {symbol} | Lot: {stake} | Conf: {signal['confidence']:.2f}")
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"❌ Échec {symbol}: {result.comment} ({result.retcode})")
                return None
            
            print(f"✅ SUCCÈS: Ordre #{result.order} exécuté!")
            
            trade_result = {
                'ticket': result.order,
                'symbol': symbol,
                'direction': direction,
                'volume': stake,
                'price': result.price,
                'sl': sl,
                'tp': tp,
                'profile': profile,
                'status': 'EXECUTED',
                'timestamp': datetime.now().isoformat()
            }
            return trade_result
            
        except Exception as e:
            print(f"❌ Erreur critique {symbol}: {e}")
            return None
    
    def get_account_info(self) -> Dict:
        try:
            account_info = mt5.account_info()
            if account_info:
                return { "balance": account_info.balance, "equity": account_info.equity, "margin": account_info.margin }
            return {"balance": 0, "equity": 0, "margin": 0}
        except Exception: return {"balance": 0, "equity": 0, "margin": 0}
    
    def update_performance_stats(self, executed_trades: List[Dict]):
        self.performance_stats['total_trades'] += len(executed_trades)

def run_monster_mind_v2():
    print("""
    🚀 MONSTERMIND V2 - SYSTEME DE TRADING AVANCE
    =============================================
    ⚠️  MODE Move Like GHOST  ⚠️
    =============================================
    """)
    
    try:
        if not initialize_mt5():
            print("❌ Échec critique initialisation MT5")
            return
    except Exception as e:
        print(f"❌ Erreur initialisation MT5: {e}")
        return
    
    try:
        monster_mind = MonsterMindV2()
        trading_engine = AdvancedTradingEngine(monster_mind)
        
        if monster_mind.global_config["DATA_SETTINGS"]["ENABLE_HISTORICAL_ANALYSIS"]:
            monster_mind.run_historical_analysis()
        
        # Période initiale courte pour charger les régimes
        monster_mind.run_initial_analysis_period(5) 
        
        print("🎯 Démarrage de la boucle de trading V2...")
        run_trading_loop(monster_mind, trading_engine)
        
    except KeyboardInterrupt:
        print("\n🛑 Arrêt demandé par l'utilisateur...")
    except Exception as e:
        print(f"\n💥 Erreur critique: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("🧹 Nettoyage et fermeture...")
        try:
            shutdown_mt5()
        except:
            pass

def run_trading_loop(monster_mind: MonsterMindV2, trading_engine: AdvancedTradingEngine):
    """Boucle de trading principale - VERSION TABLEAU DE BORD LIVE"""
    last_report_time = time.time()
    last_data_save = time.time()
    last_analysis_time = time.time()
    
    report_interval = monster_mind.global_config["REPORTING_SETTINGS"]["REPORT_INTERVAL_SEC"]
    data_save_interval = monster_mind.global_config["DATA_SETTINGS"]["DATA_SAVE_INTERVAL_MIN"] * 60
    # Intervalle d'analyse (5 minutes par défaut)
    analysis_interval = 300 
    
    # --- BROADCASTER & AUDITEUR ---
    broadcaster = DataBroadcaster()
    # On initialise l'auditeur pour traquer les fermetures
    auditor = HistoryAuditor(monster_mind.TRADE_LOG_FILE)
    recent_activity = [] # Pour le broadcast des trades
    
    cycle_count = 0
    print(f"\n✅ DÉMARRAGE DU MOTEUR (Seuil Confiance: {monster_mind.global_config['STRATEGY_SETTINGS']['MIN_CONFIDENCE_SCORE']})")

    while True:
        try:
            current_time = time.time()
            cycle_count += 1
            
            # Affichage console minimaliste pour ne pas spammer
            sys.stdout.write(f"\r🔄 Cycle #{cycle_count} | Temps: {datetime.now().strftime('%H:%M:%S')} | Positions: {mt5.positions_total()} | Scan actif... ")
            sys.stdout.flush()
            
            # 1. Exécution et Correction
            executed_trades = trading_engine.execute_trading_cycle()
            
            if executed_trades:
                print("\n" + "!"*50)
                print(f"💰 SUCCÈS ! {len(executed_trades)} trade(s) lancés !")
                for trade in executed_trades:
                    print(f"    👉 {trade['direction']} {trade['symbol']} @ {trade['price']} (Conf: {trade['score']:.2f})")
                
                recent_activity.extend(executed_trades)
                recent_activity = recent_activity[-50:] 
                print("!"*50 + "\n")
            
            # 2. Analyse Périodique (Régimes de marché)
            if current_time - last_analysis_time >= analysis_interval:
                print("\n\n🔍 --- ANALYSE PÉRIODIQUE DU MARCHÉ ---")
                analysis = trading_engine.analyze_current_market()
                print("📊 Régimes détectés:")
                regime_data = []
                for sym, data in analysis.items():
                    if 'error' not in data:
                        regime = data['regime'].get('composite_regime', 'N/A')
                        regime_data.append((sym, regime))
                
                # Affichage trié ou filtré
                for sym, regime in sorted(regime_data, key=lambda x: x[0]):
                    print(f"    🔹 {sym}: {regime}")
                print("--------------------------------------\n")
                last_analysis_time = current_time
            
            # 3. Sauvegarde & Audit des fermetures
            auditor.scan_and_log() # On cherche les trades fermés

            if current_time - last_data_save >= data_save_interval:
                try:
                    monster_mind.adaptive_system.save_session_data()
                    print("\n💾 Sauvegarde automatique des données adaptatives effectuée")
                    last_data_save = current_time
                except Exception: pass
            
            # 4. Rapport détaillé
            if current_time - last_report_time >= report_interval:
                generate_comprehensive_report(monster_mind, trading_engine)
                last_report_time = current_time
            
            # 5. --- BROADCAST LIVE AU DASHBOARD ---
            try:
                positions = mt5.positions_get()
                if positions is None: positions = []
                acc = trading_engine.get_account_info()
                # Envoi des infos compte, positions, et historique des exécutions récentes
                broadcaster.broadcast(acc, positions, recent_activity) 
            except Exception: pass

            time.sleep(monster_mind.SLEEP_SEC)
            
        except KeyboardInterrupt:
            print("\n🛑 Arrêt demandé par l'utilisateur")
            break
        except Exception as e:
            print(f"\n❌ Erreur dans la boucle: {e}")
            time.sleep(5)

def generate_comprehensive_report(monster_mind: MonsterMindV2, trading_engine: AdvancedTradingEngine):
    print("\n" + "="*80)
    print(f"📊 RAPPORT MONSTERMIND V2 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    print("="*80)
    try:
        positions = mt5.positions_get()
        if positions is None: positions = []
        print(f"\n📈 POSITIONS OUVERTES: {len(positions)}")
        
        acc = trading_engine.get_account_info()
        print(f"💰 BALANCE: {acc['balance']:.2f} | EQUITY: {acc['equity']:.2f}")

        if positions:
            total_pl = 0
            for pos in positions:
                profit_loss = pos.profit
                total_pl += profit_loss
                position_age = (time.time() - pos.time) / 60
                # Utiliser le type pour afficher BUY/SELL
                pos_type = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL" 
                print(f"    {pos.ticket} | {pos.symbol} | {pos_type} | {pos.volume} lots | P/L: {profit_loss:.2f} | Âge: {position_age:.1f}min")
            print(f"    TOTAL P/L EN COURS: {total_pl:.2f}")
        
        stats = trading_engine.performance_stats
        print(f"\n🎯 SESSION STATS: {stats['total_trades']} trades exécutés")
        
    except Exception as e:
        print(f"❌ Erreur génération rapport: {e}")
    print("="*80)

if __name__ == "__main__":
    run_monster_mind_v2()