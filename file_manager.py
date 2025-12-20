"""
Sınav Sistemi Dosya Yöneticisi
Bu modül dosya işlemlerini güvenli ve güvenilir şekilde yönetir.
"""

import os
import shutil
import hashlib
import logging
from typing import Optional, Tuple, Dict, List
from datetime import datetime
import json

class SecureFileHandler:
    """Güvenli dosya işleyici"""
    
    def __init__(self, base_dir: str = "Cevaplar"):
        self.base_dir = base_dir
        self.ensure_directory_exists(base_dir)
        
    def ensure_directory_exists(self, directory: str):
        """Dizinin var olduğundan emin ol"""
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            logging.error(f"Dizin oluşturma hatası: {e}")
            raise
    
    def generate_safe_filename(self, student_no: str, original_filename: str) -> str:
        """Güvenli dosya adı oluştur"""
        # Dosya adını temizle
        safe_original = self._sanitize_filename(original_filename)
        
        # Zaman damgası ekle
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Dosya adını ve uzantısını ayır
        name, ext = os.path.splitext(safe_original)
        
        # Güvenli dosya adı oluştur
        safe_filename = f"{student_no}_{timestamp}_{name}{ext}"
        
        return safe_filename
    
    def _sanitize_filename(self, filename: str) -> str:
        """Dosya adını güvenli hale getir"""
        import re
        
        # Tehlikeli karakterleri kaldır
        safe_chars = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
        
        # Nokta ile başlayan dosyaları engelle
        if safe_chars.startswith('.'):
            safe_chars = 'file_' + safe_chars[1:]
        
        # Çok uzun dosya adlarını kısalt
        if len(safe_chars) > 100:
            name, ext = os.path.splitext(safe_chars)
            safe_chars = name[:95] + ext
        
        return safe_chars
    
    def save_file_securely(self, file_data: bytes, student_no: str, 
                          original_filename: str) -> Tuple[bool, str, str]:
        """Dosyayı güvenli şekilde kaydet"""
        try:
            # Güvenli dosya adı oluştur
            safe_filename = self.generate_safe_filename(student_no, original_filename)
            file_path = os.path.join(self.base_dir, safe_filename)
            
            # Geçici dosya oluştur
            temp_path = file_path + ".tmp"
            
            # Dosyayı geçici konuma yaz
            with open(temp_path, 'wb') as f:
                f.write(file_data)
            
            # Dosya bütünlüğünü kontrol et
            if self._verify_file_integrity(temp_path, len(file_data)):
                # Geçici dosyayı final konuma taşı
                shutil.move(temp_path, file_path)
                
                # Metadata kaydet
                self._save_file_metadata(file_path, student_no, original_filename, len(file_data))
                
                logging.info(f"Dosya güvenli şekilde kaydedildi: {safe_filename}")
                return True, file_path, safe_filename
            else:
                # Bozuk dosyayı sil
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return False, "", "Dosya bütünlüğü kontrolü başarısız"
                
        except Exception as e:
            logging.error(f"Dosya kaydetme hatası: {e}")
            return False, "", str(e)
    
    def _verify_file_integrity(self, file_path: str, expected_size: int) -> bool:
        """Dosya bütünlüğünü kontrol et"""
        try:
            # Dosya boyutu kontrolü
            actual_size = os.path.getsize(file_path)
            if actual_size != expected_size:
                logging.error(f"Dosya boyutu uyumsuz: {actual_size} != {expected_size}")
                return False
            
            # Dosya okunabilir mi kontrol et
            with open(file_path, 'rb') as f:
                f.read(1024)  # İlk 1KB'ı oku
            
            return True
            
        except Exception as e:
            logging.error(f"Dosya bütünlük kontrolü hatası: {e}")
            return False
    
    def _save_file_metadata(self, file_path: str, student_no: str, 
                           original_filename: str, file_size: int):
        """Dosya metadata'sını kaydet"""
        try:
            metadata = {
                "student_no": student_no,
                "original_filename": original_filename,
                "file_size": file_size,
                "upload_time": datetime.now().isoformat(),
                "file_hash": self._calculate_file_hash(file_path)
            }
            
            metadata_path = file_path + ".meta"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logging.error(f"Metadata kaydetme hatası: {e}")
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Dosyanın SHA-256 hash'ini hesapla"""
        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            logging.error(f"Hash hesaplama hatası: {e}")
            return ""
    
class QuestionFileManager:
    """Soru dosyası yöneticisi"""
    
    def __init__(self, questions_dir: str = "Sorular"):
        self.questions_dir = questions_dir
        self.ensure_directory_exists(questions_dir)
    
    def ensure_directory_exists(self, directory: str):
        """Dizinin var olduğundan emin ol"""
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            logging.error(f"Dizin oluşturma hatası: {e}")
            raise
    
    def list_question_files(self) -> List[Dict]:
        """Soru dosyalarını listele"""
        files = []
        try:
            for filename in os.listdir(self.questions_dir):
                file_path = os.path.join(self.questions_dir, filename)
                if os.path.isfile(file_path):
                    file_info = {
                        "filename": filename,
                        "size": os.path.getsize(file_path),
                        "modified": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
                    }
                    files.append(file_info)
            
            # Dosya adına göre sırala
            files.sort(key=lambda x: x["filename"])
            
        except Exception as e:
            logging.error(f"Soru dosyası listeleme hatası: {e}")
        
        return files
    
    def get_file_content(self, filename: str) -> Optional[bytes]:
        """Dosya içeriğini al"""
        try:
            file_path = os.path.join(self.questions_dir, filename)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                with open(file_path, 'rb') as f:
                    return f.read()
            return None
        except Exception as e:
            logging.error(f"Dosya okuma hatası: {e}")
            return None

# Global instance'lar
_secure_file_handler = None
_question_file_manager = None

def get_secure_file_handler() -> SecureFileHandler:
    """Global güvenli dosya işleyicisini al"""
    global _secure_file_handler
    if _secure_file_handler is None:
        _secure_file_handler = SecureFileHandler()
    return _secure_file_handler

def get_question_file_manager() -> QuestionFileManager:
    """Global soru dosyası yöneticisini al"""
    global _question_file_manager
    if _question_file_manager is None:
        _question_file_manager = QuestionFileManager()
    return _question_file_manager

