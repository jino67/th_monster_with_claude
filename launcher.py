"""
MONSTERMIND V2 - SYSTEME DE TRADING AVANCE
"""

import sys
import os
import logging
from datetime import datetime

# Configuration robuste du path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

def setup_logging():
    """Configure le système de logging"""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f"{log_dir}/monstermind_v2_{datetime.now().strftime('%Y%m%d')}.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )

def check_dependencies():
    """Vérifie les dépendances nécessaires"""
    required_packages = [
        'pandas', 'numpy', 'MetaTrader5', 'ta'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("❌ Packages manquants:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\n📦 Installation: pip install -r requirements.txt")
        return False
    
    return True

def display_banner():
    """Affiche la bannière du système"""
    banner = """
    🚀 MONSTERMIND V2 - SYSTEME DE TRADING AVANCE
    =============================================
    Version: 2.0.0
    Statut: PRÊT PLE TEST
    =============================================
    """
    print(banner)

def setup_credentials():
    """Configure les identifiants MT5"""
    try:
        # Ajout du chemin config
        config_path = os.path.join(current_dir, 'config')
        if config_path not in sys.path:
            sys.path.insert(0, config_path)
            
        from security_manager import security_manager
        
        if not security_manager.check_credentials_setup():
            print("\n🔐 CONFIGURATION REQUISE")
            print("Vous devez configurer vos identifiants MT5 pour continuer.")
            
            response = input("Voulez-vous configurer maintenant? (o/N): ").strip().lower()
            
            if response in ['o', 'oui', 'y', 'yes']:
                security_manager.setup_credentials()
            else:
                print("❌ Configuration annulée. Le système ne peut pas fonctionner sans identifiants.")
                return False
        
        return True
    except ImportError as e:
        print(f"❌ Erreur import security_manager: {e}")
        print("🔧 Utilisation du mode démo sans identifiants MT5")
        return True  # Continue en mode démo

def main():
    """Fonction principale"""
    
    # Configuration
    setup_logging()
    display_banner()
    
    # Vérification des dépendances
    if not check_dependencies():
        sys.exit(1)
    
    print("✅ Toutes les dépendances sont satisfaites")
    
    # Configuration des identifiants
    if not setup_credentials():
        sys.exit(1)
    
    print("🔧 Initialisation du système...")
    
    try:
        # Import des modules V2 - Version corrigée
        try:
            from main.monster_mind_v2 import run_monster_mind_v2
        except ImportError as e:
            print(f"❌ Erreur import principale: {e}")
            print("🔄 Tentative de correction du path...")
            # Ajout explicite du chemin
            sys.path.insert(0, os.path.join(current_dir, 'main'))
            from monster_mind_v2 import run_monster_mind_v2
        
        # Lancement du système principal
        run_monster_mind_v2()
        
    except KeyboardInterrupt:
        print("\n🛑 Arrêt demandé par l'utilisateur")
    except Exception as e:
        print(f"💥 Erreur critique: {e}")
        logging.exception("Erreur lors de l'exécution")
    finally:
        print("🧹 Nettoyage terminé")

if __name__ == "__main__":
    main()