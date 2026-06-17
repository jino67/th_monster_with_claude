"""
MonsterMind V2 - Trading Strategies
Specialized strategies for different market conditions and instruments
"""

from .volatility_strategy import VolatilityStrategy
from .crash_boom_strategy import CrashBoomStrategy
from .jump_strategy import JumpStrategy
from .strategy_optimizer import StrategyOptimizer

__all__ = [
    'VolatilityStrategy',
    'CrashBoomStrategy',
    'JumpStrategy',
    'StrategyOptimizer'
]