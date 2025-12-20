import socket
import threading
import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import logging
import time
from datetime import datetime
import json
from config_manager import get_config
from file_manager import get_secure_file_handler, get_question_file_manager

# Konfigürasyonu yükle
config = get_config()

# --- AYARLAR ---
HOST_IP = config.get("server.host", "0.0.0.0")
CONTROL_PORT = config.get("server.port", 2121)
BUFFER_SIZE = config.get("server.buffer_size", 4096)
FORMAT = "utf-8"
MAX_CONNECTIONS = config.get("server.max_connections", 50)
HEARTBEAT_INTERVAL = config.get("server.heartbeat_interval", 30)
MAX_FILE_SIZE = config.get("server.max_file_size_mb", 50) * 1024 * 1024

# Dizinleri oluştur
for directory in ["Sorular", "Cevaplar", "Logs"]:
    if not os.path.exists(directory): 
        os.makedirs(directory)

# Logging ayarları - config'den al
log_level = getattr(logging, config.get("logging.level", "INFO").upper())
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('Logs/server.log'),
        logging.StreamHandler()
    ]
)

connected_students = {}
student_activities = {}  # Öğrenci aktivitelerini takip

def load_students():
    """Öğrenci veritabanını yükle"""
    students = {}
    try:
        with open("students.txt", "r", encoding="utf-8") as f:
            line_count = 0
            for line in f:
                line_count += 1
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split(":")
                    if len(parts) >= 3:
                        no, password, name = parts[0].strip(), parts[1].strip(), parts[2].strip()
                        if no and password and name:
                            students[no] = {"password": password, "name": name}
                        else:
                            logging.warning(f"Geçersiz öğrenci verisi satır {line_count}: {line}")
                    else:
                        logging.warning(f"Eksik veri satır {line_count}: {line}")
        logging.info(f"{len(students)} öğrenci yüklendi")
    except FileNotFoundError:
        logging.warning("students.txt bulunamadı, varsayılan öğrenciler oluşturuluyor")
        # Varsayılan öğrenci oluştur
        students = {
            "415576": {"password": "123456", "name": "Furkan Barış"},
            "123456": {"password": "password", "name": "Test Öğrenci"}
        }
        # Varsayılan dosyayı oluştur
        try:
            with open("students.txt", "w", encoding="utf-8") as f:
                f.write("# Öğrenci Veritabanı\n")
                f.write("# Format: öğrenci_no:şifre:ad_soyad\n")
                for no, data in students.items():
                    f.write(f"{no}:{data['password']}:{data['name']}\n")
            logging.info("Varsayılan students.txt oluşturuldu")
        except Exception as e:
            logging.error(f"students.txt oluşturulamadı: {e}")
    except Exception as e:
        logging.error(f"Öğrenci veritabanı yükleme hatası: {e}")
        students = {}
    return students

def verify_student(student_no, password):
    """Öğrenci no ve şifre doğrulama"""
    try:
        students = load_students()
        if student_no in students:
            is_valid = students[student_no]["password"] == password
            name = students[student_no]["name"] if is_valid else None
            
            # Aktiviteyi kaydet
            activity = {
                "timestamp": datetime.now().isoformat(),
                "action": "login_attempt",
                "success": is_valid,
                "student_no": student_no
            }
            log_student_activity(student_no, activity)
            
            return is_valid, name
        else:
            logging.warning(f"Bilinmeyen öğrenci numarası: {student_no}")
            return False, None
    except Exception as e:
        logging.error(f"Öğrenci doğrulama hatası: {e}")
        return False, None

def log_student_activity(student_no, activity):
    """Öğrenci aktivitelerini logla"""
    try:
        if student_no not in student_activities:
            student_activities[student_no] = []
        
        student_activities[student_no].append(activity)
        
        # Dosyaya da kaydet
        log_file = f"Logs/student_{student_no}_activity.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{activity['timestamp']} - {activity['action']} - {json.dumps(activity)}\n")
            
    except Exception as e:
        logging.error(f"Aktivite loglama hatası: {e}") 

class TeacherServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Öğretmen Kontrol Paneli - Sınav Sistemi")
        # UI config'den boyutları al
        width = config.get("ui.window_width", 900)
        height = config.get("ui.window_height", 600)
        self.root.geometry(f"{width}x{height}")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.exam_started = False 
        self.exam_time_remaining = 0
        self.timer_running = False
        self.server_running = True
        self.start_time = None
        
        logging.info("Öğretmen kontrol paneli başlatıldı")

        # --- ARAYÜZ ---
        # Üst kontrol paneli
        top_frame = tk.Frame(root, pady=10, bg="#f0f0f0")
        top_frame.pack(side=tk.TOP, fill=tk.X)
        
        # Sol taraf butonlar
        left_buttons = tk.Frame(top_frame, bg="#f0f0f0")
        left_buttons.pack(side=tk.LEFT)
        
        tk.Button(left_buttons, text="🚀 Sınavı Başlat", bg="#d32f2f", fg="white", 
                 font=("Arial", 10, "bold"), command=self.start_exam_timer).pack(side=tk.LEFT, padx=5)
        tk.Button(left_buttons, text="📢 Duyuru Gönder", bg="#2196F3", fg="white", 
                 font=("Arial", 10), command=self.send_broadcast).pack(side=tk.LEFT, padx=5)
        tk.Button(left_buttons, text="🔓 Girişleri Aç", bg="#4CAF50", fg="white",
                 font=("Arial", 10), command=self.unlock_entries).pack(side=tk.LEFT, padx=5)
        tk.Button(left_buttons, text="📊 İstatistikler", bg="#FF9800", fg="white",
                 font=("Arial", 10), command=self.show_statistics).pack(side=tk.LEFT, padx=5)
        
        # Sağ taraf bilgiler
        right_info = tk.Frame(top_frame, bg="#f0f0f0")
        right_info.pack(side=tk.RIGHT)
        
        self.timer_lbl = tk.Label(right_info, text="⏰ Süre: --:--", fg="blue", 
                                 font=("Arial", 12, "bold"), bg="#f0f0f0")
        self.timer_lbl.pack(side=tk.RIGHT, padx=10)
        
        self.status_lbl = tk.Label(right_info, text="✅ Durum: Girişler AÇIK", fg="green", 
                                  font=("Arial", 10, "bold"), bg="#f0f0f0")
        self.status_lbl.pack(side=tk.RIGHT, padx=10)
        
        self.connection_lbl = tk.Label(right_info, text="🌐 Bağlantı: 0 öğrenci", 
                                      fg="blue", font=("Arial", 10), bg="#f0f0f0")
        self.connection_lbl.pack(side=tk.RIGHT, padx=10)

        # Öğrenci listesi frame
        list_frame = tk.Frame(root)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Liste başlığı
        tk.Label(list_frame, text="👥 Bağlı Öğrenciler", font=("Arial", 12, "bold")).pack(anchor="w")
        
        # Treeview ve scrollbar
        tree_frame = tk.Frame(list_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Kolonlar: Öğrenci No, Ad, IP, Durum, Bağlantı Zamanı, Son Aktivite, Teslim Dosyası, Teslim Zamanı
        self.tree = ttk.Treeview(
            tree_frame,
            columns=(
                "No",
                "Ad",
                "IP",
                "Durum",
                "Bağlantı",
                "Son İşlem",
                "Teslim Dosyası",
                "Teslim Zamanı"
            ),
            show='headings'
        )
        self.tree.heading("No", text="Öğrenci No")
        self.tree.heading("Ad", text="Ad Soyad")
        self.tree.heading("IP", text="IP Adresi")
        self.tree.heading("Durum", text="Durum")
        self.tree.heading("Bağlantı", text="Bağlantı Zamanı")
        self.tree.heading("Son İşlem", text="Son Aktivite")
        self.tree.heading("Teslim Dosyası", text="Teslim Dosyası")
        self.tree.heading("Teslim Zamanı", text="Teslim Zamanı")
        
        self.tree.column("No", width=80)
        self.tree.column("Ad", width=140)
        self.tree.column("IP", width=110)
        self.tree.column("Durum", width=90)
        self.tree.column("Bağlantı", width=120)
        self.tree.column("Son İşlem", width=220)
        self.tree.column("Teslim Dosyası", width=160)
        self.tree.column("Teslim Zamanı", width=110)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Sunucu başlatma
        self.server_socket = None
        self.start_server()
        
        # Periyodik güncelleme
        self.update_connection_count()
        
    def start_server(self):
        """Sunucuyu başlat"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((HOST_IP, CONTROL_PORT))
            self.server_socket.listen(MAX_CONNECTIONS)
            
            logging.info(f"Sunucu başlatıldı: {HOST_IP}:{CONTROL_PORT}")
            messagebox.showinfo("Sunucu Başlatıldı", 
                              f"Sınav sunucusu başarıyla başlatıldı!\n\n"
                              f"IP: {HOST_IP}\n"
                              f"Port: {CONTROL_PORT}\n"
                              f"Maksimum bağlantı: {MAX_CONNECTIONS}")
            
            threading.Thread(target=self.accept_clients, daemon=True).start()
            
        except Exception as e:
            error_msg = f"Sunucu başlatılamadı: {e}\n\nMuhtemel nedenler:\n• Port {CONTROL_PORT} zaten kullanımda\n• Yönetici izni gerekli\n• Ağ bağlantısı sorunu"
            logging.error(error_msg)
            messagebox.showerror("Sunucu Hatası", error_msg)
            self.root.destroy()
    
    def update_connection_count(self):
        """Bağlantı sayısını güncelle"""
        if self.server_running:
            count = len(connected_students)
            self.connection_lbl.config(text=f"🌐 Bağlantı: {count} öğrenci")
            self.root.after(5000, self.update_connection_count)  # 5 saniyede bir güncelle
    
    def show_statistics(self):
        """İstatistikleri göster"""
        stats_window = tk.Toplevel(self.root)
        stats_window.title("📊 Sınav İstatistikleri")
        stats_window.geometry("500x400")
        
        stats_text = tk.Text(stats_window, wrap=tk.WORD, padx=10, pady=10)
        stats_text.pack(fill=tk.BOTH, expand=True)
        
        # İstatistikleri hazırla
        total_students = len(load_students())
        connected_count = len(connected_students)

        
        
        # Başlangıç zamanını gösterilebilir formata çevir
        start_time_display = self.start_time if self.start_time else "Henüz başlamadı"
        
        stats_content = f"""📊 SINAV SİSTEMİ İSTATİSTİKLERİ
{'='*50}

👥 Öğrenci Bilgileri:
• Toplam kayıtlı öğrenci: {total_students}
• Şu anda bağlı: {connected_count}
• Bağlantı oranı: %{(connected_count/total_students*100) if total_students > 0 else 0:.1f}

⏰ Sınav Durumu:
• Sınav durumu: {'BAŞLADI' if self.exam_started else 'BAŞLAMADI'}
• Kalan süre: {self.exam_time_remaining//60:02d}:{self.exam_time_remaining%60:02d}
• Başlangıç zamanı: {start_time_display}

📁 Dosya Durumu:
• Soru dosyası sayısı: {len(os.listdir('Sorular')) if os.path.exists('Sorular') else 0}
• Teslim edilen cevap: {len(os.listdir('Cevaplar')) if os.path.exists('Cevaplar') else 0}

🔗 Bağlantı Detayları:"""
        
        for student_no, data in connected_students.items():
            stats_content += f"\n• {student_no} ({data.get('name', 'Bilinmiyor')}) - {data['addr'][0]}"
        
        stats_text.insert(tk.END, stats_content)
        stats_text.config(state=tk.DISABLED)
    
    def on_closing(self):
        """Uygulama kapatılırken"""
        if messagebox.askokcancel("Çıkış", "Sınav sunucusunu kapatmak istediğinizden emin misiniz?"):
            self.server_running = False
            logging.info("Sunucu kapatılıyor...")
            
            # Tüm öğrencilere bildir
            for student_no, data in connected_students.items():
                try:
                    data["conn"].send("CMD:MSG:Sunucu kapatılıyor. Lütfen çalışmanızı kaydedin!".encode(FORMAT))
                except:
                    pass
            
            try:
                self.server_socket.close()
            except:
                pass
            
            self.root.destroy()

    def accept_clients(self):
        """Yeni istemci bağlantılarını kabul et"""
        while self.server_running:
            try:
                conn, addr = self.server_socket.accept()
                logging.info(f"Yeni bağlantı: {addr[0]}:{addr[1]}")
                threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
            except Exception as e:
                if self.server_running:  # Sadece sunucu çalışıyorsa hata logla
                    logging.error(f"Bağlantı kabul hatası: {e}")
                break

    def handle_client(self, conn, addr):
        """İstemci bağlantısını yönet"""
        student_no = "Bilinmiyor"
        student_name = "Bilinmiyor"
        connection_time = datetime.now().strftime("%H:%M:%S")
        
        try:
            # Hoşgeldin mesajı
            welcome_msg = "220 Sinav Sunucusu Hazir.\n"
            conn.send(welcome_msg.encode(FORMAT))
            logging.info(f"Yeni bağlantı kuruldu: {addr[0]}:{addr[1]}")
            
            conn.settimeout(300)  # 5 dakika timeout
            
            while self.server_running:
                try:
                    data = conn.recv(BUFFER_SIZE).decode(FORMAT).strip()
                    if not data: 
                        logging.info(f"Boş veri alındı, bağlantı kapatılıyor: {addr[0]}")
                        break
                        
                    parts = data.split(" ")
                    cmd = parts[0].upper()
                    
                    logging.info(f"{student_no} ({addr[0]}) komutu: {cmd}")

                    if cmd == "LOGIN":
                        if self.exam_started:
                            conn.send("550 SINAV_BASLADI_GIRIS_YASAK\n".encode(FORMAT))
                            logging.warning(f"Sınav sırasında giriş denemesi: {addr[0]}")
                            break
                        
                        if len(parts) < 3:
                            conn.send("530 Eksik bilgi. LOGIN <no> <sifre>\n".encode(FORMAT))
                            continue
                            
                        student_no = parts[1].strip()
                        password = parts[2].strip()
                        
                        # Zaten bağlı mı kontrol et
                        if student_no in connected_students:
                            conn.send("550 ZATEN_BAGLI\n".encode(FORMAT))
                            logging.warning(f"Zaten bağlı öğrenci giriş denemesi: {student_no}")
                            break
                        
                        # Şifre doğrulama
                        is_valid, student_name = verify_student(student_no, password)
                        
                        if is_valid:
                            connected_students[student_no] = {
                                "conn": conn, 
                                "addr": addr, 
                                "name": student_name,
                                "login_time": connection_time,
                                "last_activity": datetime.now(),
                                "delivery_file": "",
                                "delivery_time": ""
                            }
                            conn.send("230 Giris Basarili\n".encode(FORMAT))
                            
                            activity_msg = f"Giriş Yaptı ({student_name})"
                            self.update_ui_list(student_no, student_name, addr[0], "Aktif", connection_time, activity_msg)
                            
                            logging.info(f"Başarılı giriş: {student_no} - {student_name}")
                            
                            # Eğer sınav başlamışsa timer gönder
                            if self.exam_started and self.timer_running:
                                try:
                                    sync_msg = f"CMD:SYNC:{self.exam_time_remaining}\n"
                                    conn.send(sync_msg.encode(FORMAT))
                                    logging.info(f"Sınav timer gönderildi: {student_no}")
                                except Exception as e:
                                    logging.error(f"Timer gönderme hatası: {e}")
                        else:
                            conn.send("530 Hatali numara veya sifre\n".encode(FORMAT))
                            logging.warning(f"Yanlış giriş denemesi: {student_no} from {addr[0]}")

                    elif cmd == "LIST":
                        if student_no == "Bilinmiyor":
                            conn.send("530 Once giris yapin\n".encode(FORMAT))
                            continue
                            
                        try:
                            # Use QuestionFileManager to list files
                            question_manager = get_question_file_manager()
                            files_info = question_manager.list_question_files()
                            files = [f["filename"] for f in files_info]
                            files_str = ",".join(files) if files else ""
                            conn.send(f"DATA_LIST:{files_str}\n".encode(FORMAT))
                            
                            self.update_ui_list(
                                student_no,
                                student_name,
                                addr[0],
                                "Aktif",
                                connection_time,
                                f"Sorular listelendi ({len(files)} dosya)"
                            )
                            
                            # Aktiviteyi güncelle
                            if student_no in connected_students:
                                connected_students[student_no]["last_activity"] = datetime.now()
                                
                        except Exception as e:
                            logging.error(f"Dosya listeleme hatası: {e}")
                            conn.send("550 Dosya listesi alinamadi\n".encode(FORMAT))

                    elif cmd == "STOR":
                        if student_no == "Bilinmiyor":
                            conn.send("530 Once giris yapin\n".encode(FORMAT))
                            continue
                            
                        # GÜVENLİK KONTROLÜ
                        if not self.exam_started:
                            conn.send("550 SINAV_BASLAMADI_YUKLEME_YASAK\n".encode(FORMAT))
                            logging.warning(f"Sınav başlamadan yükleme denemesi: {student_no}")
                            continue

                        if len(parts) < 3:
                            conn.send("550 Eksik parametre\n".encode(FORMAT))
                            continue
                            
                        try:
                            filename = parts[1]
                            filesize = int(parts[2])
                            
                            # Dosya boyutu kontrolü
                            max_size_mb = config.get("server.max_file_size_mb", 50)
                            if filesize > max_size_mb * 1024 * 1024:
                                conn.send(f"550 Dosya cok buyuk (max {max_size_mb}MB)\n".encode(FORMAT))
                                continue
                                
                            conn.send("READY_TO_UPLOAD\n".encode(FORMAT))
                            
                            # Yükleme başladığında mevcut teslim bilgilerini koru
                            current_delivery_file = ""
                            current_delivery_time = ""
                            if student_no in connected_students:
                                current_delivery_file = connected_students[student_no].get("delivery_file", "")
                                current_delivery_time = connected_students[student_no].get("delivery_time", "")
                            
                            self.update_ui_list(
                                student_no,
                                student_name,
                                addr[0],
                                "Yüklüyor",
                                connection_time,
                                f"{filename} yükleniyor... ({filesize} bytes)",
                                current_delivery_file,
                                current_delivery_time
                            )
                            
                            # Use SecureFileHandler to receive and save file
                            secure_handler = get_secure_file_handler()
                            
                            # Receive file data
                            received = 0
                            file_data_chunks = []
                            while received < filesize:
                                remaining = filesize - received
                                chunk_size = min(BUFFER_SIZE, remaining)
                                chunk = conn.recv(chunk_size)
                                if not chunk: 
                                    break
                                file_data_chunks.append(chunk)
                                received += len(chunk)
                            
                            if received == filesize:
                                # Combine all chunks
                                file_data = b''.join(file_data_chunks)
                                
                                # Save file securely using SecureFileHandler
                                success, save_path, safe_filename = secure_handler.save_file_securely(
                                    file_data, 
                                    student_no, 
                                    filename
                                )
                                
                                if success:
                                    conn.send("226 Transfer tamamlandi\n".encode(FORMAT))
                                    
                                    # Teslim bilgilerini güncelle
                                    delivery_time = datetime.now().strftime("%H:%M:%S")
                                    if student_no in connected_students:
                                        connected_students[student_no]["delivery_file"] = filename
                                        connected_students[student_no]["delivery_time"] = delivery_time
                                    
                                    self.update_ui_list(
                                        student_no,
                                        student_name,
                                        addr[0],
                                        "TESLİM EDİLDİ",
                                        connection_time,
                                        f"CEVAP TESLİM EDİLDİ: {filename}",
                                        filename,
                                        delivery_time
                                    )
                                    logging.info(f"Dosya başarıyla alındı: {student_no} - {safe_filename} (güvenli kayıt)")
                                    
                                    # Aktiviteyi kaydet
                                    activity = {
                                        "timestamp": datetime.now().isoformat(),
                                        "action": "file_upload",
                                        "filename": filename,
                                        "filesize": filesize,
                                        "student_no": student_no,
                                        "saved_filename": safe_filename
                                    }
                                    log_student_activity(student_no, activity)
                                else:
                                    conn.send("550 Dosya kaydetme hatasi\n".encode(FORMAT))
                                    logging.error(f"Dosya kaydetme başarısız: {safe_filename}")
                            else:
                                conn.send("550 Transfer yarim kaldi\n".encode(FORMAT))
                                logging.error(f"Eksik transfer: {received}/{filesize} bytes")
                                
                        except ValueError:
                            conn.send("550 Gecersiz dosya boyutu\n".encode(FORMAT))
                        except Exception as e:
                            logging.error(f"Dosya yükleme hatası: {e}")
                            conn.send("550 Yukleme hatasi\n".encode(FORMAT))
                    
                    elif cmd == "RETR":
                        if student_no == "Bilinmiyor":
                            conn.send("550 Once giris yapin\n".encode(FORMAT))
                            continue
                        
                        # GÜVENLİK KONTROLÜ - Sınav başlamadan dosya indirilemez
                        if not self.exam_started:
                            conn.send("550 SINAV_BASLAMADI_INDIRME_YASAK\n".encode(FORMAT))
                            logging.warning(f"Sınav başlamadan indirme denemesi: {student_no}")
                            continue
                        
                        if len(parts) < 2:
                            conn.send("550 Eksik parametre (dosya adı gerekli)\n".encode(FORMAT))
                            continue
                        
                        try:
                            filename = parts[1]
                            
                            # Use QuestionFileManager to get file content
                            question_manager = get_question_file_manager()
                            file_data = question_manager.get_file_content(filename)
                            
                            if file_data is None:
                                conn.send("550 Dosya bulunamadi\n".encode(FORMAT))
                                logging.warning(f"Dosya bulunamadı: {filename} (öğrenci: {student_no})")
                                continue
                            
                            # Dosya boyutunu al
                            filesize = len(file_data)
                            
                            # İndirmeye hazır olduğunu bildir
                            ready_msg = f"READY {filesize}\n".encode(FORMAT)
                            conn.send(ready_msg)
                            logging.info(f"READY mesajı gönderildi: {filename} ({filesize} bytes)")
                            
                            # Aktiviteyi güncelle
                            if student_no in connected_students:
                                connected_students[student_no]["last_activity"] = datetime.now()
                            
                            self.update_ui_list(
                                student_no,
                                student_name,
                                addr[0],
                                "İndiriyor",
                                connection_time,
                                f"{filename} indiriliyor... ({filesize} bytes)"
                            )
                            
                            # Çok kısa bir bekleme - istemcinin READY mesajını işlemesi için
                            # Ama çok uzun olmamalı, yoksa istemci timeout olabilir
                            time.sleep(0.05)  # 50ms yeterli
                            
                            # Dosyayı gönder
                            sent = 0
                            try:
                                while sent < filesize:
                                    remaining = filesize - sent
                                    chunk_size = min(BUFFER_SIZE, remaining)
                                    chunk = file_data[sent:sent + chunk_size]
                                    if not chunk:
                                        break
                                    conn.sendall(chunk)
                                    sent += len(chunk)
                                    
                                    # Büyük dosyalar için ilerleme logla
                                    if filesize > 1024 * 1024 and sent % (1024 * 1024) == 0:  # Her MB'da bir
                                        logging.info(f"Dosya gönderiliyor: {sent}/{filesize} bytes ({sent*100//filesize}%)")
                                
                                if sent == filesize:
                                    # Transfer tamamlandı mesajını gönder
                                    conn.send("226 Transfer tamamlandi\n".encode(FORMAT))
                                    logging.info(f"Dosya başarıyla gönderildi: {student_no} - {filename} ({filesize} bytes)")
                            except Exception as send_error:
                                logging.error(f"Dosya gönderme hatası: {send_error}")
                                raise
                                
                                self.update_ui_list(
                                    student_no,
                                    student_name,
                                    addr[0],
                                    "Aktif",
                                    connection_time,
                                    f"{filename} indirildi"
                                )
                                
                                logging.info(f"Dosya başarıyla gönderildi: {student_no} - {filename} ({filesize} bytes)")
                                
                                # Aktiviteyi kaydet
                                activity = {
                                    "timestamp": datetime.now().isoformat(),
                                    "action": "file_download",
                                    "filename": filename,
                                    "filesize": filesize,
                                    "student_no": student_no
                                }
                                log_student_activity(student_no, activity)
                            else:
                                conn.send("550 Transfer yarim kaldi\n".encode(FORMAT))
                                logging.error(f"Eksik transfer: {sent}/{filesize} bytes")
                                
                        except Exception as e:
                            logging.error(f"Dosya indirme hatası: {e}")
                            conn.send("550 Indirme hatasi\n".encode(FORMAT))
                    
                    elif cmd == "PING":
                        conn.send("PONG\n".encode(FORMAT))
                        if student_no in connected_students:
                            connected_students[student_no]["last_activity"] = datetime.now()
                    
                    else:
                        conn.send("500 Bilinmeyen komut\n".encode(FORMAT))
                        logging.warning(f"Bilinmeyen komut: {cmd} from {student_no}")
                        
                except socket.timeout:
                    logging.warning(f"Bağlantı zaman aşımı: {student_no} ({addr[0]})")
                    break
                except Exception as e:
                    logging.error(f"Komut işleme hatası: {e}")
                    break

        except Exception as e:
            logging.error(f"İstemci yönetim hatası: {e}")
        finally:
            # Temizlik
            try: 
                conn.close()
            except: 
                pass
                
            if student_no != "Bilinmiyor" and student_no in connected_students:
                # Son teslim bilgilerini al
                delivery_file = connected_students[student_no].get("delivery_file", "")
                delivery_time = connected_students[student_no].get("delivery_time", "")
                del connected_students[student_no]
                self.update_ui_list(
                    student_no,
                    student_name,
                    addr[0],
                    "Çevrimdışı",
                    connection_time,
                    "Bağlantı Koptu",
                    delivery_file,
                    delivery_time
                )
                logging.info(f"Bağlantı kapatıldı: {student_no} ({addr[0]})")

    def start_exam_timer(self):
        mins = simpledialog.askinteger("Süre", "Sınav süresi kaç dakika?")
        if mins:
            self.exam_started = True
            self.exam_time_remaining = mins * 60
            # Sınav başlangıç zamanını kaydet
            self.start_time = datetime.now().strftime("%H:%M:%S")
            self.timer_running = True
            self.status_lbl.config(text="Durum: SINAV BAŞLADI", fg="red")
            
            total_seconds = mins * 60
            for s_no, data in connected_students.items():
                try: 
                    data["conn"].send(f"CMD:TIME_SECONDS:{total_seconds}\n".encode(FORMAT))
                except: pass
            
            self.update_server_timer()

    def update_server_timer(self):
        if self.timer_running and self.exam_time_remaining > 0:
            mins, secs = divmod(self.exam_time_remaining, 60)
            self.timer_lbl.config(text=f"Süre: {mins:02}:{secs:02}", fg="red")
            
            if self.exam_time_remaining % 30 == 0:
                for s_no, data in connected_students.items():
                    try: 
                        data["conn"].send(f"CMD:SYNC:{self.exam_time_remaining}\n".encode(FORMAT))
                    except: pass
            
            self.exam_time_remaining -= 1
            self.root.after(1000, self.update_server_timer)
        elif self.timer_running and self.exam_time_remaining <= 0:
            self.timer_lbl.config(text="Süre: 00:00", fg="red")
            self.timer_running = False
            messagebox.showinfo("Sınav Bitti", "Sınav süresi doldu!")
            for s_no, data in connected_students.items():
                try: data["conn"].send("CMD:TIME_UP\n".encode(FORMAT))
                except: pass

    def unlock_entries(self):
        self.exam_started = False
        self.timer_running = False
        self.exam_time_remaining = 0
        self.status_lbl.config(text="Durum: Girişler AÇIK", fg="green")
        self.timer_lbl.config(text="Süre: --:--", fg="blue")

    def send_broadcast(self):
        msg = simpledialog.askstring("Duyuru", "Mesaj:")
        if msg:
            for s_no, data in connected_students.items():
                try: data["conn"].send(f"CMD:MSG:{msg}\n".encode(FORMAT))
                except: pass

    def update_ui_list(self, no, name, ip, status, connection_time, action, delivery_file=None, delivery_time=None):
        """UI listesini güncelle"""
        self.root.after(
            0,
            lambda: self._update_tree_safe(
                no,
                name,
                ip,
                status,
                connection_time,
                action,
                delivery_file,
                delivery_time,
            ),
        )
    
    def _update_tree_safe(self, no, name, ip, status, connection_time, action, delivery_file=None, delivery_time=None):
        """Thread-safe UI güncellemesi"""
        str_no = str(no).strip()
        found_item = None
        
        # Mevcut kaydı bul
        for item in self.tree.get_children():
            item_vals = self.tree.item(item)['values']
            if len(item_vals) > 0 and str(item_vals[0]).strip() == str_no:
                found_item = item
                break
        
        # Mevcut teslim bilgilerini doldur (gönderilmemişse)
        if delivery_file is None and str_no in connected_students:
            delivery_file = connected_students[str_no].get("delivery_file", "")
        if delivery_time is None and str_no in connected_students:
            delivery_time = connected_students[str_no].get("delivery_time", "")
        
        # Zaman damgası ekle
        timestamp = datetime.now().strftime("%H:%M:%S")
        action_with_time = f"[{timestamp}] {action}"
        
        if found_item:
            # Mevcut kaydı güncelle
            self.tree.item(
                found_item,
                values=(
                    str_no,
                    name,
                    ip,
                    status,
                    connection_time,
                    action_with_time,
                    delivery_file or "",
                    delivery_time or "",
                ),
            )
        else:
            # Yeni kayıt ekle
            self.tree.insert(
                "",
                "end",
                values=(
                    str_no,
                    name,
                    ip,
                    status,
                    connection_time,
                    action_with_time,
                    delivery_file or "",
                    delivery_time or "",
                ),
            )

if __name__ == "__main__":
    root = tk.Tk()
    app = TeacherServerGUI(root)
    root.mainloop()