"""
Sınav Sistemi Güvenlik Yardımcıları
Bu modül güvenlik ile ilgili fonksiyonları içerir.
"""

import hashlib
import secrets
import os
import time
import logging
from typing import Optional, Tuple, List
import re

class SecurityManager:
    """Güvenlik yönetim sınıfı"""
    
    def __init__(self):
        self.failed_attempts = {}  # IP -> (count, last_attempt_time)
        self.max_attempts = 5
        self.lockout_duration = 300  # 5 dakika
        
    def hash_password(self, password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        """Şifreyi güvenli şekilde hash'le"""
        if salt is None:
            salt = secrets.token_hex(16)
        
        # PBKDF2 ile güvenli hash
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000  # 100,000 iterasyon
        )
        
        return password_hash.hex(), salt
    
    def verify_password(self, password: str, stored_hash: str, salt: str) -> bool:
        """Şifre doğrulaması yap"""
        try:
            computed_hash, _ = self.hash_password(password, salt)
            return secrets.compare_digest(computed_hash, stored_hash)
        except Exception as e:
            logging.error(f"Şifre doğrulama hatası: {e}")
            return False
    
    def is_ip_locked(self, ip_address: str) -> bool:
        """IP adresi kilitli mi kontrol et"""
        if ip_address not in self.failed_attempts:
            return False
        
        count, last_attempt = self.failed_attempts[ip_address]
        
        # Kilitleme süresi dolmuş mu?
        if time.time() - last_attempt > self.lockout_duration:
            del self.failed_attempts[ip_address]
            return False
        
        return count >= self.max_attempts
    
    def record_failed_attempt(self, ip_address: str):
        """Başarısız giriş denemesini kaydet"""
        current_time = time.time()
        
        if ip_address in self.failed_attempts:
            count, _ = self.failed_attempts[ip_address]
            self.failed_attempts[ip_address] = (count + 1, current_time)
        else:
            self.failed_attempts[ip_address] = (1, current_time)
        
        logging.warning(f"Başarısız giriş denemesi: {ip_address} ({self.failed_attempts[ip_address][0]} deneme)")
    
    def clear_failed_attempts(self, ip_address: str):
        """Başarılı giriş sonrası denemeleri temizle"""
        if ip_address in self.failed_attempts:
            del self.failed_attempts[ip_address]
    
    def validate_student_number(self, student_no: str) -> bool:
        """Öğrenci numarası formatını doğrula"""
        if not student_no:
            return False
        
        # Sadece rakam, 6-10 karakter arası
        if not re.match(r'^\d{6,10}$', student_no):
            return False
        
        return True
    
    def validate_password(self, password: str) -> Tuple[bool, List[str]]:
        """Şifre güvenlik kurallarını kontrol et"""
        errors = []
        
        if len(password) < 6:
            errors.append("Şifre en az 6 karakter olmalı")
        
        if len(password) > 50:
            errors.append("Şifre en fazla 50 karakter olabilir")
        
        # Basit karakterler kontrolü
        if not re.search(r'[a-zA-Z]', password):
            errors.append("Şifre en az bir harf içermeli")
        
        if not re.search(r'\d', password):
            errors.append("Şifre en az bir rakam içermeli")
        
        return len(errors) == 0, errors
    
    def sanitize_filename(self, filename: str) -> str:
        """Dosya adını güvenli hale getir"""
        # Tehlikeli karakterleri temizle
        safe_chars = re.sub(r'[<>:"/\\|?*]', '_', filename)
        
        # Nokta ile başlayan dosyaları engelle
        if safe_chars.startswith('.'):
            safe_chars = '_' + safe_chars[1:]
        
        # Çok uzun dosya adlarını kısalt
        if len(safe_chars) > 100:
            name, ext = os.path.splitext(safe_chars)
            safe_chars = name[:95] + ext
        
        return safe_chars
    
    def is_allowed_file_extension(self, filename: str, allowed_extensions: List[str]) -> bool:
        """Dosya uzantısı izinli mi kontrol et"""
        if not filename:
            return False
        
        _, ext = os.path.splitext(filename.lower())
        return ext in [e.lower() for e in allowed_extensions]
    
    def generate_session_token(self) -> str:
        """Güvenli oturum token'ı oluştur"""
        return secrets.token_urlsafe(32)
    
    def validate_file_content(self, file_path: str) -> Tuple[bool, str]:
        """Dosya içeriğini güvenlik açısından kontrol et"""
        try:
            # Dosya boyutu kontrolü
            file_size = os.path.getsize(file_path)
            if file_size > 50 * 1024 * 1024:  # 50MB
                return False, "Dosya çok büyük"
            
            # Dosya türü kontrolü (magic bytes)
            with open(file_path, 'rb') as f:
                header = f.read(512)
            
            # Basit malware imzası kontrolü (örnek)
            suspicious_patterns = [
                b'eval(',
                b'exec(',
                b'<script',
                b'javascript:',
                b'vbscript:'
            ]
            
            for pattern in suspicious_patterns:
                if pattern in header.lower():
                    return False, f"Şüpheli içerik tespit edildi: {pattern.decode('utf-8', errors='ignore')}"
            
            return True, "Dosya güvenli"
            
        except Exception as e:
            logging.error(f"Dosya güvenlik kontrolü hatası: {e}")
            return False, f"Dosya kontrol hatası: {str(e)}"
    
    def log_security_event(self, event_type: str, details: dict):
        """Güvenlik olaylarını logla"""
        log_entry = {
            "timestamp": time.time(),
            "type": event_type,
            "details": details
        }
        
        logging.warning(f"GÜVENLİK OLAYI: {event_type} - {details}")
        
        # Güvenlik loglarını ayrı dosyaya da yaz
        try:
            security_log_file = "Logs/security.log"
            os.makedirs(os.path.dirname(security_log_file), exist_ok=True)
            
            with open(security_log_file, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {event_type}: {details}\n")
        except Exception as e:
            logging.error(f"Güvenlik log yazma hatası: {e}")

class FileValidator:
    """Dosya doğrulama sınıfı"""
    
    ALLOWED_EXTENSIONS = {
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.txt': 'text/plain',
        '.rtf': 'application/rtf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.zip': 'application/zip',
        '.rar': 'application/x-rar-compressed',
        '.7z': 'application/x-7z-compressed'
    }
    
    @classmethod
    def validate_file(cls, file_path: str) -> Tuple[bool, str]:
        """Dosyayı kapsamlı şekilde doğrula"""
        try:
            if not os.path.exists(file_path):
                return False, "Dosya bulunamadı"
            
            # Dosya boyutu kontrolü
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                return False, "Dosya boş"
            
            if file_size > 50 * 1024 * 1024:  # 50MB
                return False, "Dosya çok büyük (max 50MB)"
            
            # Uzantı kontrolü
            _, ext = os.path.splitext(file_path.lower())
            if ext not in cls.ALLOWED_EXTENSIONS:
                return False, f"İzin verilmeyen dosya türü: {ext}"
            
            # İçerik kontrolü
            security_manager = SecurityManager()
            is_safe, message = security_manager.validate_file_content(file_path)
            
            if not is_safe:
                return False, message
            
            return True, "Dosya geçerli"
            
        except Exception as e:
            logging.error(f"Dosya doğrulama hatası: {e}")
            return False, f"Doğrulama hatası: {str(e)}"

# Global güvenlik yöneticisi
_security_manager = None

def get_security_manager() -> SecurityManager:
    """Global güvenlik yöneticisini al"""
    global _security_manager
    if _security_manager is None:
        _security_manager = SecurityManager()
    return _security_manager

def hash_password(password: str) -> Tuple[str, str]:
    """Şifreyi hash'le"""
    return get_security_manager().hash_password(password)

def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Şifreyi doğrula"""
    return get_security_manager().verify_password(password, stored_hash, salt)

def validate_student_credentials(student_no: str, password: str) -> Tuple[bool, List[str]]:
    """Öğrenci kimlik bilgilerini doğrula"""
    errors = []
    
    # Öğrenci numarası kontrolü
    if not get_security_manager().validate_student_number(student_no):
        errors.append("Geçersiz öğrenci numarası formatı")
    
    # Şifre kontrolü
    is_valid_password, password_errors = get_security_manager().validate_password(password)
    if not is_valid_password:
        errors.extend(password_errors)
    
    return len(errors) == 0, errors

if __name__ == "__main__":
    # Test
    security = SecurityManager()
    
    # Şifre hash testi
    password = "test123"
    hashed, salt = security.hash_password(password)
    print(f"Hash: {hashed}")
    print(f"Salt: {salt}")
    print(f"Doğrulama: {security.verify_password(password, hashed, salt)}")
    
    # Dosya adı temizleme testi
    unsafe_filename = "../../../etc/passwd"
    safe_filename = security.sanitize_filename(unsafe_filename)
    print(f"Güvenli dosya adı: {safe_filename}")
