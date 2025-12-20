"""Sınav Sistemi - Öğretmen Sunucu"""
import socket
import threading
import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import logging
from datetime import datetime
import json
from config_manager import get_config
from network_utils import create_server_socket
from protocol_handlers import ProtocolHandler

# Konfigürasyonu yükle
config = get_config()

# --- AYARLAR ---
HOST_IP = config.get("server.host", "0.0.0.0")
CONTROL_PORT = config.get("server.port", 2121)
BUFFER_SIZE = config.get("server.buffer_size", 4096)
FORMAT = "utf-8"
MAX_CONNECTIONS = config.get("server.max_connections", 50)

# Dizinleri oluştur
for directory in ["Sorular", "Cevaplar", "Logs"]:
    if not os.path.exists(directory): 
        os.makedirs(directory)

# Logging ayarları
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
student_activities = {}

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
        logging.warning("students.txt bulunamadı")
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
        
        log_file = f"Logs/student_{student_no}_activity.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{activity['timestamp']} - {activity['action']} - {json.dumps(activity)}\n")
    except Exception as e:
        logging.error(f"Aktivite loglama hatası: {e}")

class TeacherServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Öğretmen Kontrol Paneli - Sınav Sistemi")
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
        self.setup_ui()
        self.server_socket = None
        self.start_server()
        self.update_connection_count()
    
    def setup_ui(self):
        """UI bileşenlerini oluştur"""
        # Üst kontrol paneli
        top_frame = tk.Frame(self.root, pady=10, bg="#f0f0f0")
        top_frame.pack(side=tk.TOP, fill=tk.X)
        
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
        
        # Öğrenci listesi
        list_frame = tk.Frame(self.root)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tk.Label(list_frame, text="👥 Bağlı Öğrenciler", font=("Arial", 12, "bold")).pack(anchor="w")
        
        tree_frame = tk.Frame(list_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("No", "Ad", "IP", "Durum", "Bağlantı", "Son İşlem", "Teslim Dosyası", "Teslim Zamanı"),
            show='headings'
        )
        
        for col, text in [("No", "Öğrenci No"), ("Ad", "Ad Soyad"), ("IP", "IP Adresi"),
                          ("Durum", "Durum"), ("Bağlantı", "Bağlantı Zamanı"),
                          ("Son İşlem", "Son Aktivite"), ("Teslim Dosyası", "Teslim Dosyası"),
                          ("Teslim Zamanı", "Teslim Zamanı")]:
            self.tree.heading(col, text=text)
        
        widths = [80, 140, 110, 90, 120, 220, 160, 110]
        for col, width in zip(self.tree["columns"], widths):
            self.tree.column(col, width=width)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def start_server(self):
        """Sunucuyu başlat"""
        try:
            self.server_socket = create_server_socket(HOST_IP, CONTROL_PORT, MAX_CONNECTIONS)
            logging.info(f"Sunucu başlatıldı: {HOST_IP}:{CONTROL_PORT}")
            messagebox.showinfo("Sunucu Başlatıldı", 
                              f"Sınav sunucusu başarıyla başlatıldı!\n\n"
                              f"IP: {HOST_IP}\n"
                              f"Control Port: {CONTROL_PORT}\n"
                              f"Maksimum bağlantı: {MAX_CONNECTIONS}")
            
            threading.Thread(target=self.accept_clients, daemon=True).start()
        except Exception as e:
            error_msg = f"Sunucu başlatılamadı: {e}\n\nMuhtemel nedenler:\n• Port {CONTROL_PORT} zaten kullanımda\n• Yönetici izni gerekli"
            logging.error(error_msg)
            messagebox.showerror("Sunucu Hatası", error_msg)
            self.root.destroy()
    
    def update_connection_count(self):
        """Bağlantı sayısını güncelle"""
        if self.server_running:
            count = len(connected_students)
            self.connection_lbl.config(text=f"🌐 Bağlantı: {count} öğrenci")
            self.root.after(5000, self.update_connection_count)
    
    def show_statistics(self):
        """İstatistikleri göster"""
        stats_window = tk.Toplevel(self.root)
        stats_window.title("📊 Sınav İstatistikleri")
        stats_window.geometry("500x400")
        
        stats_text = tk.Text(stats_window, wrap=tk.WORD, padx=10, pady=10)
        stats_text.pack(fill=tk.BOTH, expand=True)
        
        total_students = len(load_students())
        connected_count = len(connected_students)
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
                if self.server_running:
                    logging.error(f"Bağlantı kabul hatası: {e}")
                break
    
    def handle_client(self, conn, addr):
        """İstemci bağlantısını yönet - uses ProtocolHandler"""
        student_no = "Bilinmiyor"
        student_name = "Bilinmiyor"
        connection_time = datetime.now().strftime("%H:%M:%S")
        pending_username = None
        passive_data_socket = None
        passive_data_port = None
        
        # Initialize protocol handler
        handler = ProtocolHandler(
            self.server_socket,
            connected_students,
            log_student_activity,
            self.update_ui_list,
            lambda: self.exam_started,
            lambda: self.exam_time_remaining,
            verify_student
        )
        
        try:
            welcome_msg = "220 Sinav Sunucusu Hazir.\n"
            conn.send(welcome_msg.encode(FORMAT))
            logging.info(f"Yeni bağlantı kuruldu: {addr[0]}:{addr[1]}")
            
            conn.settimeout(300)
            
            while self.server_running:
                try:
                    data = conn.recv(BUFFER_SIZE).decode(FORMAT).strip()
                    if not data: 
                        logging.info(f"Boş veri alındı, bağlantı kapatılıyor: {addr[0]}")
                        break
                    
                    parts = data.split(" ")
                    cmd = parts[0].upper()
                    
                    logging.info(f"{student_no} ({addr[0]}) komutu: {cmd}")
                    
                    # Handle CMD: messages (not FTP commands)
                    if cmd.startswith("CMD:"):
                        self._handle_cmd_message(cmd, conn, student_no)
                        continue
                    
                    # Use protocol handler for FTP commands
                    new_student_no, new_passive_socket, new_passive_port, should_break = handler.handle_command(
                        cmd, parts, conn, addr, student_no, student_name, connection_time,
                        pending_username, passive_data_socket, passive_data_port
                    )
                    
                    # Update state based on command
                    if cmd == "USER":
                        # USER command returns the username as new_student_no (for pending)
                        pending_username = new_student_no if new_student_no != "Bilinmiyor" else None
                    elif cmd == "PASS" or cmd == "LOGIN":
                        # PASS/LOGIN updates student_no
                        if new_student_no != "Bilinmiyor":
                            student_no = new_student_no
                            pending_username = None
                            if student_no in connected_students:
                                student_name = connected_students[student_no].get("name", "Bilinmiyor")
                        elif new_student_no == "Bilinmiyor" and student_no != "Bilinmiyor":
                            # Login failed, reset
                            pending_username = None
                    
                    passive_data_socket = new_passive_socket
                    passive_data_port = new_passive_port
                    
                    if should_break:
                        break
                        
                except socket.timeout:
                    logging.warning(f"Bağlantı zaman aşımı: {student_no} ({addr[0]})")
                    break
                except Exception as e:
                    logging.error(f"Komut işleme hatası: {e}")
                    break
        
        except Exception as e:
            logging.error(f"İstemci yönetim hatası: {e}")
        finally:
            try: 
                conn.close()
            except: 
                pass
                
            if student_no != "Bilinmiyor" and student_no in connected_students:
                delivery_file = connected_students[student_no].get("delivery_file", "")
                delivery_time = connected_students[student_no].get("delivery_time", "")
                del connected_students[student_no]
                self.update_ui_list(
                    student_no, student_name, addr[0], "Çevrimdışı", connection_time,
                    "Bağlantı Koptu", delivery_file, delivery_time
                )
                logging.info(f"Bağlantı kapatıldı: {student_no} ({addr[0]})")
    
    def _handle_cmd_message(self, cmd: str, conn: socket.socket, student_no: str):
        """Handle CMD: protocol messages (not FTP commands)"""
        # These are handled separately as they're not part of FTP protocol
        pass
    
    def start_exam_timer(self):
        """Sınav timer'ını başlat"""
        mins = simpledialog.askinteger("Süre", "Sınav süresi kaç dakika?")
        if mins:
            self.exam_started = True
            self.exam_time_remaining = mins * 60
            self.start_time = datetime.now().strftime("%H:%M:%S")
            self.timer_running = True
            self.status_lbl.config(text="Durum: SINAV BAŞLADI", fg="red")
            
            total_seconds = mins * 60
            for s_no, data in connected_students.items():
                try: 
                    data["conn"].send(f"CMD:TIME_SECONDS:{total_seconds}\n".encode(FORMAT))
                except: 
                    pass
            
            self.update_server_timer()
    
    def update_server_timer(self):
        """Sunucu timer'ını güncelle"""
        if self.timer_running and self.exam_time_remaining > 0:
            mins, secs = divmod(self.exam_time_remaining, 60)
            self.timer_lbl.config(text=f"Süre: {mins:02}:{secs:02}", fg="red")
            
            if self.exam_time_remaining % 30 == 0:
                for s_no, data in connected_students.items():
                    try: 
                        data["conn"].send(f"CMD:SYNC:{self.exam_time_remaining}\n".encode(FORMAT))
                    except: 
                        pass
            
            self.exam_time_remaining -= 1
            self.root.after(1000, self.update_server_timer)
        elif self.timer_running and self.exam_time_remaining <= 0:
            self.timer_lbl.config(text="Süre: 00:00", fg="red")
            self.timer_running = False
            messagebox.showinfo("Sınav Bitti", "Sınav süresi doldu!")
            for s_no, data in connected_students.items():
                try: 
                    data["conn"].send("CMD:TIME_UP\n".encode(FORMAT))
                except: 
                    pass
    
    def unlock_entries(self):
        """Girişleri aç"""
        self.exam_started = False
        self.timer_running = False
        self.exam_time_remaining = 0
        self.status_lbl.config(text="Durum: Girişler AÇIK", fg="green")
        self.timer_lbl.config(text="Süre: --:--", fg="blue")
    
    def send_broadcast(self):
        """Duyuru gönder"""
        msg = simpledialog.askstring("Duyuru", "Mesaj:")
        if msg:
            for s_no, data in connected_students.items():
                try: 
                    data["conn"].send(f"CMD:MSG:{msg}\n".encode(FORMAT))
                except: 
                    pass
    
    def update_ui_list(self, no, name, ip, status, connection_time, action, delivery_file=None, delivery_time=None):
        """UI listesini güncelle"""
        self.root.after(0, lambda: self._update_tree_safe(no, name, ip, status, connection_time, action, delivery_file, delivery_time))
    
    def _update_tree_safe(self, no, name, ip, status, connection_time, action, delivery_file=None, delivery_time=None):
        """Thread-safe UI güncellemesi"""
        str_no = str(no).strip()
        found_item = None
        
        for item in self.tree.get_children():
            item_vals = self.tree.item(item)['values']
            if len(item_vals) > 0 and str(item_vals[0]).strip() == str_no:
                found_item = item
                break
        
        if delivery_file is None and str_no in connected_students:
            delivery_file = connected_students[str_no].get("delivery_file", "")
        if delivery_time is None and str_no in connected_students:
            delivery_time = connected_students[str_no].get("delivery_time", "")
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        action_with_time = f"[{timestamp}] {action}"
        
        values = (str_no, name, ip, status, connection_time, action_with_time, delivery_file or "", delivery_time or "")
        
        if found_item:
            self.tree.item(found_item, values=values)
        else:
            self.tree.insert("", "end", values=values)

if __name__ == "__main__":
    root = tk.Tk()
    app = TeacherServerGUI(root)
    root.mainloop()
