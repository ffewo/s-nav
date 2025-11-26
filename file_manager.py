"""
Sınav Sistemi Dosya Yöneticisi
Bu modül dosya işlemlerini güvenli ve güvenilir şekilde yönetir.
"""

import os
import shutil
import hashlib
import time
import threading
import logging
from typing import Optional, Tuple, Dict, List, Callable
from datetime import datetime
import json

class FileTransferManager:
    """Dosya transfer yöneticisi"""
    
    def __init__(self):
        self.active_transfers = {}  # transfer_id -> transfer_info
        self.transfer_lock = threading.Lock()
        
    def start_upload(self, student_no: str, filename: str, filesize: int, 
                    progress_callback: Optional[Callable] = None) -> str:
        """Dosya yükleme işlemini başlat"""
        transfer_id = f"{student_no}_{int(time.time())}_{filename}"
        
        with self.transfer_lock:
            self.active_transfers[transfer_id] = {
                "student_no": student_no,
                "filename": filename,
                "filesize": filesize,
                "bytes_received": 0,
                "start_time": time.time(),
                "status": "active",
                "progress_callback": progress_callback,
                "temp_file": None,
                "final_file": None
            }
        
        logging.info(f"Dosya yükleme başlatıldı: {transfer_id}")
        return transfer_id
    
    def update_progress(self, transfer_id: str, bytes_received: int):
        """Transfer ilerlemesini güncelle"""
        with self.transfer_lock:
            if transfer_id in self.active_transfers:
                transfer_info = self.active_transfers[transfer_id]
                transfer_info["bytes_received"] = bytes_received
                
                # Progress callback çağır
                if transfer_info["progress_callback"]:
                    progress = (bytes_received / transfer_info["filesize"]) * 100
                    transfer_info["progress_callback"](progress)
    
    def complete_transfer(self, transfer_id: str, success: bool = True):
        """Transfer'ı tamamla"""
        with self.transfer_lock:
            if transfer_id in self.active_transfers:
                transfer_info = self.active_transfers[transfer_id]
                transfer_info["status"] = "completed" if success else "failed"
                transfer_info["end_time"] = time.time()
                
                duration = transfer_info["end_time"] - transfer_info["start_time"]
                logging.info(f"Transfer tamamlandı: {transfer_id} - {duration:.2f}s")
    
    def get_transfer_info(self, transfer_id: str) -> Optional[Dict]:
        """Transfer bilgilerini al"""
        with self.transfer_lock:
            return self.active_transfers.get(transfer_id)
    
    def cleanup_old_transfers(self, max_age_hours: int = 24):
        """Eski transfer kayıtlarını temizle"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        with self.transfer_lock:
            to_remove = []
            for transfer_id, info in self.active_transfers.items():
                if current_time - info["start_time"] > max_age_seconds:
                    to_remove.append(transfer_id)
            
            for transfer_id in to_remove:
                del self.active_transfers[transfer_id]
                logging.info(f"Eski transfer kaydı temizlendi: {transfer_id}")

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
    
    def get_file_info(self, file_path: str) -> Optional[Dict]:
        """Dosya bilgilerini al"""
        try:
            metadata_path = file_path + ".meta"
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return None
        except Exception as e:
            logging.error(f"Dosya bilgisi okuma hatası: {e}")
            return None
    
    def list_student_files(self, student_no: str) -> List[Dict]:
        """Öğrencinin dosyalarını listele"""
        files = []
        try:
            for filename in os.listdir(self.base_dir):
                if filename.startswith(f"{student_no}_") and not filename.endswith('.meta'):
                    file_path = os.path.join(self.base_dir, filename)
                    file_info = self.get_file_info(file_path)
                    
                    if file_info:
                        file_info["saved_filename"] = filename
                        file_info["file_path"] = file_path
                        files.append(file_info)
            
            # Yükleme zamanına göre sırala
            files.sort(key=lambda x: x.get("upload_time", ""), reverse=True)
            
        except Exception as e:
            logging.error(f"Dosya listeleme hatası: {e}")
        
        return files
    
    def backup_file(self, file_path: str) -> Optional[str]:
        """Dosyanın yedeğini oluştur"""
        try:
            if not os.path.exists(file_path):
                return None
            
            backup_dir = os.path.join(self.base_dir, "backups")
            self.ensure_directory_exists(backup_dir)
            
            filename = os.path.basename(file_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"{timestamp}_{filename}"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            shutil.copy2(file_path, backup_path)
            
            # Metadata'yı da yedekle
            meta_path = file_path + ".meta"
            if os.path.exists(meta_path):
                backup_meta_path = backup_path + ".meta"
                shutil.copy2(meta_path, backup_meta_path)
            
            logging.info(f"Dosya yedeği oluşturuldu: {backup_path}")
            return backup_path
            
        except Exception as e:
            logging.error(f"Dosya yedekleme hatası: {e}")
            return None
    
    def cleanup_temp_files(self):
        """Geçici dosyaları temizle"""
        try:
            for filename in os.listdir(self.base_dir):
                if filename.endswith('.tmp'):
                    file_path = os.path.join(self.base_dir, filename)
                    # 1 saatten eski geçici dosyaları sil
                    if time.time() - os.path.getctime(file_path) > 3600:
                        os.remove(file_path)
                        logging.info(f"Eski geçici dosya silindi: {filename}")
        except Exception as e:
            logging.error(f"Geçici dosya temizleme hatası: {e}")

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
_file_transfer_manager = None
_secure_file_handler = None
_question_file_manager = None

def get_file_transfer_manager() -> FileTransferManager:
    """Global dosya transfer yöneticisini al"""
    global _file_transfer_manager
    if _file_transfer_manager is None:
        _file_transfer_manager = FileTransferManager()
    return _file_transfer_manager

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

if __name__ == "__main__":
    # Test
    handler = SecureFileHandler()
    
    # Test dosyası oluştur
    test_data = b"Bu bir test dosyasidir."
    success, path, filename = handler.save_file_securely(test_data, "123456", "test.txt")
    
    print(f"Kaydetme başarılı: {success}")
    print(f"Dosya yolu: {path}")
    print(f"Güvenli dosya adı: {filename}")
    
    # Dosya bilgilerini al
    info = handler.get_file_info(path)
    print(f"Dosya bilgileri: {info}")
    
    # Öğrenci dosyalarını listele
    files = handler.list_student_files("123456")
    print(f"Öğrenci dosyaları: {files}")
