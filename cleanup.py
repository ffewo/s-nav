#!/usr/bin/env python3
"""
Sınav Sistemi Temizlik Scripti
Bu script gereksiz dosyaları temizler ve sistemi optimize eder.
"""

import os
import shutil
import glob
import time
from datetime import datetime, timedelta

def cleanup_logs(max_age_days=7):
    """Eski log dosyalarını temizle"""
    print("Log dosyaları temizleniyor...")
    
    if not os.path.exists("Logs"):
        return
    
    cutoff_date = datetime.now() - timedelta(days=max_age_days)
    cleaned_count = 0
    
    for log_file in glob.glob("Logs/*.log"):
        try:
            file_time = datetime.fromtimestamp(os.path.getmtime(log_file))
            if file_time < cutoff_date:
                os.remove(log_file)
                print(f"  Silindi: {log_file}")
                cleaned_count += 1
        except Exception as e:
            print(f"  Hata: {log_file} silinemedi - {e}")
    
    print(f"  {cleaned_count} eski log dosyası temizlendi")

def cleanup_temp_files():
    """Geçici dosyaları temizle"""
    print("Geçici dosyalar temizleniyor...")
    
    temp_patterns = [
        "*.tmp", "*.temp", "*.bak", "*.swp", "*~",
        "*.pyc", "*.pyo", ".DS_Store", "Thumbs.db", "desktop.ini"
    ]
    
    cleaned_count = 0
    
    for pattern in temp_patterns:
        for temp_file in glob.glob(pattern):
            try:
                os.remove(temp_file)
                print(f"  Silindi: {temp_file}")
                cleaned_count += 1
            except Exception as e:
                print(f"  Hata: {temp_file} silinemedi - {e}")
    
    print(f"  {cleaned_count} geçici dosya temizlendi")

def cleanup_pycache():
    """Python cache klasörlerini temizle"""
    print("Python cache dosyaları temizleniyor...")
    
    cleaned_count = 0
    
    for root, dirs, files in os.walk("."):
        if "__pycache__" in dirs:
            cache_path = os.path.join(root, "__pycache__")
            try:
                shutil.rmtree(cache_path)
                print(f"  Silindi: {cache_path}")
                cleaned_count += 1
            except Exception as e:
                print(f"  Hata: {cache_path} silinemedi - {e}")
    
    print(f"  {cleaned_count} cache klasörü temizlendi")

def cleanup_old_backups(max_age_days=30):
    """Eski yedek dosyalarını temizle"""
    print("Eski yedek dosyaları temizleniyor...")
    
    backup_patterns = ["*.backup", "*.backup.*", "config.json.backup.*"]
    cutoff_date = datetime.now() - timedelta(days=max_age_days)
    cleaned_count = 0
    
    for pattern in backup_patterns:
        for backup_file in glob.glob(pattern):
            try:
                file_time = datetime.fromtimestamp(os.path.getmtime(backup_file))
                if file_time < cutoff_date:
                    os.remove(backup_file)
                    print(f"  Silindi: {backup_file}")
                    cleaned_count += 1
            except Exception as e:
                print(f"  Hata: {backup_file} silinemedi - {e}")
    
    print(f"  {cleaned_count} eski yedek dosyası temizlendi")

def cleanup_empty_dirs():
    """Boş klasörleri temizle"""
    print("Boş klasörler kontrol ediliyor...")
    
    # Korunması gereken klasörler
    protected_dirs = {"Logs", "Sorular", "Cevaplar"}
    cleaned_count = 0
    
    for root, dirs, files in os.walk(".", topdown=False):
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            
            # Korunan klasörleri atla
            if os.path.basename(dir_path) in protected_dirs:
                continue
            
            try:
                # Klasör boş mu kontrol et
                if not os.listdir(dir_path):
                    os.rmdir(dir_path)
                    print(f"  Silindi: {dir_path}")
                    cleaned_count += 1
            except Exception as e:
                print(f"  Hata: {dir_path} silinemedi - {e}")
    
    print(f"  {cleaned_count} boş klasör temizlendi")

def show_disk_usage():
    """Disk kullanımını göster"""
    print("Disk kullanımı:")
    
    total_size = 0
    file_count = 0
    
    for root, dirs, files in os.walk("."):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                size = os.path.getsize(file_path)
                total_size += size
                file_count += 1
            except:
                pass
    
    # Boyutu MB cinsinden göster
    size_mb = total_size / (1024 * 1024)
    print(f"  Toplam dosya sayısı: {file_count}")
    print(f"  Toplam boyut: {size_mb:.2f} MB")

def main():
    """Ana temizlik fonksiyonu"""
    print("=" * 50)
    print("Sınav Sistemi Temizlik Scripti")
    print("=" * 50)
    
    start_time = time.time()
    
    # Başlangıç durumu
    print("\nBaşlangıç durumu:")
    show_disk_usage()
    
    print("\nTemizlik işlemleri başlatılıyor...\n")
    
    # Temizlik işlemleri
    cleanup_temp_files()
    print()
    
    cleanup_pycache()
    print()
    
    cleanup_logs(max_age_days=7)
    print()
    
    cleanup_old_backups(max_age_days=30)
    print()
    
    cleanup_empty_dirs()
    print()
    
    # Son durum
    print("Temizlik sonrası durum:")
    show_disk_usage()
    
    # Süre hesapla
    elapsed_time = time.time() - start_time
    print(f"\nTemizlik tamamlandı! Süre: {elapsed_time:.2f} saniye")
    
    print("\nÖneriler:")
    print("• Bu scripti haftada bir çalıştırın")
    print("• Önemli dosyaları yedeklemeyi unutmayın")
    print("• Log dosyalarını düzenli kontrol edin")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTemizlik işlemi kullanıcı tarafından durduruldu.")
    except Exception as e:
        print(f"\n\nHata: {e}")
        print("Temizlik işlemi başarısız oldu.")
