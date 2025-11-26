"""
Sınav Sistemi Konfigürasyon Yöneticisi
Bu modül sistem ayarlarını yönetir ve varsayılan değerler sağlar.
"""

import json
import os
import logging
from typing import Dict, Any, Optional

class ConfigManager:
    """Konfigürasyon yönetim sınıfı"""
    
    def __init__(self, config_file: str = "config.json"):
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
        """Varsayılan konfigürasyon değerleri"""
        return {
            "server": {
                "host": "0.0.0.0",
                "port": 2121,
                "max_connections": 50,
                "buffer_size": 4096,
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
        """
        Nokta notasyonu ile konfigürasyon değeri al
        Örnek: get("server.port") -> 2121
        """
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
    
    def set(self, key_path: str, value: Any) -> bool:
        """
        Nokta notasyonu ile konfigürasyon değeri ayarla
        Örnek: set("server.port", 3000)
        """
        try:
            keys = key_path.split('.')
            config_ref = self.config
            
            # Son key hariç tüm key'lere git
            for key in keys[:-1]:
                if key not in config_ref:
                    config_ref[key] = {}
                config_ref = config_ref[key]
            
            # Son key'e değeri ata
            config_ref[keys[-1]] = value
            return True
            
        except Exception as e:
            logging.error(f"Konfigürasyon yazma hatası ({key_path}): {e}")
            return False
    
    def save(self) -> bool:
        """Konfigürasyonu dosyaya kaydet"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            logging.info(f"Konfigürasyon kaydedildi: {self.config_file}")
            return True
        except Exception as e:
            logging.error(f"Konfigürasyon kaydetme hatası: {e}")
            return False
    
    def reload(self) -> bool:
        """Konfigürasyonu yeniden yükle"""
        try:
            self.config = self._load_config()
            return True
        except Exception as e:
            logging.error(f"Konfigürasyon yeniden yükleme hatası: {e}")
            return False
    
    def get_server_config(self) -> Dict[str, Any]:
        """Sunucu konfigürasyonunu al"""
        return self.get("server", {})
    
    def get_client_config(self) -> Dict[str, Any]:
        """İstemci konfigürasyonunu al"""
        return self.get("client", {})
    
    def get_security_config(self) -> Dict[str, Any]:
        """Güvenlik konfigürasyonunu al"""
        return self.get("security", {})
    
    def get_exam_config(self) -> Dict[str, Any]:
        """Sınav konfigürasyonunu al"""
        return self.get("exam", {})
    
    def get_ui_config(self) -> Dict[str, Any]:
        """UI konfigürasyonunu al"""
        return self.get("ui", {})
    
    def validate_config(self) -> Dict[str, list]:
        """Konfigürasyon doğrulaması yap"""
        errors = []
        warnings = []
        
        # Sunucu ayarları kontrolü
        server_port = self.get("server.port")
        if not isinstance(server_port, int) or server_port < 1024 or server_port > 65535:
            errors.append("Sunucu portu 1024-65535 arasında olmalı")
        
        # Dosya boyutu kontrolü
        max_file_size = self.get("server.max_file_size_mb")
        if not isinstance(max_file_size, (int, float)) or max_file_size <= 0:
            errors.append("Maksimum dosya boyutu pozitif bir sayı olmalı")
        
        # İstemci ayarları kontrolü
        reconnect_attempts = self.get("client.reconnect_attempts")
        if not isinstance(reconnect_attempts, int) or reconnect_attempts < 1:
            warnings.append("Yeniden bağlanma denemesi en az 1 olmalı")
        
        # Sınav süresi kontrolü
        exam_duration = self.get("exam.default_duration_minutes")
        if not isinstance(exam_duration, int) or exam_duration < 5:
            warnings.append("Sınav süresi en az 5 dakika olmalı")
        
        return {"errors": errors, "warnings": warnings}
    
    def create_backup(self) -> Optional[str]:
        """Mevcut konfigürasyonun yedeğini oluştur"""
        try:
            import time
            timestamp = int(time.time())
            backup_file = f"{self.config_file}.backup.{timestamp}"
            
            if os.path.exists(self.config_file):
                import shutil
                shutil.copy2(self.config_file, backup_file)
                logging.info(f"Konfigürasyon yedeği oluşturuldu: {backup_file}")
                return backup_file
            return None
        except Exception as e:
            logging.error(f"Yedek oluşturma hatası: {e}")
            return None

# Global konfigürasyon instance'ı
_config_instance = None

def get_config() -> ConfigManager:
    """Global konfigürasyon instance'ını al"""
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigManager()
    return _config_instance

def reload_config():
    """Global konfigürasyonu yeniden yükle"""
    global _config_instance
    if _config_instance:
        _config_instance.reload()
    else:
        _config_instance = ConfigManager()

# Kolay erişim fonksiyonları
def get_server_ip() -> str:
    """Sunucu IP adresini al"""
    # İlk olarak ip.txt dosyasını kontrol et (geriye uyumluluk)
    if os.path.exists("ip.txt"):
        try:
            with open("ip.txt", "r") as f:
                ip = f.read().strip()
                if ip:
                    return ip
        except:
            pass
    
    # Sonra config'den al
    return get_config().get("client.server_ip", "127.0.0.1")

def get_server_port() -> int:
    """Sunucu portunu al"""
    return get_config().get("server.port", 2121)

def get_banned_apps() -> list:
    """Yasaklı uygulamaları al"""
    return get_config().get("security.banned_applications", [])

def get_max_file_size() -> int:
    """Maksimum dosya boyutunu al (bytes)"""
    mb = get_config().get("server.max_file_size_mb", 50)
    return mb * 1024 * 1024

if __name__ == "__main__":
    # Test
    config = ConfigManager()
    print("Konfigürasyon testi:")
    print(f"Sunucu portu: {config.get('server.port')}")
    print(f"Maksimum dosya boyutu: {config.get('server.max_file_size_mb')} MB")
    print(f"Yasaklı uygulamalar: {config.get('security.banned_applications')}")
    
    # Doğrulama
    validation = config.validate_config()
    if validation["errors"]:
        print(f"Hatalar: {validation['errors']}")
    if validation["warnings"]:
        print(f"Uyarılar: {validation['warnings']}")
