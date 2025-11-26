# Sınav Sistemi - Güvenli Çevrimdışı Sınav Platformu

Bu proje, güvenli ve güvenilir çevrimiçi sınav yönetimi için geliştirilmiş bir masaüstü uygulamasıdır.

## 🛠️ Kurulum

### 1. Gerekli Kütüphaneleri Yükleyin

```bash
pip install psutil
```

### 2. Dosyaları İndirin

Projeyi bilgisayarınıza indirin veya klonlayın.

### 3. Konfigürasyon

`config.json` dosyasını ihtiyaçlarınıza göre düzenleyin:

```json
{
    "server": {
        "host": "0.0.0.0",
        "port": 2121,
        "max_connections": 50
    },
    "client": {
        "server_ip": "127.0.0.1"
    }
}
```

### 4. Öğrenci Veritabanı

`students.txt` dosyasını oluşturun:

```
# Format: öğrenci_no:şifre:ad_soyad
123456:password:Test Öğrenci
415576:123456:Furkan Barış
```

## 🎯 Kullanım

### Sunucu Başlatma (Öğretmen)

```bash
python server.py
```

**Özellikler:**
- 🚀 Sınavı başlatma ve süre ayarlama
- 📢 Öğrencilere duyuru gönderme
- 👥 Bağlı öğrencileri görüntüleme
- 📊 Detaylı istatistikler
- 🔒 Giriş kontrolü

### İstemci Başlatma (Öğrenci)

```bash
python client.py
```
## 📁 Dosya Yapısı

```
app/
├── server.py              # Sunucu uygulaması
├── client.py              # İstemci uygulaması
├── config.json            # Konfigürasyon dosyası
├── config_manager.py      # Konfigürasyon yöneticisi
├── security_utils.py      # Güvenlik araçları
├── file_manager.py        # Dosya yönetimi
├── students.txt           # Öğrenci veritabanı
├── Sorular/              # Soru dosyaları
├── Cevaplar/             # Cevap dosyaları
└── Logs/                 # Log dosyaları
```

## ⚙️ Konfigürasyon Seçenekleri

### Sunucu Ayarları
- `host`: Sunucu IP adresi
- `port`: Sunucu portu
- `max_connections`: Maksimum bağlantı sayısı
- `max_file_size_mb`: Maksimum dosya boyutu (MB)

### Güvenlik Ayarları
- `banned_applications`: Yasaklı uygulamalar
- `allowed_file_extensions`: İzin verilen dosya uzantıları

### Sınav Ayarları
- `default_duration_minutes`: Varsayılan sınav süresi
- `warning_time_minutes`: Uyarı süresi
- `auto_submit_on_time_up`: Süre bitince otomatik teslim


Bu proje eğitim amaçlı geliştirilmiştir.

---
