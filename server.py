"""Sınav Sistemi - Öğretmen Sunucu Core Logic"""
import socket
import threading
import os
import time
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


class ServerCore:
    """Server core logic - handles networking, state management, and business logic"""
    
    def __init__(self, ui_update_callback=None):
        """
        Initialize server core
        
        Args:
            ui_update_callback: Callback function(no, name, ip, status, connection_time, action, delivery_file, delivery_time)
        """
        self.ui_update_callback = ui_update_callback
        self.server_socket = None
        self.server_running = False
        self.exam_started = False
        self.exam_time_remaining = 0
        self.timer_running = False
        self.start_time = None
        self.connected_students = connected_students  # Shared reference
    
    def start_server(self) -> bool:
        """Start the server socket"""
        try:
            self.server_socket = create_server_socket(HOST_IP, CONTROL_PORT, MAX_CONNECTIONS)
            logging.info(f"Sunucu başlatıldı: {HOST_IP}:{CONTROL_PORT}")
            self.server_running = True
            threading.Thread(target=self.accept_clients, daemon=True).start()
            return True
        except Exception as e:
            logging.error(f"Sunucu başlatılamadı: {e}")
            return False
    
    def accept_clients(self):
        """Accept new client connections"""
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
        """Handle client connection - uses ProtocolHandler"""
        student_no = "Bilinmiyor"
        student_name = "Bilinmiyor"
        connection_time = datetime.now().strftime("%H:%M:%S")
        pending_username = None
        passive_data_socket = None
        passive_data_port = None
        
        # Initialize protocol handler
        handler = ProtocolHandler(
            self.server_socket,
            self.connected_students,
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
                        # These are handled separately
                        continue
                    
                    # Use protocol handler for FTP commands
                    try:
                        new_student_no, new_passive_socket, new_passive_port, should_break = handler.handle_command(
                            cmd, parts, conn, addr, student_no, student_name, connection_time,
                            pending_username, passive_data_socket, passive_data_port
                        )
                    except (socket.error, OSError) as e:
                        # Socket error - connection likely closed
                        logging.warning(f"Socket hatası (bağlantı kapatılmış olabilir): {e}")
                        break
                    except Exception as e:
                        logging.error(f"Komut işleme hatası: {e}")
                        break
                    
                    # Update state based on command
                    if cmd == "USER":
                        pending_username = new_student_no if new_student_no != "Bilinmiyor" else None
                    elif cmd == "PASS" or cmd == "LOGIN":
                        if new_student_no != "Bilinmiyor":
                            student_no = new_student_no
                            pending_username = None
                            if student_no in self.connected_students:
                                student_name = self.connected_students[student_no].get("name", "Bilinmiyor")
                        elif new_student_no == "Bilinmiyor" and student_no != "Bilinmiyor":
                            # Login failed - clean up pending login
                            if pending_username:
                                ProtocolHandler._pending_logins.pop(pending_username, None)
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
                
            # Clean up pending logins for pending_username (if login not completed)
            if pending_username and pending_username != "Bilinmiyor":
                ProtocolHandler._pending_logins.pop(pending_username, None)
            
            # Clean up connection - only remove if this is the current connection
            if student_no != "Bilinmiyor" and student_no in self.connected_students:
                # Verify this is the same connection before removing
                stored_conn = self.connected_students[student_no].get("conn")
                if stored_conn is conn:  # Only remove if it's the same connection
                    delivery_file = self.connected_students[student_no].get("delivery_file", "")
                    delivery_time = self.connected_students[student_no].get("delivery_time", "")
                    del self.connected_students[student_no]
                    self.update_ui_list(
                        student_no, student_name, addr[0], "Çevrimdışı", connection_time,
                        "Bağlantı Koptu", delivery_file, delivery_time
                    )
                    logging.info(f"Bağlantı kapatıldı: {student_no} ({addr[0]})")
                    
                    # Also clean up pending logins
                    ProtocolHandler._pending_logins.pop(student_no, None)
                else:
                    # Different connection - don't remove (new connection replaced old one)
                    logging.info(f"Bağlantı kapatıldı ama farklı bağlantı aktif: {student_no} ({addr[0]})")
    
    def update_ui_list(self, no, name, ip, status, connection_time, action, delivery_file=None, delivery_time=None):
        """Update UI list via callback"""
        if self.ui_update_callback:
            self.ui_update_callback(no, name, ip, status, connection_time, action, delivery_file, delivery_time)
    
    def start_exam_timer(self, minutes: int) -> bool:
        """Start exam timer"""
        try:
            self.exam_started = True
            self.exam_time_remaining = minutes * 60
            self.start_time = datetime.now().strftime("%H:%M:%S")
            self.timer_running = True
            
            total_seconds = minutes * 60
            for s_no, data in self.connected_students.items():
                try: 
                    data["conn"].send(f"CMD:TIME_SECONDS:{total_seconds}\n".encode(FORMAT))
                except: 
                    pass
            
            # Start timer update loop
            threading.Thread(target=self._timer_loop, daemon=True).start()
            return True
        except Exception as e:
            logging.error(f"Sınav timer başlatma hatası: {e}")
            return False
    
    def _timer_loop(self):
        """Internal timer update loop"""
        while self.timer_running and self.exam_time_remaining > 0:
            if self.exam_time_remaining % 30 == 0:
                for s_no, data in self.connected_students.items():
                    try: 
                        data["conn"].send(f"CMD:SYNC:{self.exam_time_remaining}\n".encode(FORMAT))
                    except: 
                        pass
            
            time.sleep(1)
            self.exam_time_remaining -= 1
        
        if self.timer_running and self.exam_time_remaining <= 0:
            self.timer_running = False
            self.exam_started = False  # Sınav bitti, girişleri aç
            logging.info("Sınav süresi doldu - girişler açıldı")
            for s_no, data in self.connected_students.items():
                try: 
                    data["conn"].send("CMD:TIME_UP\n".encode(FORMAT))
                except: 
                    pass
    
    
    def unlock_entries(self):

        self.exam_started = False
        self.timer_running = False
        self.exam_time_remaining = 0
    
    def send_broadcast(self, message: str):

        for s_no, data in self.connected_students.items():
            try: 
                data["conn"].send(f"CMD:MSG:{message}\n".encode(FORMAT))
            except: 
                pass
    
    def get_connection_count(self) -> int:

        return len(self.connected_students)
    
    def extend_exam_time(self, additional_minutes: int) -> bool:
        """Extend exam time by additional minutes"""
        if not self.exam_started or not self.timer_running:
            return False
        
        try:
            additional_seconds = additional_minutes * 60
            self.exam_time_remaining += additional_seconds
            
            # Send new time to all connected students
            for s_no, data in self.connected_students.items():
                try: 
                    data["conn"].send(f"CMD:SYNC:{self.exam_time_remaining}\n".encode(FORMAT))
                except: 
                    pass
            
            logging.info(f"Sınav süresi {additional_minutes} dakika uzatıldı. Yeni süre: {self.exam_time_remaining // 60} dakika")
            return True
        except Exception as e:
            logging.error(f"Süre uzatma hatası: {e}")
            return False
    
    def get_exam_status(self) -> dict:
        return {
            "exam_started": self.exam_started,
            "time_remaining": self.exam_time_remaining,
            "timer_running": self.timer_running,
            "start_time": getattr(self, 'start_time', None)
        }
    
    def stop_server(self):
        """Stop server and notify all clients"""
        self.server_running = False
        self.timer_running = False
        
        # Notify all clients that server is shutting down
        for student_no, data in self.connected_students.items():
            try:
                # Send shutdown message first
                data["conn"].send("CMD:MSG:Sunucu kapatılıyor. Lütfen çalışmanızı kaydedin!".encode(FORMAT))
                # Send shutdown command to prevent reconnection attempts
                data["conn"].send("CMD:SERVER_SHUTDOWN\n".encode(FORMAT))
            except:
                pass
        
        # Close all client connections
        for student_no, data in list(self.connected_students.items()):
            try:
                data["conn"].close()
            except:
                pass
        
        # Clear connected students
        self.connected_students.clear()
        
        # Close server socket
        try:
            if self.server_socket:
                self.server_socket.close()
        except:
            pass
        
        logging.info("Sunucu kapatıldı")

if __name__ == "__main__":
    # Import and run UI
    from server_ui import TeacherServerGUI
    import tkinter as tk
    root = tk.Tk()
    app = TeacherServerGUI(root)
    root.mainloop()
