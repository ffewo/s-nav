#!/usr/bin/env python3
"""
Server dağıtım paketi oluşturucu
"""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
DIST = ROOT / "dist" / "server"

def create_server_package():
    """Server dağıtım paketini oluştur"""
    print("=" * 50)
    print("Server Dağıtım Paketi Oluşturuluyor...")
    print("=" * 50)
    
    # Dist klasörünü temizle ve oluştur
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)
    
    # Gerekli klasörleri oluştur
    (DIST / "server").mkdir()
    (DIST / "common").mkdir()
    (DIST / "config").mkdir()
    (DIST / "data" / "questions").mkdir(parents=True)
    (DIST / "data" / "answers").mkdir(parents=True)
    (DIST / "logs").mkdir()
    
    # Server dosyalarını kopyala
    print("\n[1/6] Server dosyaları kopyalanıyor...")
    server_files = [
        "server/server.py",
        "server/server_ui.py",
        "server/protocol_handlers.py",
        "server/__init__.py"
    ]
    for file in server_files:
        src = ROOT / file
        if src.exists():
            shutil.copy2(src, DIST / file)
            print(f"  ✓ {file}")
    
    # Common dosyalarını kopyala
    print("\n[2/6] Common dosyaları kopyalanıyor...")
    common_files = [
        "common/config_manager.py",
        "common/exceptions.py",
        "common/file_manager.py",
        "common/network_utils.py",
        "common/__init__.py"
    ]
    for file in common_files:
        src = ROOT / file
        if src.exists():
            shutil.copy2(src, DIST / file)
            print(f"  ✓ {file}")
    
    # Config dosyalarını kopyala
    print("\n[3/6] Config dosyaları kopyalanıyor...")
    config_files = [
        "config/config.json",
        "config/students.txt"
    ]
    for file in config_files:
        src = ROOT / file
        if src.exists():
            shutil.copy2(src, DIST / file)
            print(f"  ✓ {file}")
    
    # README ve başlatma scripti oluştur
    print("\n[4/6] Dokümantasyon oluşturuluyor...")
    
    # Server README
    readme_content = """# Sınav Sistemi - Server (Öğretmen)

## Kurulum

1. Python 3.8+ yüklü olmalıdır
2. Gerekli paketler: tkinter (genellikle Python ile birlikte gelir)

## Çalıştırma

```bash
python -m server.server_ui
```

veya

```bash
python server/server_ui.py
```

## Yapılandırma

- `config/config.json` - Ana konfigürasyon dosyası
- `config/students.txt` - Öğrenci listesi (format: no:isim:sifre)

## Klasörler

- `data/questions/` - Soru dosyaları buraya konulur
- `data/answers/` - Öğrencilerden gelen cevaplar buraya kaydedilir
- `logs/` - Log dosyaları

## Notlar

- İlk çalıştırmada gerekli klasörler otomatik oluşturulur
- Server IP adresi config.json'da ayarlanabilir
"""
    (DIST / "README.md").write_text(readme_content, encoding="utf-8")
    print("  ✓ README.md")
    
    # Başlatma scripti (Windows)
    start_script = """@echo off
echo Sınav Sistemi - Server Baslatiliyor...
python -m server.server_ui
pause
"""
    (DIST / "start_server.bat").write_text(start_script, encoding="utf-8")
    print("  ✓ start_server.bat")
    
    # Başlatma scripti (Linux/Mac)
    start_script_sh = """#!/bin/bash
echo "Sınav Sistemi - Server Baslatiliyor..."
python3 -m server.server_ui
"""
    start_sh = DIST / "start_server.sh"
    start_sh.write_text(start_script_sh, encoding="utf-8")
    os.chmod(start_sh, 0o755)
    print("  ✓ start_server.sh")
    
    # .gitkeep dosyaları
    print("\n[5/6] Klasör yapısı tamamlanıyor...")
    (DIST / "data" / "questions" / ".gitkeep").touch()
    (DIST / "data" / "answers" / ".gitkeep").touch()
    (DIST / "logs" / ".gitkeep").touch()
    
    # Paket bilgisi
    print("\n[6/6] Paket bilgisi oluşturuluyor...")
    package_info = f"""Sınav Sistemi - Server Paketi
Oluşturulma Tarihi: {Path(__file__).stat().st_mtime}
"""
    (DIST / "PACKAGE_INFO.txt").write_text(package_info, encoding="utf-8")
    
    print("\n" + "=" * 50)
    print(f"✓ Server paketi hazır: {DIST}")
    print("=" * 50)
    print("\nPaket içeriği:")
    print(f"  - Server modülleri: {len(list((DIST / 'server').glob('*.py')))} dosya")
    print(f"  - Common modüller: {len(list((DIST / 'common').glob('*.py')))} dosya")
    print(f"  - Config dosyaları: {len(list((DIST / 'config').glob('*')))} dosya")

if __name__ == "__main__":
    create_server_package()

