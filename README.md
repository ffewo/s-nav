# Sınav Sistemi - Güvenli Çevrimiçi Sınav Platformu

Bu proje, güvenli ve güvenilir çevrimiçi sınav yönetimi için geliştirilmiş bir masaüstü uygulamasıdır.

## 🚀 Özellikler

### Güvenlik
- ✅ Gelişmiş şifre hash'leme (PBKDF2)
- ✅ IP tabanlı başarısız giriş koruması
- ✅ Dosya içeriği güvenlik taraması
- ✅ Yasaklı uygulama engelleme
- ✅ Güvenli dosya adı oluşturma
- ✅ Kapsamlı güvenlik loglama

### Ağ ve Bağlantı
- ✅ Otomatik yeniden bağlanma
- ✅ Heartbeat monitoring
- ✅ Zaman aşımı yönetimi
- ✅ Bağlantı durumu takibi
- ✅ Hata toleransı

### Dosya Yönetimi
- ✅ Güvenli dosya transferi
- ✅ Dosya bütünlüğü kontrolü
- ✅ Otomatik yedekleme
- ✅ Metadata yönetimi
- ✅ Transfer ilerleme takibi

### Kullanıcı Arayüzü
- ✅ Modern ve kullanıcı dostu tasarım
- ✅ Gerçek zamanlı durum güncellemeleri
- ✅ Detaylı istatistikler
- ✅ Emoji destekli görsel geri bildirim
- ✅ Responsive tasarım

### Yönetim
- ✅ JSON tabanlı konfigürasyon
- ✅ Kapsamlı loglama sistemi
- ✅ Öğrenci aktivite takibi
- ✅ Sınav süre yönetimi
- ✅ Duyuru sistemi

## 📋 Sistem Gereksinimleri

- **İşletim Sistemi:** Windows 10/11, macOS 10.14+, Linux Ubuntu 18.04+
- **Python:** 3.7 veya üzeri
- **RAM:** En az 512 MB
- **Disk Alanı:** En az 100 MB boş alan
- **Ağ:** TCP/IP bağlantısı

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

**Özellikler:**
- 🔐 Güvenli giriş sistemi
- 📁 Soru dosyalarını indirme
- 📤 Cevap dosyası yükleme
- ⏰ Gerçek zamanlı süre takibi
- 🚫 Otomatik browser engelleme

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

## 🔧 Gelişmiş Özellikler

### 1. Güvenlik Loglama

Tüm güvenlik olayları `Logs/security.log` dosyasına kaydedilir:
- Başarısız giriş denemeleri
- Şüpheli dosya yüklemeleri
- Yasaklı uygulama tespitleri

### 2. Dosya Bütünlüğü

Her yüklenen dosya için:
- SHA-256 hash kontrolü
- Boyut doğrulaması
- Metadata kaydı

### 3. Otomatik Yedekleme

Kritik dosyalar otomatik olarak yedeklenir:
- Öğrenci cevapları
- Konfigürasyon dosyaları
- Log dosyaları

## 🐛 Sorun Giderme

### Bağlantı Sorunları

1. **Sunucu başlamıyor:**
   - Port 2121'in kullanımda olmadığını kontrol edin
   - Firewall ayarlarını kontrol edin
   - Yönetici izinleri gerekebilir

2. **İstemci bağlanamıyor:**
   - `ip.txt` dosyasındaki IP adresini kontrol edin
   - Sunucunun çalıştığından emin olun
   - Ağ bağlantısını kontrol edin

### Dosya Sorunları

1. **Dosya yüklenmiyor:**
   - Dosya boyutunu kontrol edin (max 50MB)
   - Dosya uzantısının izinli olduğunu kontrol edin
   - Disk alanını kontrol edin

2. **Soru dosyaları görünmüyor:**
   - `Sorular/` klasörünün var olduğunu kontrol edin
   - Dosya izinlerini kontrol edin

## 📊 Performans İpuçları

1. **Ağ Optimizasyonu:**
   - Buffer boyutunu ağ hızına göre ayarlayın
   - Heartbeat aralığını optimize edin

2. **Dosya Yönetimi:**
   - Büyük dosyalar için chunk boyutunu artırın
   - Eski log dosyalarını düzenli temizleyin

3. **Güvenlik:**
   - Şifre karmaşıklığını artırın
   - IP kilitleme süresini ayarlayın

## 🔄 Güncellemeler

### v2.0 Yenilikleri
- ✅ Gelişmiş güvenlik sistemi
- ✅ Otomatik yeniden bağlanma
- ✅ Dosya bütünlüğü kontrolü
- ✅ Kapsamlı loglama
- ✅ Modern UI tasarımı
- ✅ Konfigürasyon yönetimi

## 📞 Destek

Sorunlarınız için:
1. Log dosyalarını kontrol edin
2. Konfigürasyon ayarlarını gözden geçirin
3. Sistem gereksinimlerini kontrol edin

## 📄 Lisans

Bu proje eğitim amaçlı geliştirilmiştir.

---

**Not:** Bu sistem güvenlik odaklı tasarlanmıştır ancak kritik sınavlar için ek güvenlik önlemleri alınması önerilir.
