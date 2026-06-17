"""Détection des setups Smart Money Concept"""
import pandas as pd

def detect_smc_direction(df, lookback=20):
    """Détection basique de direction SMC"""
    if len(df) < lookback:
        return "SIDEWAYS"
    
    highs = df['high'].tail(lookback)
    lows = df['low'].tail(lookback)
    
    if highs.max() == highs.iloc[-1] and lows.max() == lows.iloc[-1]:
        return "BULLISH"
    elif highs.min() == highs.iloc[-1] and lows.min() == lows.iloc[-1]:
        return "BEARISH"
    else:
        return "SIDEWAYS"

def detect_breakout(df, period=10):
    """Détection de breakout simple"""
    if len(df) < period:
        return False
    
    current_high = df['high'].iloc[-1]
    current_low = df['low'].iloc[-1]
    
    previous_high = df['high'].iloc[-period:-1].max()
    previous_low = df['low'].iloc[-period:-1].min()
    
    if current_high > previous_high:
        return "BULLISH_BREAKOUT"
    elif current_low < previous_low:
        return "BEARISH_BREAKOUT"
    else:
        return "NO_BREAKOUT"