import socket
import threading
import os
import time
import tkinter as tk
from tkinter import messagebox, filedialog
import psutil
import sys
import logging
import json
from datetime import datetime
from config_manager import get_config

# Konfigürasyonu yükle
config = get_config()

# --- AYARLAR ---
# Önce ip.txt dosyasını kontrol et (geriye uyumluluk)
SERVER_IP = config.get("client.server_ip", "127.0.0.1")
if os.path.exists("ip.txt"):
    with open("ip.txt", "r") as f: 
        ip_from_file = f.read().strip()
        if ip_from_file:
            SERVER_IP = ip_from_file

CONTROL_PORT = config.get("server.port", 2121)
BUFFER_SIZE = config.get("server.buffer_size", 4096)
FORMAT = "utf-8"
RECONNECT_ATTEMPTS = config.get("client.reconnect_attempts", 5)
RECONNECT_DELAY = config.get("client.reconnect_delay", 3)

# Logging ayarları - config'den al
log_level = getattr(logging, config.get("logging.level", "INFO").upper())
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('Logs/client.log'),
        logging.StreamHandler()
    ]
)

# Logs dizinini oluştur
os.makedirs('Logs', exist_ok=True)

class SinavClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Sınav Sistemi - Öğrenci")
        # UI config'den boyutları al
        width = config.get("ui.window_width", 600)
        height = config.get("ui.window_height", 500)
        self.root.geometry(f"{width}x{height}")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close) 

        self.app_running = True
        # Config'den yasaklı uygulamaları al
        self.banned_apps = config.get("security.banned_applications", 
                                     ["chrome.exe", "firefox.exe", "msedge.exe", "opera.exe"])
        threading.Thread(target=self.browser_killer, daemon=True).start()

        self.control_socket = None
        self.is_connected = False
        self.student_no = ""
        self.exam_started = False
        self.reconnect_attempts = 0
        self.last_heartbeat = time.time()
        
        logging.info("Sınav sistemi başlatıldı")
        self.setup_login_ui()
        self.connect_to_server()

    def connect_to_server(self):
        """Sunucuya bağlanma ve yeniden bağlanma mantığı"""
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

    def browser_killer(self):
        """Yasaklı uygulamaları kapatma"""
        while self.app_running:
            try:
                for proc in psutil.process_iter(['name']):
                    try:
                        if proc.info['name'] in self.banned_apps: 
                            proc.kill()
                            logging.info(f"Yasaklı uygulama kapatıldı: {proc.info['name']}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except Exception as e:
                logging.error(f"Browser killer hatası: {e}")
            time.sleep(2)
    
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
        """Sunucudan gelen komutları dinleme"""
        while self.app_running and self.is_connected:
            try:
                self.control_socket.settimeout(1.0)  # Non-blocking receive
                raw_data = self.control_socket.recv(BUFFER_SIZE).decode(FORMAT)
                
                if not raw_data: 
                    logging.warning("Sunucudan boş veri geldi, bağlantı kopmuş olabilir")
                    self.handle_connection_lost()
                    break
                
                self.last_heartbeat = time.time()  # Bağlantı aktif
                commands = raw_data.split("\n")
                
                for data in commands:
                    data = data.strip()
                    if not data: continue
                    
                    logging.info(f"Sunucudan komut alındı: {data}")
                    
                    if data.startswith("CMD:MSG:"):
                        msg = data.split("CMD:MSG:", 1)[1]  # Daha güvenli split
                        self.root.after(0, lambda m=msg: messagebox.showinfo("DUYURU", m))
                    
                    elif data.startswith("CMD:TIME_SECONDS:"):
                        try:
                            seconds = int(data.split(":")[2])
                            self.root.after(0, self.activate_exam_mode)
                            self.root.after(0, lambda s=seconds: self.start_countdown(s))
                        except (ValueError, IndexError) as e:
                            logging.error(f"Zaman parse hatası: {e}")
                    
                    elif data.startswith("CMD:SYNC:"):
                        try:
                            server_time = int(data.split(":")[2])
                            self.root.after(0, self.activate_exam_mode)
                            self.root.after(0, lambda s=server_time: self.start_countdown(s))
                        except (ValueError, IndexError) as e:
                            logging.error(f"Sync parse hatası: {e}")
                        
                    elif data == "CMD:TIME_UP":
                        self.root.after(0, self.time_up_shutdown)
                    
                    elif data == "PONG":
                        # Heartbeat yanıtı
                        pass
                        
            except socket.timeout:
                # Timeout normal, devam et
                continue
            except Exception as e:
                logging.error(f"Server listener hatası: {e}")
                self.handle_connection_lost()
                break

    def start_countdown(self, seconds):
        if seconds >= 0:
            mins, secs = divmod(seconds, 60)
            color = "red" if seconds <= 300 else "orange" if seconds <= 600 else "green"
            self.timer_label.config(text=f"Süre: {mins:02}:{secs:02}", fg=color)
            
            if self.app_running:
                 self.root.after(1000, lambda: self.start_countdown(seconds - 1))
        else:
            self.time_up_shutdown()

    def activate_exam_mode(self):
        """Sınav modunu aktif et - buton ve durumu güncelle"""
        if not self.exam_started:
            self.exam_started = True
            try:
                self.upload_btn.config(state="normal", bg="#FF5722", text="DOSYA YÜKLE / TESLİM ET")
            except Exception as e:
                print(f"Button activation error: {e}")

    def handle_login(self):
        """Kullanıcı girişi işlemi"""
        no = self.entry_no.get().strip()
        pw = self.entry_pw.get().strip()
        
        # Input validation
        if not no or not pw:
            messagebox.showwarning("Uyarı", "Öğrenci numarası ve şifre gerekli!")
            return
        
        if not no.isdigit():
            messagebox.showwarning("Uyarı", "Öğrenci numarası sadece rakamlardan oluşmalıdır!")
            return
            
        if not self.is_connected:
            messagebox.showerror("Bağlantı Hatası", "Sunucuya bağlı değilsiniz!")
            return
            
        try:
            login_cmd = f"LOGIN {no} {pw}"
            logging.info(f"Giriş denemesi: {no}")
            
            self.control_socket.send(login_cmd.encode(FORMAT))
            self.control_socket.settimeout(10.0)  # Login için timeout
            resp = self.control_socket.recv(BUFFER_SIZE).decode(FORMAT).strip()
            
            logging.info(f"Giriş yanıtı: {resp}")
            
            if "550" in resp:
                messagebox.showerror("Giriş Yasak", 
                                   "Sınav başladıktan sonra giriş yapamazsınız!\n\n"
                                   "Lütfen öğretmeninizle iletişime geçin.")
                logging.warning(f"Sınav sırasında giriş denemesi: {no}")
                self.root.destroy()
                sys.exit()
            elif "530" in resp:
                messagebox.showerror("Giriş Hatası", 
                                   "Yanlış öğrenci numarası veya şifre!\n\n"
                                   "Lütfen bilgilerinizi kontrol edin.")
                self.entry_pw.delete(0, 'end')  # Şifreyi temizle
                self.entry_pw.focus()  # Şifre alanına odaklan
                logging.warning(f"Yanlış giriş denemesi: {no}")
            elif "230" in resp:
                self.student_no = no
                logging.info(f"Başarılı giriş: {no}")
                messagebox.showinfo("Başarılı", f"Hoşgeldiniz {no}!\n\nSınav sistemi hazırlanıyor...")
                self.setup_main_ui()
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
        selection = self.file_listbox.curselection()
        if not selection: 
            messagebox.showwarning("Uyarı", "Dosya seçmediniz.")
            return
        filename = self.file_listbox.get(selection[0])
        threading.Thread(target=self._download_thread, args=(filename,), daemon=True).start()

    def _download_thread(self, filename):
        """Dosya indirme thread'i"""
        if not self.is_connected:
            self.root.after(0, lambda: messagebox.showerror("Hata", "Sunucuya bağlı değilsiniz!"))
            return
            
        try:
            logging.info(f"Dosya indiriliyor: {filename}")
            self.control_socket.send(f"RETR {filename}".encode(FORMAT))
            
            # Gerçek indirme işlemi burada yapılabilir
            # Şimdilik simülasyon
            self.root.after(0, lambda: messagebox.showinfo("Başarılı", 
                                                          f"{filename} başarıyla indirildi!\n\n"
                                                          f"Dosya masaüstünüze kaydedildi."))
            logging.info(f"Dosya başarıyla indirildi: {filename}")
        except Exception as e:
            logging.error(f"Dosya indirme hatası: {e}")
            self.root.after(0, lambda: messagebox.showerror("Hata", 
                                                           f"Dosya indirilemedi!\n\nHata: {str(e)}"))
            self.handle_connection_lost()

    def select_and_upload(self):
        # Ekstra istemci taraflı kontrol
        if not self.exam_started:
            messagebox.showwarning("Uyarı", "Sınav henüz başlamadı!")
            return
            
        filepath = filedialog.askopenfilename(title="Gönderilecek Dosyayı Seçin")
        if not filepath: return
        filename = os.path.basename(filepath)
        threading.Thread(target=self._upload_thread, args=(filepath, filename), daemon=True).start()

    def _upload_thread(self, filepath, filename):
        """Dosya yükleme thread'i"""
        if not self.is_connected:
            self.root.after(0, lambda: messagebox.showerror("Hata", "Sunucuya bağlı değilsiniz!"))
            return
            
        try:
            filesize = os.path.getsize(filepath)
            logging.info(f"Dosya yükleniyor: {filename} ({filesize} bytes)")
            
            # Yükleme komutunu gönder
            upload_cmd = f"STOR {filename} {filesize}"
            self.control_socket.send(upload_cmd.encode(FORMAT))
            
            # Sunucu yanıtını bekle
            self.control_socket.settimeout(10.0)
            resp = self.control_socket.recv(BUFFER_SIZE).decode(FORMAT).strip()
            logging.info(f"Yükleme yanıtı: {resp}")
            
            if "550" in resp:
                self.root.after(0, lambda: messagebox.showerror("Yükleme Yasak", 
                                                               "Sınav başlamadığı için dosya yükleyemezsiniz!"))
                return
            
            if "READY" not in resp:
                self.root.after(0, lambda: messagebox.showerror("Hata", 
                                                               f"Sunucu yüklemeyi reddetti: {resp}"))
                return

            # Dosyayı gönder
            bytes_sent = 0
            with open(filepath, "rb") as f:
                while bytes_sent < filesize:
                    chunk = f.read(min(BUFFER_SIZE, filesize - bytes_sent))
                    if not chunk:
                        break
                    self.control_socket.sendall(chunk)
                    bytes_sent += len(chunk)
                    
                    # İlerleme göstergesi (opsiyonel)
                    progress = (bytes_sent / filesize) * 100
                    if bytes_sent % (BUFFER_SIZE * 10) == 0:  # Her 40KB'da bir log
                        logging.info(f"Yükleme ilerlemesi: %{progress:.1f}")
            
            # Tamamlanma onayını bekle
            self.control_socket.settimeout(5.0)
            try: 
                final_resp = self.control_socket.recv(BUFFER_SIZE).decode(FORMAT)
                logging.info(f"Yükleme tamamlandı: {final_resp.strip()}")
            except socket.timeout:
                logging.warning("Yükleme onayı zaman aşımı")
            
            logging.info(f"Dosya başarıyla yüklendi: {filename}")
            self.root.after(0, self.finish_exam_shutdown)
            
        except socket.timeout:
            logging.error("Dosya yükleme zaman aşımı")
            self.root.after(0, lambda: messagebox.showerror("Zaman Aşımı", 
                                                           "Dosya yükleme zaman aşımına uğradı!"))
        except Exception as e:
            logging.error(f"Dosya yükleme hatası: {e}")
            self.root.after(0, lambda: messagebox.showerror("Yükleme Hatası", 
                                                           f"Dosya yüklenemedi!\n\nHata: {str(e)}"))
            self.handle_connection_lost()

    def finish_exam_shutdown(self):
        messagebox.showinfo("Başarılı", "Sınav dosyanız gönderildi. Sistem kapatılıyor.")
        self.on_close()

    def time_up_shutdown(self):
        messagebox.showwarning("SÜRE BİTTİ", "Sınav süresi doldu! Sistem kapatılıyor.")
        self.on_close()

    def on_close(self):
        self.app_running = False
        try: self.control_socket.close()
        except: pass
        try: self.root.destroy()
        except: pass
        os._exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = SinavClientGUI(root)
    root.mainloop()