import json
import os
import getpass
from typing import Dict, Optional
from pathlib import Path

class SecurityManager:
    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.credentials_file = os.path.join(config_dir, "credentials.json")
        self._ensure_config_dir()
    
    def _ensure_config_dir(self):
        """Crée le dossier config s'il n'existe pas"""
        Path(self.config_dir).mkdir(exist_ok=True)
    
    def setup_credentials(self) -> Dict:
        """Configure les identifiants de manière sécurisée"""
        print("\n🔐 CONFIGURATION DES IDENTIFIANTS MT5")
        print("=" * 40)
        
        # Demande interactive
        account_number = input("Numéro de compte MT5: ").strip()
        password = getpass.getpass("Mot de passe MT5: ")
        server = input("Serveur MT5: ").strip()
        
        if not server:
            server = "DefaultServer"
            print("⚠️  Utilisation du serveur par défaut")
        
        credentials = {
            'account_number': int(account_number),
            'password': password,
            'server': server,
            'configured': True,
            'first_setup': True
        }
        
        # Sauvegarde
        self._save_credentials(credentials)
        
        print("✅ Identifiants configurés avec succès!")
        return credentials
    
    def _save_credentials(self, credentials: Dict):
        """Sauvegarde les identifiants"""
        try:
            with open(self.credentials_file, 'w', encoding='utf-8') as f:
                json.dump(credentials, f, indent=2)
            
            # Sécurité basique
            os.chmod(self.credentials_file, 0o600)
            
        except Exception as e:
            print(f"❌ Erreur sauvegarde identifiants: {e}")
    
    def load_credentials(self) -> Optional[Dict]:
        """Charge les identifiants"""
        if not os.path.exists(self.credentials_file):
            return None
        
        try:
            with open(self.credentials_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Erreur chargement identifiants: {e}")
            return None
    
    def check_credentials_setup(self) -> bool:
        """Vérifie si les identifiants sont configurés"""
        credentials = self.load_credentials()
        return credentials is not None and credentials.get('configured', False)
    
    def get_connection_params(self) -> Dict:
        """Retourne les paramètres de connexion"""
        credentials = self.load_credentials()
        
        if not credentials:
            print("❌ Aucun identifiant configuré")
            return self.setup_credentials()
        
        return {
            'account_number': credentials['account_number'],
            'password': credentials['password'],
            'server': credentials['server']
        }

# Instance globale
security_manager = SecurityManager()