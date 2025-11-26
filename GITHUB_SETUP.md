# GitHub'a Proje Yükleme Rehberi

Bu rehber sınav sistemi projesini GitHub'a yüklemek için gerekli adımları içerir.

## 🚀 Hızlı Başlangıç

### 1. Mevcut Repository'yi Temizle

```bash
# Eski dosyaları git'ten kaldır
git rm -r app/game/
git rm -r frontend/
git rm -r tests/
git rm app/main.py
git rm Dockerfile
git rm docker-compose.yml

# Değişiklikleri commit et
git add .
git commit -m "Eski proje dosyalarını kaldır"
```

### 2. Yeni Sınav Sistemi Dosyalarını Ekle

```bash
# Tüm yeni dosyaları ekle
git add .
git commit -m "Sınav sistemi v2.0 - Kapsamlı güvenlik ve özellik güncellemesi"
```

### 3. GitHub'a Push Et

```bash
# Ana branch'e push et
git push origin main
```

## 📋 Detaylı Adımlar

### Adım 1: Repository Durumunu Kontrol Et

```bash
git status
git log --oneline -5
```

### Adım 2: Eski Dosyaları Temizle

```bash
# Silinen dosyaları git'ten kaldır
git add -u

# Yeni dosyaları ekle
git add .

# Durumu kontrol et
git status
```

### Adım 3: Commit Mesajı Hazırla

```bash
git commit -m "feat: Sınav Sistemi v2.0 - Kapsamlı Güvenlik ve Özellik Güncellemesi

✨ Yeni Özellikler:
- Gelişmiş güvenlik sistemi (PBKDF2 hash, IP koruması)
- Otomatik yeniden bağlanma ve heartbeat monitoring
- JSON tabanlı konfigürasyon yönetimi
- Dosya bütünlüğü kontrolü ve güvenli transfer
- Modern kullanıcı arayüzü ve gerçek zamanlı güncellemeler
- Kapsamlı loglama ve aktivite takibi

🔧 Teknik İyileştirmeler:
- Modüler kod yapısı
- Hata toleransı ve exception handling
- Otomatik temizlik sistemi
- Git entegrasyonu ve dokümantasyon

🛡️ Güvenlik:
- Şifre hash'leme ve doğrulama
- Dosya güvenlik taraması
- Yasaklı uygulama engelleme
- IP tabanlı erişim kontrolü

📚 Dokümantasyon:
- Kapsamlı README
- Kurulum ve kullanım rehberi
- Konfigürasyon örnekleri"
```

### Adım 4: Remote Repository Kontrol

```bash
# Remote repository'leri listele
git remote -v

# Eğer remote yoksa ekle
git remote add origin https://github.com/KULLANICI_ADI/REPO_ADI.git

# Eğer farklı bir remote kullanmak istiyorsan
git remote set-url origin https://github.com/KULLANICI_ADI/YENİ_REPO_ADI.git
```

### Adım 5: Push İşlemi

```bash
# İlk push (eğer yeni repo ise)
git push -u origin main

# Normal push
git push origin main
```

## 🔧 Alternatif: Yeni Repository Oluştur

Eğer tamamen yeni bir repository oluşturmak istiyorsan:

### 1. GitHub'da Yeni Repository Oluştur

1. GitHub.com'a git
2. "New repository" butonuna tıkla
3. Repository adını gir (örn: `sinav-sistemi`)
4. Açıklama ekle: "Güvenli Çevrimiçi Sınav Yönetim Sistemi"
5. Public/Private seç
6. README, .gitignore ve license ekleme (zaten var)
7. "Create repository" tıkla

### 2. Mevcut Projeyi Yeni Repository'ye Bağla

```bash
# Mevcut remote'u kaldır
git remote remove origin

# Yeni remote ekle
git remote add origin https://github.com/KULLANICI_ADI/sinav-sistemi.git

# Push et
git push -u origin main
```

## 📝 Commit Mesaj Standartları

### Commit Türleri:
- `feat:` - Yeni özellik
- `fix:` - Bug düzeltmesi
- `docs:` - Dokümantasyon
- `style:` - Kod formatı
- `refactor:` - Kod yeniden düzenleme
- `test:` - Test ekleme/düzeltme
- `chore:` - Bakım işleri

### Örnek Commit Mesajları:
```bash
git commit -m "feat: Otomatik yeniden bağlanma özelliği eklendi"
git commit -m "fix: Dosya yükleme timeout sorunu düzeltildi"
git commit -m "docs: README güncellendi ve kurulum rehberi eklendi"
git commit -m "chore: Gereksiz dosyalar temizlendi"
```

## 🏷️ Tag Oluşturma (Versiyon)

```bash
# Yeni versiyon tag'i oluştur
git tag -a v2.0.0 -m "Sınav Sistemi v2.0.0 - Kapsamlı güvenlik güncellemesi"

# Tag'leri push et
git push origin --tags
```

## 🔒 .gitignore Kontrolü

Proje zaten `.gitignore` dosyası içeriyor. Kontrol et:

```bash
cat .gitignore
```

## 📊 Repository İstatistikleri

Push sonrası GitHub'da:
- Code tab'ında dosyalar görünecek
- README.md otomatik görüntülenecek
- Releases tab'ında versiyonlar olacak
- Issues ve Discussions açılabilir

## 🚨 Önemli Notlar

1. **Güvenlik**: `students.txt` dosyası gerçek şifreler içeriyorsa `.gitignore`'a ekle
2. **Log Dosyaları**: Kişisel bilgi içeren loglar push etme
3. **Konfigürasyon**: Hassas bilgiler için environment variables kullan
4. **Yedekleme**: Push öncesi yerel yedek al

## 🎯 Push Sonrası Yapılacaklar

1. **README Güncelle**: GitHub'da görünümü kontrol et
2. **Issues Oluştur**: Gelecek özellikler için
3. **Wiki Ekle**: Detaylı dokümantasyon için
4. **Actions Kurulum**: CI/CD için (opsiyonel)
5. **License Ekle**: Açık kaynak için

## 📞 Sorun Giderme

### Push Hatası Alırsan:
```bash
# Force push (DİKKATLİ KULLAN)
git push --force-with-lease origin main

# Veya pull sonrası push
git pull origin main --rebase
git push origin main
```

### Büyük Dosya Sorunu:
```bash
# Git LFS kullan
git lfs track "*.pdf"
git add .gitattributes
git commit -m "Git LFS için PDF dosyaları"
```
