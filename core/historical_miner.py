import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, timedelta
import json
import os
from typing import Dict, List, Optional
import time

class HistoricalDataMiner:
    def __init__(self):
        self.data_dir = "data_historical"
        self.raw_dir = os.path.join(self.data_dir, "raw_data")
        self.processed_dir = os.path.join(self.data_dir, "processed_data")
        self.regimes_dir = os.path.join(self.data_dir, "market_regimes")
        self._ensure_directories()
        
        self.timeframes = {
            'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'M15': mt5.TIMEFRAME_M15,
            'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4, 'D1': mt5.TIMEFRAME_D1
        }
        
        # Compteurs pour affichage optimisé
        self.symbols_processed = 0
        self.total_symbols = 0
        
    def _ensure_directories(self):
        """Crée les répertoires nécessaires"""
        for directory in [self.data_dir, self.raw_dir, self.processed_dir, self.regimes_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)

    def collect_comprehensive_data(self, symbols: List[str], start_date: str = "2015-01-01"):
        """Collecte les données OHLCV avec affichage optimisé"""
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.now()
        self.total_symbols = len(symbols)
        self.symbols_processed = 0
        
        print(f"🚀 COLLECTE HISTORIQUE OPTIMISÉE")
        print(f"📊 {self.total_symbols} symboles | 📅 Depuis {start_date}")
        print("=" * 60)
        
        for symbol in symbols:
            self.symbols_processed += 1
            print(f"\n[{self.symbols_processed}/{self.total_symbols}] {symbol}")
            
            for tf_name, tf_value in self.timeframes.items():
                try:
                    latest_existing = self.get_latest_timestamp(symbol, tf_name)
                    
                    if latest_existing:
                        collect_start = latest_existing + timedelta(minutes=1)
                        status = "🔄 Mise à jour"
                    else:
                        collect_start = start_dt
                        status = "📥 Première collecte"
                    
                    if collect_start >= end_dt:
                        print(f"   ✅ {tf_name}: Déjà à jour")
                        continue
                    
                    new_data = self.collect_timeframe_data(symbol, tf_value, collect_start, end_dt, tf_name)
                    
                    if new_data is not None and len(new_data) > 0:
                        self.merge_and_save_data(symbol, tf_name, new_data)
                        self.process_symbol_data(symbol, tf_name)
                    else:
                        print(f"   ℹ️  {tf_name}: Aucune nouvelle donnée")
                        
                except Exception as e:
                    print(f"   ❌ {tf_name}: {str(e)[:50]}...")
        
        print("=" * 60)
        print("✅ COLLECTE TERMINÉE AVEC SUCCÈS")

    def collect_timeframe_data(self, symbol: str, timeframe: int, start_dt: datetime, end_dt: datetime, tf_name: str) -> Optional[pd.DataFrame]:
        """Collecte les données avec affichage minimal"""
        current_date = start_dt
        all_data = []
        segment_days = self.get_segment_size(tf_name)
        
        segments_collected = 0
        total_candles = 0
        
        while current_date < end_dt:
            segment_end = current_date + timedelta(days=segment_days)
            if segment_end > end_dt:
                segment_end = end_dt
                
            try:
                rates = mt5.copy_rates_range(symbol, timeframe, current_date, segment_end)
                
                if rates is not None and len(rates) > 0:
                    df = pd.DataFrame(rates)
                    df['time'] = pd.to_datetime(df['time'], unit='s')
                    all_data.append(df)
                    segments_collected += 1
                    total_candles += len(df)
                    
            except Exception:
                pass  # Silence les erreurs de segments
            
            current_date = segment_end + timedelta(days=1)
            time.sleep(0.02)
        
        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            final_df.sort_values('time', inplace=True)
            final_df.drop_duplicates(subset=['time'], inplace=True)
            
            print(f"   ✅ {tf_name}: {len(final_df)} bougies ({segments_collected} segments)")
            return final_df
        
        return None

    def get_segment_size(self, timeframe: str) -> int:
        """Retourne la taille optimale des segments"""
        return {
            'M1': 7, 'M5': 14, 'M15': 30, 
            'H1': 60, 'H4': 90, 'D1': 180
        }.get(timeframe, 30)

    def merge_and_save_data(self, symbol: str, timeframe: str, new_data: pd.DataFrame):
        """Fusionne et sauvegarde les données"""
        filename = f"{symbol}_{timeframe}_2015_present.csv"
        filepath = os.path.join(self.raw_dir, filename)
        
        if os.path.exists(filepath):
            try:
                existing_data = pd.read_csv(filepath)
                existing_data['time'] = pd.to_datetime(existing_data['time'])
                
                merged_data = pd.concat([existing_data, new_data], ignore_index=True)
                merged_data.sort_values('time', inplace=True)
                merged_data.drop_duplicates(subset=['time'], keep='last', inplace=True)
                
            except Exception:
                merged_data = new_data
        else:
            merged_data = new_data
        
        merged_data.to_csv(filepath, index=False)

    def get_latest_timestamp(self, symbol: str, timeframe: str) -> Optional[datetime]:
        """Récupère le timestamp le plus récent"""
        filename = f"{symbol}_{timeframe}_2015_present.csv"
        filepath = os.path.join(self.raw_dir, filename)
        
        if os.path.exists(filepath):
            try:
                df = pd.read_csv(filepath, usecols=['time'])
                if not df.empty:
                    return pd.to_datetime(df['time'].iloc[-1])
            except Exception:
                pass
        return None

    def process_symbol_data(self, symbol: str, timeframe: str):
        """Traite les données avec indicateurs techniques"""
        try:
            if timeframe in ['H1', 'H4', 'D1']:
                return
            
            filename = f"{symbol}_{timeframe}_2015_present.csv"
            filepath = os.path.join(self.raw_dir, filename)
            
            if not os.path.exists(filepath):
                return
            
            df = pd.read_csv(filepath)
            df['time'] = pd.to_datetime(df['time'])
            
            processed_filename = f"{symbol}_{timeframe}_processed.csv"
            processed_filepath = os.path.join(self.processed_dir, processed_filename)
            
            if os.path.exists(processed_filepath):
                processed_df = pd.read_csv(processed_filepath)
                processed_df['time'] = pd.to_datetime(processed_df['time'])
                
                latest_processed = processed_df['time'].max()
                new_data = df[df['time'] > latest_processed]
                
                if len(new_data) == 0:
                    return
                
                if len(new_data) > 100:
                    new_data = new_data.tail(100)
                
                df_to_process = pd.concat([processed_df, new_data], ignore_index=True)
            else:
                df_to_process = df.tail(1000)
            
            df_to_process = self.calculate_technical_indicators(df_to_process)
            df_to_process.to_csv(processed_filepath, index=False)
            
            self.analyze_market_regimes(symbol, timeframe, df_to_process.tail(500))
            
        except Exception:
            pass  # Silence les erreurs de traitement

    def calculate_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcule les indicateurs techniques"""
        df = df.copy()
        
        # Indicateurs de base
        df['returns'] = df['close'].pct_change()
        df['volatility_20'] = df['returns'].rolling(20).std()
        
        # RSI
        df['rsi_14'] = self.calculate_rsi(df['close'], 14)
        
        # MACD
        df['macd'], df['macd_signal'], df['macd_hist'] = self.calculate_macd(df['close'])
        
        # ATR
        df['atr_14'] = self.calculate_atr(df, 14)
        
        # Moyennes mobiles
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_50'] = df['close'].rolling(50).mean()
        
        return df

    # ... [Gardez les mêmes méthodes calculate_rsi, calculate_macd, calculate_atr] ...

    def analyze_market_regimes(self, symbol: str, timeframe: str, df: pd.DataFrame):
        """Analyse des régimes de marché simplifiée"""
        try:
            regimes = []
            df['returns'] = df['close'].pct_change()
            df['volatility'] = df['returns'].rolling(20).std()
            
            for i in range(50, len(df)):
                current_vol = df['volatility'].iloc[i]
                avg_vol = df['volatility'].iloc[i-50:i].mean()
                
                if current_vol > avg_vol * 1.5:
                    regime_type = "HIGH_VOL"
                elif current_vol < avg_vol * 0.7:
                    regime_type = "LOW_VOL"
                else:
                    regime_type = "NORMAL"
                
                regimes.append({
                    'timestamp': df['time'].iloc[i],
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'regime': regime_type
                })
            
            if regimes:
                regimes_df = pd.DataFrame(regimes)
                filename = f"{symbol}_{timeframe}_regimes.csv"
                filepath = os.path.join(self.regimes_dir, filename)
                regimes_df.to_csv(filepath, index=False)
                
        except Exception:
            pass

    def quick_data_check(self, symbols: List[str]):
        """Vérification rapide et propre des données"""
        print("\n🔍 ÉTAT DES DONNÉES")
        print("=" * 50)
        
        for symbol in symbols:
            print(f"\n{symbol}:")
            for tf_name in ['M1', 'M5', 'M15', 'H1']:
                filename = f"{symbol}_{tf_name}_2015_present.csv"
                filepath = os.path.join(self.raw_dir, filename)
                
                if os.path.exists(filepath):
                    size_mb = os.path.getsize(filepath) / (1024 * 1024)
                    status = f"{size_mb:.1f} MB"
                    print(f"   {tf_name}: {status}")
                else:
                    print(f"   {tf_name}: ❌ MANQUANT")
        
        print("=" * 50)

    def generate_market_insights(self, symbols: List[str]):
        """Génère des insights stratégiques"""
        insights = {}
        
        for symbol in symbols:
            symbol_insights = {'best_timeframes': {}}
            
            for timeframe in ['M15', 'H1', 'H4']:
                try:
                    filename = f"{symbol}_{timeframe}_regimes.csv"
                    filepath = os.path.join(self.regimes_dir, filename)
                    
                    if os.path.exists(filepath):
                        df = pd.read_csv(filepath)
                        regime_performance = df.groupby('regime').size()
                        best_regime = regime_performance.idxmax() if not regime_performance.empty else "UNKNOWN"
                        
                        symbol_insights['best_timeframes'][timeframe] = {
                            'dominant_regime': best_regime,
                            'recommended_strategy': self.get_recommended_strategy(best_regime)
                        }
                        
                except Exception:
                    pass
            
            insights[symbol] = symbol_insights
        
        insights_file = os.path.join(self.data_dir, "market_insights.json")
        with open(insights_file, 'w', encoding='utf-8') as f:
            json.dump(insights, f, indent=2, ensure_ascii=False)
        
        print("🎯 INSIGHTS STRATÉGIQUES GÉNÉRÉS")
        return insights
    
    def get_recommended_strategy(self, regime: str) -> str:
        """Retourne la stratégie recommandée"""
        return {
            "HIGH_VOL": "BREAKOUT_MOMENTUM",
            "LOW_VOL": "MEAN_REVERSION", 
            "NORMAL": "ADAPTIVE_MIXED"
        }.get(regime, "ADAPTIVE_MIXED")