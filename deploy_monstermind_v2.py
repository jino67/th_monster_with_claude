import os
import shutil
from pathlib import Path

def create_project_structure():
    """Crée la structure complète des dossiers MonsterMind V2"""
    
    base_dirs = [
        "MonsterMind_V2",
        "MonsterMind_V2/data_historical/raw_data",
        "MonsterMind_V2/data_historical/processed_data", 
        "MonsterMind_V2/data_historical/market_regimes",
        "MonsterMind_V2/core",
        "MonsterMind_V2/strategies",
        "MonsterMind_V2/config",
        "MonsterMind_V2/analysis",
        "MonsterMind_V2/main",
        "MonsterMind_V2/utils",
        "MonsterMind_V2/logs",
        "MonsterMind_V2/reports",
        "MonsterMind_V2/backtests"
    ]
    
    print("📁 Création de la structure de dossiers...")
    
    for directory in base_dirs:
        os.makedirs(directory, exist_ok=True)
        print(f"✅ {directory}")
    
    print("🎯 Structure de dossiers créée avec succès!")

def create_all_files():
    """Crée tous les fichiers du projet"""
    
    # Liste de tous les fichiers à créer
    files_structure = {
        # Core
        "core/__init__.py": "",
        "core/historical_miner.py": "",
        "core/advanced_indicators.py": "", 
        "core/market_regime_detector.py": "",
        "core/multi_timeframe_engine.py": "",
        "core/pattern_learner.py": "",
        
        # Strategies
        "strategies/__init__.py": "",
        "strategies/volatility_strategy.py": "",
        "strategies/crash_boom_strategy.py": "",
        "strategies/jump_strategy.py": "",
        "strategies/strategy_optimizer.py": "",
        
        # Config
        "config/config_symbols_v2.json": "",
        "config/config_global_v2.json": "",
        "config/market_regimes_config.json": "",
        
        # Analysis
        "analysis/__init__.py": "",
        "analysis/backtest_engine.py": "",
        "analysis/performance_analyzer.py": "",
        "analysis/correlation_analyzer.py": "",
        
        # Main
        "main/__init__.py": "",
        "main/monster_mind_v2.py": "",
        "main/adaptive_system_v2.py": "",
        "main/position_corrector_v2.py": "",
        
        # Utils
        "utils/__init__.py": "",
        "utils/market_data_mt5.py": "",
        "utils/risk_manager_mt5.py": "",
        "utils/reporter.py": "",
        "utils/mt5_initializer.py": "",
        
        # Root
        "requirements.txt": "",
        "README.md": "",
        "main.py": ""
    }
    
    print("📄 Création des fichiers...")
    
    for file_path, content in files_structure.items():
        full_path = f"MonsterMind_V2/{file_path}"
        
        # Crée le fichier
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ {file_path}")
    
    print("🎯 Tous les fichiers créés!")

if __name__ == "__main__":
    print("🚀 DÉPLOIEMENT MONSTERMIND V2")
    print("=" * 50)
    
    create_project_structure()
    create_all_files()
    
    print("\n" + "=" * 50)
    print("✅ DÉPLOIEMENT TERMINÉ !")
    print("📁 Structure: MonsterMind_V2/")
    print("🎯 Prochaines étapes:")
    print("   1. Copier le code dans les fichiers")
    print("   2. Installer les dépendances: pip install -r requirements.txt")
    print("   3. Lancer: python main.py")