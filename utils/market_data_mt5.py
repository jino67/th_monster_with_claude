import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import time
import numpy as np

def initialize_mt5():
    """Initialise la connexion MT5 avec gestion d'erreur améliorée"""
    if not mt5.initialize():
        print("❌ Échec de l'initialisation de MT5")
        return False
    
    print("✅ MT5 initialisé avec succès")
    return True

def shutdown_mt5():
    """Ferme la connexion MT5"""
    mt5.shutdown()
    print("🔌 Connexion MT5 fermée")

def fetch_m1(symbol: str, count: int = 100) -> pd.DataFrame:
    """Récupère les données M1 avec gestion d'erreur avancée"""
    return fetch_timeframe_data(symbol, mt5.TIMEFRAME_M1, count)

def fetch_m5(symbol: str, count: int = 100) -> pd.DataFrame:
    """Récupère les données M5"""
    return fetch_timeframe_data(symbol, mt5.TIMEFRAME_M5, count)

def fetch_m15(symbol: str, count: int = 100) -> pd.DataFrame:
    """Récupère les données M15"""
    return fetch_timeframe_data(symbol, mt5.TIMEFRAME_M15, count)

def fetch_h1(symbol: str, count: int = 50) -> pd.DataFrame:
    """Récupère les données H1 (NOUVEAU en V2)"""
    return fetch_timeframe_data(symbol, mt5.TIMEFRAME_H1, count)

def fetch_h4(symbol: str, count: int = 30) -> pd.DataFrame:
    """Récupère les données H4 (NOUVEAU en V2)"""
    return fetch_timeframe_data(symbol, mt5.TIMEFRAME_H4, count)

def fetch_timeframe_data(symbol: str, timeframe: int, count: int) -> pd.DataFrame:
    """Récupère les données d'un timeframe spécifique avec gestion d'erreur"""
    max_retries = 3
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
            
            if rates is None:
                print(f"❌ Aucune donnée pour {symbol} sur {timeframe_to_str(timeframe)}")
                return create_empty_dataframe()
            
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            
            # Validation des données
            if not validate_dataframe(df):
                print(f"⚠️ Données invalides pour {symbol}, tentative {attempt + 1}")
                time.sleep(retry_delay)
                continue
            
            return df
            
        except Exception as e:
            print(f"❌ Erreur récupération données {symbol}: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    
    return create_empty_dataframe()

def timeframe_to_str(timeframe: int) -> str:
    """Convertit un timeframe MT5 en string"""
    tf_map = {
        mt5.TIMEFRAME_M1: "M1",
        mt5.TIMEFRAME_M5: "M5", 
        mt5.TIMEFRAME_M15: "M15",
        mt5.TIMEFRAME_H1: "H1",
        mt5.TIMEFRAME_H4: "H4"
    }
    return tf_map.get(timeframe, "UNKNOWN")

def validate_dataframe(df: pd.DataFrame) -> bool:
    """Valide l'intégrité des données du DataFrame"""
    if df.empty:
        return False
    
    # Vérifie les colonnes requises
    required_columns = ['open', 'high', 'low', 'close']
    if not all(col in df.columns for col in required_columns):
        return False
    
    # Vérifie les valeurs aberrantes
    for col in required_columns:
        if df[col].isnull().any() or (df[col] <= 0).any():
            return False
    
    # Vérifie la cohérence high >= low
    if (df['high'] < df['low']).any():
        return False
    
    # Vérifie la cohérence des prix
    if ((df['close'] < df['low']) | (df['close'] > df['high'])).any():
        return False
    
    return True

def create_empty_dataframe() -> pd.DataFrame:
    """Crée un DataFrame vide avec la structure attendue"""
    return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume'])

def get_symbol_info(symbol: str) -> Dict:
    """Récupère les informations détaillées d'un symbole"""
    try:
        info = mt5.symbol_info(symbol)
        if info is None:
            return {}
        
        return {
            'name': symbol,
            'point': info.point,
            'digits': info.digits,
            'trade_mode': info.trade_mode,
            'trade_stops_level': info.trade_stops_level,
            'trade_freeze_level': info.trade_freeze_level,
            'volume_min': info.volume_min,
            'volume_max': info.volume_max,
            'volume_step': info.volume_step,
            'margin_initial': info.margin_initial,
            'swap_mode': info.swap_mode
        }
    except Exception as e:
        print(f"❌ Erreur récupération info symbole {symbol}: {e}")
        return {}

def get_current_tick(symbol: str) -> Dict:
    """Récupère le tick actuel d'un symbole"""
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {}
        
        return {
            'time': pd.to_datetime(tick.time, unit='s'),
            'bid': tick.bid,
            'ask': tick.ask,
            'last': tick.last,
            'volume': tick.volume
        }
    except Exception as e:
        print(f"❌ Erreur récupération tick {symbol}: {e}")
        return {}

def check_market_hours(symbol: str) -> Dict:
    """Vérifie les heures de marché pour un symbole"""
    try:
        info = mt5.symbol_info(symbol)
        if info is None:
            return {'market_open': False, 'reason': 'Symbol not found'}
        
        # Vérification basique de la disponibilité
        if info.visible and info.trade_mode == 0:  # Trade mode full
            return {'market_open': True, 'session': 'Unknown'}
        else:
            return {'market_open': False, 'reason': 'Trading not allowed'}
            
    except Exception as e:
        return {'market_open': False, 'reason': f'Error: {str(e)}'}

# Nouveautés V2
def fetch_multiple_timeframes(symbol: str, timeframes: List[int]) -> Dict[str, pd.DataFrame]:
    """Récupère les données de plusieurs timeframes simultanément"""
    data = {}
    for tf in timeframes:
        data[timeframe_to_str(tf)] = fetch_timeframe_data(symbol, tf, 100)
    return data

def get_historical_volatility(symbol: str, period: int = 20, timeframe: int = mt5.TIMEFRAME_H1) -> float:
    """Calcule la volatilité historique"""
    try:
        df = fetch_timeframe_data(symbol, timeframe, period * 2)
        if df.empty:
            return 0.0
        
        returns = df['close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252)  # Volatilité annualisée
        return volatility * 100  # En pourcentage
        
    except Exception as e:
        print(f"❌ Erreur calcul volatilité {symbol}: {e}")
        return 0.0