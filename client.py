import socket
import threading
import os
import time
import tkinter as tk
from tkinter import messagebox, filedialog
from tkinter import ttk
import sys
import logging
import queue
from datetime import datetime
from config_manager import get_config
from security_manager import SecurityManager
from client_transfer import ClientTransferHandler
try:
    import winsound
except ImportError:
    winsound = None

# Konfigürasyonu yükle
config = get_config()

# --- AYARLAR ---
# Önce ip.txt dosyasını kontrol et 
SERVER_IP = config.get("client.server_ip", "127.0.0.1")
if os.path.exists("ip.txt"):
    with open("ip.txt", "r") as f: 
        ip_from_file = f.read().strip()
        if ip_from_file:
            SERVER_IP = ip_from_file

CONTROL_PORT = config.get("server.port", 2121)
DATA_PORT = config.get("server.data_port", 2122)
BUFFER_SIZE = config.get("server.buffer_size", 4096)
FORMAT = "utf-8"
RECONNECT_ATTEMPTS = config.get("client.reconnect_attempts", 5)
RECONNECT_DELAY = config.get("client.reconnect_delay", 3)

# Logging ayarları - config'den al
log_level = getattr(logging, config.get("logging.level", "INFO").upper())

# Mevcut logger'ları temizle (birden fazla handler eklenmesini önlemek için)
root_logger = logging.getLogger()
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# File handler oluştur (append mode)
file_handler = logging.FileHandler('Logs/client.log', mode='a', encoding='utf-8')
file_handler.setLevel(log_level)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Console handler oluştur
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Logger'ı yapılandır
root_logger.setLevel(log_level)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logging.info("="*50)
logging.info("Sınav sistemi client başlatıldı")
logging.info(f"Log seviyesi: {log_level}")
logging.info(f"Log dosyası: Logs/client.log")

class SinavClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Sınav Sistemi - Öğrenci")
        width = config.get("ui.window_width", 600)
        height = config.get("ui.window_height", 500)
        self.root.geometry(f"{width}x{height}")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close) 
        self.app_running = True
        banned_apps = config.get("security.banned_applications", 
                                 ["chrome.exe", "firefox.exe", "msedge.exe", "opera.exe", "brave.exe"])
        self.security_manager = SecurityManager(banned_apps)
        self.security_manager.start_monitoring(lambda: self.app_running)

        self.control_socket = None
        self.is_connected = False
        self.student_no = ""
        self.exam_started = False
        self.reconnect_attempts = 0
        self.last_heartbeat = time.time()
        # Upload progress UI state
        self.upload_progress_window = None
        self.upload_progress_var = tk.DoubleVar(value=0.0)
        self.upload_progress_label = None
        # Sınav süresi uyarıları için state
        self.one_minute_warned = False
        self.time_up_shutdown_called = False  # Sınav bitiş bildirimi için flag
        # READY mesajı için queue 
        self.ready_queue = queue.Queue()
        
        logging.info("Sınav sistemi başlatıldı")
        # Initialize transfer handler (will be set after connection)
        self.transfer_handler = None
        self.setup_login_ui()
        self.connect_to_server()

    def connect_to_server(self):
        """Sunucuya bağlanma"""
        for attempt in range(RECONNECT_ATTEMPTS):
            try:
                if self.control_socket:
                    try:
                        self.control_socket.close()
                    except:
                        pass
                
                self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.control_socket.settimeout(10)  # 10 saniye timeout
                self.control_socket.connect((SERVER_IP, CONTROL_PORT))
                
                welcome_msg = self.control_socket.recv(BUFFER_SIZE).decode(FORMAT)
                logging.info(f"Sunucuya bağlandı: {welcome_msg.strip()}")
                
                self.is_connected = True
                self.reconnect_attempts = 0
                self.last_heartbeat = time.time()
                
                # Initialize transfer handler
                self.transfer_handler = ClientTransferHandler(self.control_socket, SERVER_IP, BUFFER_SIZE)
                
                if hasattr(self, 'status_label'): 
                    self.status_label.config(text="Sunucuya Bağlandı ✓", fg="green")
                
                # Heartbeat başlat
                threading.Thread(target=self.heartbeat_monitor, daemon=True).start()
                return True
                
            except Exception as e:
                logging.warning(f"Bağlantı denemesi {attempt + 1}/{RECONNECT_ATTEMPTS} başarısız: {e}")
                if hasattr(self, 'status_label'):
                    self.status_label.config(text=f"Bağlantı denemesi {attempt + 1}/{RECONNECT_ATTEMPTS}...", fg="orange")
                
                if attempt < RECONNECT_ATTEMPTS - 1:
                    time.sleep(RECONNECT_DELAY)
        
        # Tüm denemeler başarısız
        logging.error("Sunucuya bağlanılamadı - tüm denemeler başarısız")
        messagebox.showerror("Bağlantı Hatası", 
                           f"Sunucuya bağlanılamadı!\n\n"
                           f"Sunucu IP: {SERVER_IP}:{CONTROL_PORT}\n"
                           f"Lütfen:\n"
                           f"• Sunucunun çalıştığından emin olun\n"
                           f"• Ağ bağlantınızı kontrol edin\n"
                           f"• IP adresinin doğru olduğunu kontrol edin")
        self.root.destroy()
        sys.exit()
        return False

    
    def heartbeat_monitor(self):
        """Sunucu bağlantısını kontrol eden heartbeat"""
        while self.app_running and self.is_connected:
            try:
                # Her 30 saniyede bir ping gönder
                if time.time() - self.last_heartbeat > 30:
                    self.control_socket.send("PING".encode(FORMAT))
                    self.last_heartbeat = time.time()
                time.sleep(10)
            except Exception as e:
                logging.error(f"Heartbeat hatası: {e}")
                self.handle_connection_lost()
                break
    
    def handle_connection_lost(self):
        """Bağlantı koptuğunda yeniden bağlanmaya çalış"""
        if not self.app_running:
            return
            
        self.is_connected = False
        logging.warning("Sunucu bağlantısı koptu, yeniden bağlanmaya çalışılıyor...")
        
        if hasattr(self, 'status_label'):
            self.status_label.config(text="Bağlantı koptu, yeniden bağlanıyor...", fg="red")
        
        # Yeniden bağlanmaya çalış
        if self.connect_to_server():
            # Başarılı bağlantı sonrası listener'ı yeniden başlat
            if hasattr(self, 'file_listbox'):
                threading.Thread(target=self.server_listener, daemon=True).start()

    def setup_login_ui(self):
        for w in self.root.winfo_children(): w.destroy()
        f = tk.Frame(self.root, padx=20, pady=20)
        f.place(relx=0.5, rely=0.5, anchor="center")
        
        tk.Label(f, text="ÖĞRENCİ GİRİŞİ", font=("Arial", 16)).pack(pady=10)
        tk.Label(f, text="Numara:").pack(anchor="w")
        self.entry_no = tk.Entry(f, width=30); self.entry_no.pack(pady=5)
        tk.Label(f, text="Şifre:").pack(anchor="w")
        self.entry_pw = tk.Entry(f, width=30, show="*"); self.entry_pw.pack(pady=5)
        self.status_label = tk.Label(f, text="Bağlanıyor...", fg="grey"); self.status_label.pack()
        tk.Button(f, text="GİRİŞ", command=self.handle_login, bg="#4CAF50", fg="white", width=20).pack(pady=10)

    def setup_main_ui(self):
        for w in self.root.winfo_children(): w.destroy()
        
        info_frame = tk.Frame(self.root, bg="#eee", pady=10)
        info_frame.pack(fill="x")
        tk.Label(info_frame, text=f"Öğrenci: {self.student_no}", font=("Arial", 12, "bold"), bg="#eee").pack(side="left", padx=10)
        self.timer_label = tk.Label(info_frame, text="Süre: Bekliyor...", font=("Arial", 14, "bold"), fg="blue", bg="#eee")
        self.timer_label.pack(side="right", padx=10)

        tk.Label(self.root, text="SINAV DOSYALARI", font=("Arial", 10)).pack(pady=5)
        
        list_frame = tk.Frame(self.root)
        list_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        self.file_listbox = tk.Listbox(list_frame, height=15)
        self.file_listbox.pack(side="left", fill="both", expand=True)
        
        btn_frame = tk.Frame(self.root, pady=10)
        btn_frame.pack(fill="x", padx=20)

        tk.Button(btn_frame, text="Listeyi Yenile", command=self.refresh_list).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Seçili Dosyayı İNDİR", command=self.download_and_open, bg="#2196F3", fg="white").pack(side="left", padx=5)
        
        # UPLOAD BUTONU (Başlangıçta KAPALI)
        self.upload_btn = tk.Button(btn_frame, text="DOSYA YÜKLE / TESLİM ET", command=self.select_and_upload, bg="#FF5722", fg="white", height=2)
        self.upload_btn.pack(side="right", padx=5)
        self.upload_btn.config(state="disabled", bg="gray", text="SINAVIN BAŞLAMASINI BEKLEYİN")

        self.start_listener()
        self.refresh_list()

    def start_listener(self):
        threading.Thread(target=self.server_listener, daemon=True).start()

    def server_listener(self):
        """Sunucudan gelen komutları dinleme - uses command dispatcher"""
        # Command dispatcher dictionary
        cmd_handlers = {
            "CMD:MSG:": self._handle_cmd_msg,
            "CMD:TIME_SECONDS:": self._handle_cmd_time_seconds,
            "CMD:SYNC:": self._handle_cmd_sync,
            "CMD:TIME_UP": self._handle_cmd_time_up,
            "PONG": lambda d: None,  # Heartbeat response
        }
        
        while self.app_running and self.is_connected:
            try:
                self.control_socket.settimeout(1.0)
                raw_data = self.control_socket.recv(BUFFER_SIZE).decode(FORMAT)
                
                if not raw_data: 
                    logging.warning("Sunucudan boş veri geldi, bağlantı kopmuş olabilir")
                    self.handle_connection_lost()
                    break
                
                self.last_heartbeat = time.time()
                commands = raw_data.split("\n")
                
                for data in commands:
                    data = data.strip()
                    if not data: 
                        continue
                    
                    # Queue 227 and READY messages for transfer threads
                    if data.startswith("227") or data.startswith("READY"):
                        logging.info(f"{data[:5]} mesajı server_listener tarafından yakalandı ve queue'ya eklendi: {data}")
                        try:
                            self.ready_queue.put_nowait(data)
                        except queue.Full:
                            logging.warning(f"{data[:5]} queue dolu, eski mesaj atlanıyor")
                        continue
                    
                    logging.info(f"Sunucudan komut alındı: {data}")
                    
                    # Use command dispatcher
                    handled = False
                    for cmd_prefix, handler in cmd_handlers.items():
                        if data.startswith(cmd_prefix):
                            handler(data)
                            handled = True
                            break
                    
                    if not handled:
                        logging.debug(f"Komut işlenmedi (bilinmeyen): {data}")
                        
            except socket.timeout:
                continue
            except Exception as e:
                logging.error(f"Server listener hatası: {e}")
                self.handle_connection_lost()
                break
    
    def _handle_cmd_msg(self, data: str):
        """Handle CMD:MSG: command"""
        msg = data.split("CMD:MSG:", 1)[1]
        self.root.after(0, lambda m=msg: messagebox.showinfo("DUYURU", m))
    
    def _handle_cmd_time_seconds(self, data: str):
        """Handle CMD:TIME_SECONDS: command"""
        try:
            seconds = int(data.split(":")[2])
            self.root.after(0, self.activate_exam_mode)
            self.root.after(0, lambda s=seconds: self.start_countdown(s))
        except (ValueError, IndexError) as e:
            logging.error(f"Zaman parse hatası: {e}")
    
    def _handle_cmd_sync(self, data: str):
        """Handle CMD:SYNC: command"""
        try:
            server_time = int(data.split(":")[2])
            self.root.after(0, self.activate_exam_mode)
            self.root.after(0, lambda s=server_time: self.start_countdown(s))
        except (ValueError, IndexError) as e:
            logging.error(f"Sync parse hatası: {e}")
    
    def _handle_cmd_time_up(self, data: str):
        """Handle CMD:TIME_UP command"""
        if not self.time_up_shutdown_called:
            self.root.after(0, self.time_up_shutdown)

    def start_countdown(self, seconds):
        if seconds >= 0:
            mins, secs = divmod(seconds, 60)
            color = "red" if seconds <= 300 else "orange" if seconds <= 600 else "green"
            self.timer_label.config(text=f"Süre: {mins:02}:{secs:02}", fg=color)
            
            # Sınavın bitmesine 1 dakika kala popup + ses uyarısı (her sınavda sadece 1 kez)
            if seconds == 60 and not self.one_minute_warned:
                self.one_minute_warned = True
                self.root.after(0, self.show_one_minute_warning)
            
            if self.app_running:
                self.root.after(1000, lambda: self.start_countdown(seconds - 1))
        else:
            # Sınav süresi doldu
            if not self.time_up_shutdown_called:
                self.time_up_shutdown()

    def show_one_minute_warning(self):
        """Sınav bitimine 1 dakika kala uyarı ve ses"""
        try:
            if winsound:
                # Basit uyarı sesi (Windows'ta çalışır)
                winsound.Beep(1000, 700)
        except Exception as e:
            logging.error(f"Ses çalma hatası: {e}")
        try:
            messagebox.showwarning("Süre Uyarısı", "Sınavın bitmesine 1 dakika kaldı!")
        except Exception as e:
            logging.error(f"Uyarı penceresi gösterilemedi: {e}")

    def activate_exam_mode(self):
        """Sınav modunu aktif et - buton ve durumu güncelle"""
        if not self.exam_started:
            self.exam_started = True
            # Yeni sınav başlarken 1 dakika uyarı durumunu sıfırla
            self.one_minute_warned = False
            # Sınav bitiş flag'ini de sıfırla (yeni sınav için)
            self.time_up_shutdown_called = False
            try:
                self.upload_btn.config(state="normal", bg="#FF5722", text="DOSYA YÜKLE / TESLİM ET")
            except Exception as e:
                print(f"Button activation error: {e}")

    def handle_login(self):
        """Kullanıcı girişi işlemi"""
        no = self.entry_no.get().strip()
        pw = self.entry_pw.get().strip()

        # 1. Temel Kontroller (Validation)
        if not no or not pw:
            messagebox.showwarning("Uyarı", "Geçerli bir öğrenci numarası ve şifre giriniz!")
            return
        
        if not no.isdigit():
            messagebox.showwarning("Uyarı", "Öğrenci numarası sadece rakamlardan oluşmalıdır!")
            return
        
        if not self.is_connected:
            messagebox.showerror("Hata", "Sunucuya bağlı değilsiniz!")
            return

        try:
            # 2. Komut Gönderme Yardımcısı (İç fonksiyon)
            def send_and_get(cmd):
                self.control_socket.send(f"{cmd}\n".encode(FORMAT))
                self.control_socket.settimeout(10.0)
                return self.control_socket.recv(BUFFER_SIZE).decode(FORMAT).strip()

            # 3. USER ve PASS Süreci
            resp_user = send_and_get(f"USER {no}")
            logging.info(f"USER {no} -> {resp_user}")

            if "331" in resp_user:  # Şifre bekliyor
                resp_pass = send_and_get(f"PASS {pw}")
                logging.info(f"PASS -> {resp_pass}")
                resp = resp_pass
            else:
                resp = resp_user

            # 4. Yanıt Analizi (Tek merkezden kontrol)
            if "230" in resp:  # Başarılı
                self.student_no = no
                logging.info(f"Başarılı giriş: {no}")
                messagebox.showinfo("Başarılı", f"Hoşgeldiniz {no}!\n\nSınav sistemi hazırlanıyor...")
                self.setup_main_ui()
            elif "550" in resp:  # Sınav başladı engeli
                messagebox.showerror("Giriş Yasak", 
                                   "Sınav başladıktan sonra giriş yapamazsınız!\n\n"
                                   "Lütfen öğretmeninizle iletişime geçin.")
                logging.warning(f"Sınav sırasında giriş denemesi: {no}")
                self.root.destroy()
                sys.exit()
            elif "530" in resp:  # Hatalı bilgi
                messagebox.showerror("Giriş Hatası", 
                                   "Yanlış öğrenci numarası veya şifre!\n\n"
                                   "Lütfen bilgilerinizi kontrol edin.")
                self.entry_pw.delete(0, 'end')  # Şifreyi temizle
                self.entry_pw.focus()  # Şifre alanına odaklan
                logging.warning(f"Yanlış giriş denemesi: {no}")
            else:
                messagebox.showerror("Hata", f"Bilinmeyen giriş hatası!\n\nSunucu yanıtı: {resp}")
                logging.error(f"Bilinmeyen giriş yanıtı: {resp}")

        except socket.timeout:
            messagebox.showerror("Zaman Aşımı", "Giriş işlemi zaman aşımına uğradı!\nLütfen tekrar deneyin.")
            logging.error("Giriş zaman aşımı")
        except Exception as e:
            messagebox.showerror("Bağlantı Hatası", 
                               f"Sunucuyla iletişim kurulamadı!\n\nHata: {str(e)}")
            logging.error(f"Giriş hatası: {e}")
            self.handle_connection_lost()

    def refresh_list(self):
        threading.Thread(target=self._refresh_thread, daemon=True).start()
    
    def _refresh_thread(self):
        """Dosya listesini yenileme thread'i"""
        if not self.is_connected:
            logging.warning("Bağlantı yok, liste yenilenemedi")
            return
            
        try:
            self.control_socket.send("LIST".encode(FORMAT))
            self.control_socket.settimeout(5.0)
            raw_data = self.control_socket.recv(BUFFER_SIZE).decode(FORMAT)
            
            logging.info(f"Liste yanıtı: {raw_data.strip()}")
            
            for part in raw_data.split("\n"):
                if part.startswith("DATA_LIST:"):
                    files_str = part.split(":", 1)[1] if ":" in part else ""
                    files = [f.strip() for f in files_str.split(",") if f.strip()]
                    self.root.after(0, lambda f=files: self._update_list(f))
                    break
        except socket.timeout:
            logging.warning("Liste alma zaman aşımı")
            self.root.after(0, lambda: messagebox.showwarning("Uyarı", "Dosya listesi alınamadı (Zaman aşımı)"))
        except Exception as e:
            logging.error(f"Liste yenileme hatası: {e}")
            self.handle_connection_lost()

    def _update_list(self, files):
        self.file_listbox.delete(0, tk.END)
        for f in files: 
            if f: self.file_listbox.insert(tk.END, f)

    def download_and_open(self):
        # Check if exam has started
        if not self.exam_started:
            messagebox.showwarning("Uyarı", "Sınav henüz başlamadı! Dosya indiremezsiniz.")
            return
            
        selection = self.file_listbox.curselection()
        if not selection: 
            messagebox.showwarning("Uyarı", "Dosya seçmediniz.")
            return
        filename = self.file_listbox.get(selection[0])
        threading.Thread(target=self._download_thread, args=(filename,), daemon=True).start()

    def _download_thread(self, filename):
        """Dosya indirme thread'i - uses ClientTransferHandler"""
        if not self.is_connected or not self.transfer_handler:
            self.root.after(0, lambda: messagebox.showerror("Hata", "Sunucuya bağlı değilsiniz!"))
            return
        
        if not self.exam_started:
            self.root.after(0, lambda: messagebox.showwarning("Uyarı", "Sınav henüz başlamadı! Dosya indiremezsiniz."))
            return
            
        try:
            logging.info(f"Dosya indiriliyor: {filename}")
            self.control_socket.send(f"RETR {filename}".encode(FORMAT))
            
            # Use transfer handler for download
            save_path = os.path.join(os.getcwd(), filename)
            success, received = self.transfer_handler.download_file(filename, save_path, self.ready_queue)
            
            if success:
                self.root.after(0, lambda: messagebox.showinfo("Başarılı", 
                                                              f"{filename} başarıyla indirildi!\n\n"
                                                              f"Dosya çalışma dizinine kaydedildi:\n{save_path}"))
                logging.info(f"Dosya başarıyla indirildi: {filename} ({received} bytes) -> {save_path}")
            else:
                self.root.after(0, lambda: messagebox.showerror("İndirme Hatası", 
                                                                 "Dosya indirilemedi!"))
        except Exception as e:
            logging.error(f"Dosya indirme hatası: {e}")
            self.root.after(0, lambda: messagebox.showerror("İndirme Hatası", 
                                                           f"Dosya indirilemedi!\n\nHata: {str(e)}"))
            self.handle_connection_lost()

    def select_and_upload(self):
        # Ekstra istemci taraflı kontrol
        if not self.exam_started:
            messagebox.showwarning("Uyarı", "Sınav henüz başlamadı!")
            return
            
        # Birden fazla dosya seçimine izin ver
        filepaths = filedialog.askopenfilenames(title="Gönderilecek Dosyaları Seçin (Birden fazla seçebilirsiniz)")
        if not filepaths: return
        
        # Seçilen dosyaları sırayla gönder (thread içinde)
        total_files = len(filepaths)
        threading.Thread(target=self._upload_multiple_files, args=(filepaths, total_files), daemon=True).start()
    
    def _upload_multiple_files(self, filepaths, total_files):
        """Birden fazla dosyayı sırayla gönder"""
        uploaded_count = 0
        failed_files = []
        
        for idx, filepath in enumerate(filepaths):
            filename = os.path.basename(filepath)
            is_last = (idx == total_files - 1)
            
            logging.info(f"Dosya {idx + 1}/{total_files} gönderiliyor: {filename}")
            
            # Her dosyayı sırayla gönder (blocking - skip_shutdown=True ile)
            # _upload_thread blocking olarak çalışıyor, bu yüzden dosyalar sırayla gönderilecek
            success = self._upload_thread(filepath, filename, total_files=total_files, skip_shutdown=True)
            
            if success:
                uploaded_count += 1
                logging.info(f"Dosya {idx + 1}/{total_files} başarıyla gönderildi: {filename}")
                if not is_last:
                    # Son dosya değilse kısa bir bekleme
                    time.sleep(0.5)
            else:
                failed_files.append(filename)
                logging.error(f"Dosya {idx + 1}/{total_files} gönderilemedi: {filename}")
        
        # Tüm dosyalar gönderildikten sonra özet mesajı göster
        if uploaded_count > 0:
            if len(failed_files) == 0:
                # Tüm dosyalar başarılı
                if total_files == 1:
                    self.root.after(0, self.finish_exam_shutdown)
                else:
                    self.root.after(0, lambda: messagebox.showinfo("Başarılı", 
                                                                   f"Tüm dosyalar başarıyla gönderildi!\n\n"
                                                                   f"Gönderilen: {uploaded_count} dosya"))
                    # Son dosya gönderildiğinde sistemi kapat
                    self.root.after(0, self.finish_exam_shutdown)
            else:
                # Bazı dosyalar başarısız
                failed_list = "\n".join(failed_files)
                self.root.after(0, lambda: messagebox.showwarning("Kısmi Başarı", 
                                                                  f"Gönderilen: {uploaded_count} dosya\n"
                                                                  f"Başarısız: {len(failed_files)} dosya\n\n"
                                                                  f"Başarısız dosyalar:\n{failed_list}"))
                # Yine de sistemi kapat (en az bir dosya gönderildi)
                self.root.after(0, self.finish_exam_shutdown)

    # --- Upload Progress UI Helpers ---
    def show_upload_progress(self, filename):
        """Yükleme sırasında gösterilecek progress bar penceresi"""
        # Eğer zaten açıksa, sadece resetle
        if self.upload_progress_window and self.upload_progress_window.winfo_exists():
            self.upload_progress_var.set(0)
            if self.upload_progress_label:
                self.upload_progress_label.config(text=f"{filename} yükleniyor... %0")
            return

        self.upload_progress_window = tk.Toplevel(self.root)
        self.upload_progress_window.title("Yükleniyor")
        self.upload_progress_window.geometry("350x120")
        self.upload_progress_window.resizable(False, False)
        self.upload_progress_window.grab_set()  # Odak al

        tk.Label(self.upload_progress_window, text="Dosya yükleniyor, lütfen bekleyin...", font=("Arial", 10)).pack(pady=5)
        self.upload_progress_label = tk.Label(self.upload_progress_window, text=f"{filename} yükleniyor... %0")
        self.upload_progress_label.pack(pady=5)

        pb = ttk.Progressbar(self.upload_progress_window, orient="horizontal", length=300,
                             mode="determinate", maximum=100, variable=self.upload_progress_var)
        pb.pack(pady=5)

    def update_upload_progress(self, percent, filename=None):
        """Progress bar yüzdesini güncelle"""
        if not (self.upload_progress_window and self.upload_progress_window.winfo_exists()):
            return
        self.upload_progress_var.set(percent)
        if self.upload_progress_label:
            if filename:
                self.upload_progress_label.config(text=f"{filename} yükleniyor... %{percent:.1f}")
            else:
                self.upload_progress_label.config(text=f"Yükleniyor... %{percent:.1f}")

    def close_upload_progress(self):
        """Yükleme bittiğinde progress penceresini kapat"""
        if self.upload_progress_window and self.upload_progress_window.winfo_exists():
            try:
                self.upload_progress_window.destroy()
            except Exception:
                pass
        self.upload_progress_window = None
        self.upload_progress_label = None
        self.upload_progress_var.set(0)

    def _upload_thread(self, filepath, filename, total_files=1, skip_shutdown=False):
        """Dosya yükleme thread'i - uses ClientTransferHandler"""
        if not self.is_connected or not self.transfer_handler:
            self.root.after(0, lambda: messagebox.showerror("Hata", "Sunucuya bağlı değilsiniz!"))
            return False
            
        try:
            filesize = os.path.getsize(filepath)
            logging.info(f"Dosya yükleniyor: {filename} ({filesize} bytes)")

            # Send upload command
            upload_cmd = f"STOR {filename} {filesize}"
            self.control_socket.send(upload_cmd.encode(FORMAT))
            
            # Show progress window
            self.root.after(0, lambda: self.show_upload_progress(filename))
            
            # Use transfer handler for upload
            def progress_callback(percent, fn):
                self.root.after(0, lambda p=percent, f=fn: self.update_upload_progress(p, f))
            
            success, bytes_sent = self.transfer_handler.upload_file(
                filepath, filename, self.ready_queue, progress_callback
            )
            
            if success:
                logging.info(f"Dosya başarıyla yüklendi: {filename}")
                self.root.after(0, lambda: self.update_upload_progress(100, filename))
                
                if not skip_shutdown and total_files == 1:
                    self.root.after(0, self.finish_exam_shutdown)
                
                return True
            else:
                self.root.after(0, lambda: messagebox.showerror("Yükleme Hatası", 
                                                                 "Dosya yüklenemedi!"))
                return False
        except socket.timeout:
            logging.error("Dosya yükleme zaman aşımı")
            self.root.after(0, lambda: messagebox.showerror("Zaman Aşımı", 
                                                           "Dosya yükleme zaman aşımına uğradı!"))
            return False
        except Exception as e:
            logging.error(f"Dosya yükleme hatası: {e}")
            self.root.after(0, lambda: messagebox.showerror("Yükleme Hatası", 
                                                           f"Dosya yüklenemedi!\n\nHata: {str(e)}"))
            self.handle_connection_lost()
            return False
        finally:
            # Hata durumunda da progress penceresini kapat
            self.root.after(0, self.close_upload_progress)

    def finish_exam_shutdown(self):
        messagebox.showinfo("Başarılı", "Sınav dosyanız gönderildi. Sistem kapatılıyor.")
        self.on_close()

    def time_up_shutdown(self):
        # Birden fazla kez çağrılmasını önle
        if self.time_up_shutdown_called:
            return
        
        self.time_up_shutdown_called = True
        logging.info("Sınav süresi doldu - sistem kapatılıyor")
        messagebox.showwarning("SÜRE BİTTİ", "Sınav süresi doldu! Sistem kapatılıyor.")
        self.on_close()

    def on_close(self):
        self.app_running = False
        # QUIT komutunu gönder (FTP uyumluluğu için)
        if self.is_connected and self.control_socket:
            try:
                self.control_socket.send("QUIT\n".encode(FORMAT))
                self.control_socket.settimeout(2.0)
                resp = self.control_socket.recv(BUFFER_SIZE).decode(FORMAT).strip()
                logging.info(f"QUIT yanıtı: {resp}")
            except Exception as e:
                logging.warning(f"QUIT komutu gönderilemedi: {e}")
        
        try: 
            if self.control_socket:
                self.control_socket.close()
        except: pass
        try: self.root.destroy()
        except: pass
        os._exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = SinavClientGUI(root)
    root.mainloop()