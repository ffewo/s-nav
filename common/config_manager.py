import json
import os
import logging
from typing import Dict, Any, Optional

class ConfigManager:

    
    def __init__(self, config_file: str = "config/config.json"):
        self.config_file = config_file
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Konfigürasyon dosyasını yükle"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                logging.info(f"Konfigürasyon yüklendi: {self.config_file}")
                return config
            else:
                logging.warning(f"Konfigürasyon dosyası bulunamadı: {self.config_file}")
                return self._get_default_config()
        except Exception as e:
            logging.error(f"Konfigürasyon yükleme hatası: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:

        return {
            "server": {
                "host": "0.0.0.0",
                "port": 2121,
                "data_port_min": 49152,
                "data_port_max": 65535,
                "max_connections": 50,
                "buffer_size": 65536,  
                "heartbeat_interval": 30,
                "connection_timeout": 300,
                "max_file_size_mb": 50
            },
            "client": {
                "server_ip": "127.0.0.1",
                "reconnect_attempts": 5,
                "reconnect_delay": 3,
                "heartbeat_interval": 30
            },
            "security": {
                "banned_applications": [
                    "chrome.exe", "firefox.exe", "msedge.exe", "opera.exe"
                ],
                "allowed_file_extensions": [
                    ".pdf", ".doc", ".docx", ".txt", ".rtf",
                    ".jpg", ".jpeg", ".png", ".gif",
                    ".zip", ".rar", ".7z"
                ]
            },
            "exam": {
                "default_duration_minutes": 120,
                "warning_time_minutes": 10,
                "auto_submit_on_time_up": True,
                "allow_multiple_submissions": False
            },
            "logging": {
                "level": "INFO",
                "max_log_size_mb": 10,
                "backup_count": 5
            },
            "ui": {
                "window_width": 900,
                "window_height": 600,
                "theme": "default",
                "font_family": "Arial",
                "font_size": 10
            }
        }
    
    def get(self, key_path: str, default: Any = None) -> Any:

        try:
            keys = key_path.split('.')
            value = self.config
            
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return default
                    
            return value
        except Exception as e:
            logging.error(f"Konfigürasyon okuma hatası ({key_path}): {e}")
            return default
    
    

# Global konfigürasyon instance'ı
_config_instance = None

def get_config() -> ConfigManager:
    """Global konfigürasyon instance'ını al"""
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigManager()
    return _config_instance

