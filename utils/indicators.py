"""Indicateurs techniques de base"""
import pandas as pd
import numpy as np
from typing import Optional

def rsi(series, period=14):
    """Relative Strength Index"""
    if len(series) < period:
        return pd.Series([50] * len(series), index=series.index)
    
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def macd_hist(series, fast=12, slow=26, signal=9):
    """MACD Histogram"""
    if len(series) < slow:
        return pd.Series([0] * len(series), index=series.index)
    
    ema_fast = series.ewm(span=fast).mean()
    ema_slow = series.ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal).mean()
    histogram = macd - signal_line
    return histogram

def in_trend(series, period=20):
    """Détection de tendance simple"""
    if len(series) < period:
        return pd.Series([0] * len(series), index=series.index)
    
    sma = series.rolling(window=period).mean()
    return (series > sma).astype(int)

def atr(close, high, low, period=14):
    """Average True Range"""
    if len(close) < period:
        return pd.Series([0] * len(close), index=close.index)
    
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr.fillna(0)

def adx(high, low, close, period=14):
    """Average Directional Index"""
    if len(close) < period * 2:
        return pd.Series([0] * len(close), index=close.index)
    
    # Calcul simplifié
    plus_dm = high.diff()
    minus_dm = low.diff().abs()
    tr = atr(close, high, low, period)
    
    plus_di = 100 * (plus_dm.rolling(period).mean() / tr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / tr)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(period).mean()
    return adx.fillna(0)

def ichimoku(high, low, close):
    """Ichimoku Cloud simplifié"""
    period9_high = high.rolling(9).max()
    period9_low = low.rolling(9).min()
    tenkan_sen = (period9_high + period9_low) / 2
    
    period26_high = high.rolling(26).max()
    period26_low = low.rolling(26).min()
    kijun_sen = (period26_high + period26_low) / 2
    
    return {
        'tenkan_sen': tenkan_sen,
        'kijun_sen': kijun_sen
    }