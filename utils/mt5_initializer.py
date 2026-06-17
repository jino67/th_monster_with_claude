import MetaTrader5 as mt5
import time
from typing import Dict, Optional
import json
import os

def initialize_mt5_v2(use_saved_credentials: bool = True) -> Dict:
    """
    Initialise MT5 avec gestion sécurisée des identifiants - VERSION CORRIGÉE
    """
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            print(f"🔧 Tentative de connexion MT5 ({attempt + 1}/{max_retries})...")
            
            # Arrêt propre si déjà connecté
            if mt5.initialize():
                mt5.shutdown()
                time.sleep(1)
            
            # Récupération des identifiants - VERSION SIMPLIFIÉE
            connection_params = get_connection_params_safe(use_saved_credentials)
            
            # Paramètres de connexion
            login_params = {
                "timeout": 30000,  # 30 secondes
                "pipeline": True
            }
            
            # Ajout des identifiants si fournis
            if connection_params and connection_params.get('account_number'):
                login_params.update({
                    "login": connection_params['account_number'],
                    "password": connection_params['password'],
                    "server": connection_params['server']
                })
            else:
                print("🔧 Utilisation du compte MT5 par défaut")
            
            # Initialisation
            if not mt5.initialize(**login_params):
                error_code = mt5.last_error()
                error_desc = get_error_description(error_code)
                print(f"❌ Échec initialisation MT5: {error_desc}")
                
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                else:
                    return {
                        'success': False,
                        'error_code': error_code,
                        'error_description': error_desc
                    }
            
            # Vérification de la connexion
            if not mt5.terminal_info():
                print("❌ Terminal non accessible")
                mt5.shutdown()
                
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                else:
                    return {
                        'success': False,
                        'error_code': -1,
                        'error_description': 'Terminal not accessible'
                    }
            
            # Connexion réussie
            account_info = mt5.account_info()
            terminal_info = mt5.terminal_info()
            
            connection_info = {
                'success': True,
                'account_number': account_info.login if account_info else 'Unknown',
                'balance': account_info.balance if account_info else 0,
                'server': account_info.server if account_info else 'Unknown',
                'terminal_version': getattr(terminal_info, 'version', 'Unknown') if terminal_info else 'Unknown',
                'connected_since': time.time()
            }
            
            print("✅ MT5 initialisé avec succès!")
            print(f"   Compte: {connection_info['account_number']}")
            print(f"   Serveur: {connection_info['server']}")
            print(f"   Balance: ${connection_info['balance']:.2f}")
            print(f"   Terminal: {connection_info['terminal_version']}")
            
            return connection_info
            
        except Exception as e:
            print(f"❌ Exception lors de l'initialisation: {e}")
            
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                return {
                    'success': False,
                    'error_code': -1,
                    'error_description': f'Exception: {str(e)}'
                }
    
    return {
        'success': False,
        'error_code': -1,
        'error_description': 'Max retries exceeded'
    }

def get_connection_params_safe(use_saved_credentials: bool = True) -> Optional[Dict]:
    """Récupère les paramètres de connexion de manière sécurisée"""
    try:
        if not use_saved_credentials:
            return None
            
        # Essayer d'importer security_manager de manière sécurisée
        try:
            # Ajout du chemin config
            import sys
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            config_path = os.path.join(project_root, 'config')
            
            if config_path not in sys.path:
                sys.path.insert(0, config_path)
            
            from security_manager import security_manager
            
            if security_manager and hasattr(security_manager, 'get_connection_params'):
                return security_manager.get_connection_params()
            else:
                print("⚠️  security_manager non disponible")
                return None
                
        except ImportError as e:
            print(f"⚠️  Impossible d'importer security_manager: {e}")
            return None
            
    except Exception as e:
        print(f"❌ Erreur récupération paramètres connexion: {e}")
        return None

def get_error_description(error_code: int) -> str:
    """Retourne la description d'une erreur MT5"""
    error_descriptions = {
        1: "Generic error",
        2: "Invalid parameters", 
        3: "Trade server not available",
        6: "No connection with trade server",
        64: "Account disabled",
        65: "Invalid account",
        133: "Trade is disabled",
        134: "Not enough money",
        135: "Price changed",
        136: "Off quotes",
        137: "Broker is busy", 
        138: "Requote",
        139: "Order is locked",
        140: "Long positions only allowed",
        141: "Too many requests",
        145: "Modification denied because order is too close to market",
        146: "Trade context is busy",
        147: "Expirations are denied by broker", 
        148: "Too many pending orders",
        149: "Hedging is prohibited",
        150: "Prohibited by FIFO rules"
    }
    
    return error_descriptions.get(abs(error_code), f"Unknown error: {error_code}")

# Fonctions legacy pour la compatibilité
def initialize_mt5():
    """Fonction legacy pour la compatibilité"""
    result = initialize_mt5_v2()
    return result['success']

def shutdown_mt5():
    """Ferme la connexion MT5"""
    try:
        mt5.shutdown()
        print("🔌 Connexion MT5 fermée avec succès")
        return True
    except Exception as e:
        print(f"❌ Erreur lors de la fermeture MT5: {e}")
        return False