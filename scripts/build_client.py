#!/usr/bin/env python3
"""
Client dağıtım paketi oluşturucu
"""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
DIST = ROOT / "dist" / "client"

def create_client_package():
    """Client dağıtım paketini oluştur"""
    print("=" * 50)
    print("Client Dağıtım Paketi Oluşturuluyor...")
    print("=" * 50)
    
    # Dist klasörünü temizle ve oluştur
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)
    
    # Gerekli klasörleri oluştur
    (DIST / "client").mkdir()
    (DIST / "common").mkdir()
    (DIST / "config").mkdir()
    (DIST / "logs").mkdir()
    
    # Client dosyalarını kopyala
    print("\n[1/5] Client dosyaları kopyalanıyor...")
    client_files = [
        "client/client.py",
        "client/client_ui.py",
        "client/client_transfer.py",
        "client/__init__.py"
    ]
    for file in client_files:
        src = ROOT / file
        if src.exists():
            shutil.copy2(src, DIST / file)
            print(f"  ✓ {file}")
    
    # Common dosyalarını kopyala (security_manager hariç - hardcoded)
    print("\n[2/5] Common dosyaları kopyalanıyor...")
    common_files = [
        "common/config_manager.py",
        "common/exceptions.py",
        "common/network_utils.py",
        "common/security_manager.py",  # Client için gerekli
        "common/__init__.py"
    ]
    for file in common_files:
        src = ROOT / file
        if src.exists():
            shutil.copy2(src, DIST / file)
            print(f"  ✓ {file}")
    
    # Config dosyalarını kopyala (sadece config.json, students.txt değil)
    print("\n[3/5] Config dosyaları kopyalanıyor...")
    config_file = ROOT / "config" / "config.json"
    if config_file.exists():
        shutil.copy2(config_file, DIST / "config" / "config.json")
        print("  ✓ config/config.json")
    
    # README ve başlatma scripti oluştur
    print("\n[4/5] Dokümantasyon oluşturuluyor...")
    
    # Client README
    readme_content = """# Sınav Sistemi - Client (Öğrenci)

## Kurulum

1. Python 3.8+ yüklü olmalıdır
2. Gerekli paketler: tkinter (genellikle Python ile birlikte gelir), psutil

### psutil Kurulumu

```bash
pip install psutil
```

## Çalıştırma

```bash
python -m client.client_ui
```

veya

```bash
python client/client_ui.py
```

## Yapılandırma

- `config/config.json` - Ana konfigürasyon dosyası
  - `client.server_ip` - Sunucu IP adresi
  - `server.port` - Sunucu portu (varsayılan: 2121)

Alternatif olarak `ip.txt` dosyası oluşturup sadece IP adresini yazabilirsiniz.

## Klasörler

- `logs/` - Log dosyaları

## Notlar

- İlk çalıştırmada gerekli klasörler otomatik oluşturulur
- Server IP adresi config.json veya ip.txt'de ayarlanabilir
- Güvenlik: Yasaklı uygulamalar kod içinde tanımlıdır (config'de değil)
"""
    (DIST / "README.md").write_text(readme_content, encoding="utf-8")
    print("  ✓ README.md")
    
    # Başlatma scripti (Windows)
    start_script = """@echo off
echo Sınav Sistemi - Client Baslatiliyor...
python -m client.client_ui
pause
"""
    (DIST / "start_client.bat").write_text(start_script, encoding="utf-8")
    print("  ✓ start_client.bat")
    
    # Başlatma scripti (Linux/Mac)
    start_script_sh = """#!/bin/bash
echo "Sınav Sistemi - Client Baslatiliyor..."
python3 -m client.client_ui
"""
    start_sh = DIST / "start_client.sh"
    start_sh.write_text(start_script_sh, encoding="utf-8")
    os.chmod(start_sh, 0o755)
    print("  ✓ start_client.sh")
    
    # .gitkeep dosyası
    print("\n[5/5] Klasör yapısı tamamlanıyor...")
    (DIST / "logs" / ".gitkeep").touch()
    
    # Paket bilgisi
    package_info = f"""Sınav Sistemi - Client Paketi
Oluşturulma Tarihi: {Path(__file__).stat().st_mtime}
"""
    (DIST / "PACKAGE_INFO.txt").write_text(package_info, encoding="utf-8")
    
    print("\n" + "=" * 50)
    print(f"✓ Client paketi hazır: {DIST}")
    print("=" * 50)
    print("\nPaket içeriği:")
    print(f"  - Client modülleri: {len(list((DIST / 'client').glob('*.py')))} dosya")
    print(f"  - Common modüller: {len(list((DIST / 'common').glob('*.py')))} dosya")
    print(f"  - Config dosyaları: {len(list((DIST / 'config').glob('*')))} dosya")

if __name__ == "__main__":
    create_client_package()

