import MetaTrader5 as mt5
import pandas as pd
from typing import Dict, List, Optional, Tuple
import numpy as np

def calculate_stake(balance: float, symbol: str, risk_mode: str, risk_value: float,
                   atr: float, atr_multiplier: float, verbose: bool = False) -> float:
    """
    Fonction de compatibilité - utilise calculate_stake_v2 avec paramètres par défaut
    """
    return calculate_stake_v2(
        balance=balance,
        symbol=symbol,
        risk_mode=risk_mode,
        risk_value=risk_value,
        atr=atr,
        atr_multiplier=atr_multiplier,
        volatility_regime="NORMAL",
        adaptive_multiplier=1.0,
        verbose=verbose
    )

def calculate_stake_v2(balance: float, symbol: str, risk_mode: str, risk_value: float,
                      atr: float, atr_multiplier: float, volatility_regime: str = "NORMAL",
                      adaptive_multiplier: float = 1.0, verbose: bool = False) -> float:
    """
    Calcule le volume V2 avec gestion de risk avancée
    """
    # Validation des entrées
    if balance <= 0 or atr <= 0 or atr_multiplier <= 0:
        if verbose:
            print("❌ Paramètres invalides pour le calcul du volume")
        return 0.0
    
    # Récupération des infos symbole
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        if verbose:
            print(f"❌ Impossible de récupérer les infos pour {symbol}")
        return 0.0
    
    # Calcul du risk amount
    if risk_mode == "fixed":
        risk_amount = risk_value
    elif risk_mode == "percent":
        risk_amount = balance * (risk_value / 100)
    else:
        if verbose:
            print(f"❌ Mode de risk inconnu: {risk_mode}")
        return 0.0
    
    # Ajustement selon la volatilité
    volatility_adjustment = get_volatility_adjustment(volatility_regime)
    risk_amount *= volatility_adjustment
    
    # Ajustement adaptatif
    risk_amount *= adaptive_multiplier
    
    # Calcul de la distance SL en points
    point_value = symbol_info.point
    sl_distance_points = (atr * atr_multiplier) / point_value
    
    if sl_distance_points <= 0:
        if verbose:
            print("❌ Distance SL invalide")
        return 0.0
    
    # Calcul du volume
    try:
        tick_value = get_tick_value(symbol, symbol_info)
        volume = risk_amount / (sl_distance_points * tick_value)
        
        # Arrondi et validation
        volume = round_volume(volume, symbol_info)
        volume = validate_volume(volume, symbol_info, balance)
        
        if verbose:
            print(f"📐 Volume V2: {volume:.2f} lots | Risk: ${risk_amount:.2f}")
            print(f"   ATR: {atr:.5f} | Multiplier: {atr_multiplier}")
            print(f"   Volatility: {volatility_regime} | Adjustment: {volatility_adjustment}")
        
        return volume
        
    except Exception as e:
        if verbose:
            print(f"❌ Erreur calcul volume: {e}")
        return 0.0

def get_volatility_adjustment(volatility_regime: str) -> float:
    """Retourne le multiplicateur de risk selon la volatilité"""
    adjustments = {
        "EXTREME_HIGH_VOL": 0.4,
        "HIGH_VOL": 0.6,
        "NORMAL_VOL": 1.0,
        "LOW_VOL": 1.2,
        "EXTREME_LOW_VOL": 1.5
    }
    return adjustments.get(volatility_regime, 1.0)

def get_tick_value(symbol: str, symbol_info) -> float:
    """Calcule la valeur d'un tick"""
    try:
        # Essaye de récupérer la valeur du tick de profit
        if hasattr(symbol_info, 'trade_tick_value_profit') and symbol_info.trade_tick_value_profit > 0:
            return symbol_info.trade_tick_value_profit
        
        # Fallback: calcul basé sur le contrat size
        contract_size = getattr(symbol_info, 'trade_contract_size', 100000)
        tick_size = getattr(symbol_info, 'trade_tick_size', 0.00001)
        
        return (contract_size * tick_size) / 10  # Approximation
        
    except Exception:
        return 1.0  # Valeur par défaut

def round_volume(volume: float, symbol_info) -> float:
    """Arrondit le volume selon les règles du symbole"""
    try:
        min_volume = symbol_info.volume_min
        max_volume = symbol_info.volume_max
        step_volume = symbol_info.volume_step
        
        # Arrondi au step le plus proche
        if step_volume > 0:
            volume = round(volume / step_volume) * step_volume
        
        # Respect des limites
        volume = max(min_volume, min(volume, max_volume))
        
        return round(volume, 2)
        
    except Exception:
        return round(volume, 2)

def validate_volume(volume: float, symbol_info, balance: float) -> float:
    """Valide le volume par rapport aux contraintes"""
    try:
        # Vérification marge disponible
        required_margin = calculate_required_margin(volume, symbol_info)
        if required_margin > balance * 0.8:  # Max 80% de la balance
            volume = (balance * 0.8) / required_margin * volume
        
        return volume
        
    except Exception:
        return volume

def calculate_required_margin(volume: float, symbol_info) -> float:
    """Calcule la marge requise"""
    try:
        if hasattr(symbol_info, 'margin_initial') and symbol_info.margin_initial > 0:
            return volume * symbol_info.margin_initial
        else:
            # Fallback: estimation basée sur le contract size
            contract_size = getattr(symbol_info, 'trade_contract_size', 100000)
            return volume * contract_size * 0.01  # 1% de marge
            
    except Exception:
        return volume * 1000  # Estimation conservative

def calculate_position_risk(positions: List) -> Dict:
    """Calcule le risk global du portefeuille"""
    total_risk = 0
    symbol_risk = {}
    
    for position in positions:
        symbol = position.symbol
        current_risk = calculate_single_position_risk(position)
        total_risk += current_risk
        
        if symbol not in symbol_risk:
            symbol_risk[symbol] = 0
        symbol_risk[symbol] += current_risk
    
    return {
        'total_risk': total_risk,
        'symbol_risk': symbol_risk,
        'risk_concentration': calculate_risk_concentration(symbol_risk),
        'diversification_score': calculate_diversification_score(symbol_risk)
    }

def calculate_single_position_risk(position) -> float:
    """Calcule le risk d'une position individuelle"""
    try:
        # Risk basé sur la distance au SL
        if position.sl > 0:
            if position.type == mt5.ORDER_TYPE_BUY:
                risk_distance = position.price_open - position.sl
            else:
                risk_distance = position.sl - position.price_open
            
            risk_amount = risk_distance * position.volume * get_tick_value(position.symbol, mt5.symbol_info(position.symbol))
            return risk_amount
        else:
            # Estimation basée sur l'ATR
            return position.volume * 100  # Estimation conservative
            
    except Exception:
        return 0

def calculate_risk_concentration(symbol_risk: Dict) -> float:
    """Calcule la concentration du risk"""
    if not symbol_risk:
        return 0.0
    
    total_risk = sum(symbol_risk.values())
    max_risk = max(symbol_risk.values())
    
    return max_risk / total_risk if total_risk > 0 else 0.0

def calculate_diversification_score(symbol_risk: Dict) -> float:
    """Calcule un score de diversification"""
    if not symbol_risk or len(symbol_risk) == 0:
        return 0.0
    
    if len(symbol_risk) == 1:
        return 0.0
    
    total_risk = sum(symbol_risk.values())
    perfect_distribution = total_risk / len(symbol_risk)
    
    # Écart par rapport à la distribution parfaite
    divergence = sum(abs(risk - perfect_distribution) for risk in symbol_risk.values())
    max_divergence = total_risk * (1 - 1/len(symbol_risk))
    
    score = 1 - (divergence / max_divergence) if max_divergence > 0 else 0.0
    return max(0.0, min(score, 1.0))

def get_dynamic_sl_tp(symbol: str, direction: str, atr: float, 
                     rr_ratio: float, volatility_regime: str) -> Tuple[float, float]:
    """Calcule les niveaux SL/TP dynamiques"""
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return 0, 0
        
        current_price = tick.ask if direction == "bullish" else tick.bid
        
        # Ajustement de l'ATR selon la volatilité
        atr_multiplier = get_atr_multiplier(volatility_regime)
        adjusted_atr = atr * atr_multiplier
        
        if direction == "bullish":
            sl = current_price - adjusted_atr
            tp = current_price + (adjusted_atr * rr_ratio)
        else:
            sl = current_price + adjusted_atr
            tp = current_price - (adjusted_atr * rr_ratio)
        
        return sl, tp
        
    except Exception as e:
        print(f"❌ Erreur calcul SL/TP: {e}")
        return 0, 0

def get_atr_multiplier(volatility_regime: str) -> float:
    """Retourne le multiplicateur ATR selon la volatilité"""
    multipliers = {
        "EXTREME_HIGH_VOL": 2.0,
        "HIGH_VOL": 1.5,
        "NORMAL_VOL": 1.0,
        "LOW_VOL": 0.8,
        "EXTREME_LOW_VOL": 0.6
    }
    return multipliers.get(volatility_regime, 1.0)