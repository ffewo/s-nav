#!/usr/bin/env python3
"""
Tüm dağıtım paketlerini oluştur
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "scripts"

def build_all():
    """Tüm paketleri oluştur"""
    print("=" * 60)
    print("TÜM DAĞITIM PAKETLERİ OLUŞTURULUYOR")
    print("=" * 60)
    
    # Server paketi
    print("\n" + "-" * 60)
    print("SERVER PAKETİ")
    print("-" * 60)
    subprocess.run([sys.executable, str(SCRIPTS / "build_server.py")])
    
    # Client paketi
    print("\n" + "-" * 60)
    print("CLIENT PAKETİ")
    print("-" * 60)
    subprocess.run([sys.executable, str(SCRIPTS / "build_client.py")])
    
    print("\n" + "=" * 60)
    print("✓ TÜM PAKETLER HAZIR!")
    print("=" * 60)
    print(f"\nPaketler: {ROOT / 'dist'}")
    print("  - dist/server/")
    print("  - dist/client/")

if __name__ == "__main__":
    build_all()

