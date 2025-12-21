import socket
import threading
import os
import time
import logging
import queue
from typing import Tuple
from datetime import datetime
from config_manager import get_config
from client_transfer import ClientTransferHandler

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


class ClientCore:
    
    def __init__(self, ui_status_callback=None, ui_timer_callback=None, ui_message_callback=None, ui_exam_started_callback=None):

        self.ui_status_callback = ui_status_callback
        self.ui_timer_callback = ui_timer_callback
        self.ui_message_callback = ui_message_callback
        self.ui_exam_started_callback = ui_exam_started_callback
        
        # Load config
        self.server_ip = config.get("client.server_ip", "127.0.0.1")
        if os.path.exists("ip.txt"):
            with open("ip.txt", "r") as f:
                ip_from_file = f.read().strip()
                if ip_from_file:
                    self.server_ip = ip_from_file
        
        self.control_port = config.get("server.port", 2121)
        self.buffer_size = config.get("server.buffer_size", 4096)
        self.format = "utf-8"
        self.reconnect_attempts_max = config.get("client.reconnect_attempts", 5)
        self.reconnect_delay = config.get("client.reconnect_delay", 3)
        
        self.control_socket = None
        self.is_connected = False
        self.student_no = ""
        self.exam_started = False
        self.reconnect_attempts = 0
        self.last_heartbeat = time.time()
        self.ready_queue = queue.Queue()
        self.login_response_queue = queue.Queue()  # Queue for login responses
        self.transfer_handler = None
        self.app_running = True
        
        # Exam timer state
        self.one_minute_warned = False
        self.time_up_shutdown_called = False
        self.exam_time_remaining = 0
        self.current_timer = None  # Track current timer to cancel if needed
    
    def connect_to_server(self) -> bool:
        """Connect to server with improved error handling"""
        for attempt in range(self.reconnect_attempts_max):
            try:
                if self.control_socket:
                    try:
                        self.control_socket.close()
                    except:
                        pass
                
                # Validate IP address
                try:
                    socket.inet_aton(self.server_ip)
                except socket.error:
                    error_msg = f"Geçersiz IP adresi: {self.server_ip}"
                    logging.error(error_msg)
                    if self.ui_message_callback:
                        self.ui_message_callback(
                            f"{error_msg}\n\n"
                            f"Lütfen 'ip.txt' dosyasında veya config.json'da geçerli bir IP adresi girin.\n"
                            f"Örnek: 192.168.1.100 veya 127.0.0.1",
                            "IP Adresi Hatası",
                            "error"
                        )
                    return False
                
                # Create socket and connect
                self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.control_socket.settimeout(10)
                
                logging.info(f"Sunucuya bağlanılıyor: {self.server_ip}:{self.control_port} (deneme {attempt + 1}/{self.reconnect_attempts_max})")
                
                try:
                    self.control_socket.connect((self.server_ip, self.control_port))
                except socket.timeout:
                    raise Exception(f"Bağlantı zaman aşımı - sunucu {self.server_ip}:{self.control_port} yanıt vermiyor")
                except ConnectionRefusedError:
                    raise Exception(f"Bağlantı reddedildi - sunucu {self.server_ip}:{self.control_port} çalışmıyor olabilir")
                except OSError as e:
                    if e.errno == 10051:  # Windows: Network is unreachable
                        raise Exception(f"Ağ erişilemiyor - {self.server_ip} adresine ulaşılamıyor")
                    elif e.errno == 10049:  # Windows: Address not available
                        raise Exception(f"IP adresi kullanılamıyor - {self.server_ip} geçersiz olabilir")
                    else:
                        raise Exception(f"Ağ hatası: {str(e)}")
                
                # Receive welcome message
                try:
                    self.control_socket.settimeout(5)
                    welcome_msg = self.control_socket.recv(self.buffer_size).decode(self.format)
                    logging.info(f"Sunucuya bağlandı: {welcome_msg.strip()}")
                except socket.timeout:
                    raise Exception("Sunucu bağlantı kuruldu ancak hoş geldin mesajı alınamadı")
                
                self.is_connected = True
                self.reconnect_attempts = 0
                self.last_heartbeat = time.time()
                
                # Initialize transfer handler
                self.transfer_handler = ClientTransferHandler(self.control_socket, self.server_ip, self.buffer_size)
                
                if self.ui_status_callback:
                    self.ui_status_callback("Sunucuya Bağlandı ✓", "green")
                
                # Start heartbeat
                threading.Thread(target=self.heartbeat_monitor, daemon=True).start()
                return True
                
            except Exception as e:
                error_detail = str(e)
                logging.warning(f"Bağlantı denemesi {attempt + 1}/{self.reconnect_attempts_max} başarısız: {error_detail}")
                if self.ui_status_callback:
                    self.ui_status_callback(f"Bağlantı denemesi {attempt + 1}/{self.reconnect_attempts_max}...", "orange")
                
                if attempt < self.reconnect_attempts_max - 1:
                    time.sleep(self.reconnect_delay)
        
        # All attempts failed
        logging.error(f"Sunucuya bağlanılamadı - tüm denemeler başarısız: {self.server_ip}:{self.control_port}")
        if self.ui_message_callback:
            self.ui_message_callback(
                f"Sunucuya bağlanılamadı!\n\n"
                f"Sunucu: {self.server_ip}:{self.control_port}\n\n"
                f"Lütfen kontrol edin:\n"
                f"• Sunucu çalışıyor mu? (server.py çalıştırıldı mı?)\n"
                f"• IP adresi doğru mu? (ip.txt veya config.json)\n"
                f"• Port doğru mu? (varsayılan: 2121)\n"
                f"• Firewall sunucu portunu engelliyor mu?\n"
                f"• Aynı ağda mısınız? (farklı ağdaysa router ayarları gerekebilir)\n\n"
                f"İpucu: Sunucu IP'sini öğrenmek için sunucu bilgisayarda 'ipconfig' komutunu çalıştırın.",
                "Bağlantı Hatası",
                "error"
            )
        return False
    
    def heartbeat_monitor(self):
        while self.app_running and self.is_connected:
            try:
                if time.time() - self.last_heartbeat > 30:
                    self.control_socket.send("PING".encode(self.format))
                    self.last_heartbeat = time.time()
                time.sleep(10)
            except Exception as e:
                logging.error(f"Heartbeat hatası: {e}")
                self.handle_connection_lost()
                break
    
    def handle_connection_lost(self):
        if not self.app_running:
            return
        
        self.is_connected = False
        logging.warning("Sunucu bağlantısı koptu, yeniden bağlanmaya çalışılıyor...")
        
        if self.ui_status_callback:
            self.ui_status_callback("Bağlantı koptu, yeniden bağlanıyor...", "red")
        
        if self.connect_to_server():
            # Restart listener if needed
            threading.Thread(target=self.server_listener, daemon=True).start()
    
    def server_listener(self):
        """Listen for server commands"""
        cmd_handlers = {
            "CMD:MSG:": self._handle_cmd_msg,
            "CMD:TIME_SECONDS:": self._handle_cmd_time_seconds,
            "CMD:SYNC:": self._handle_cmd_sync,
            "CMD:TIME_UP": self._handle_cmd_time_up,
            "CMD:SERVER_SHUTDOWN": self._handle_server_shutdown,
            "PONG": lambda d: None,
        }
        
        while self.app_running and self.is_connected:
            try:
                self.control_socket.settimeout(1.0)
                raw_data = self.control_socket.recv(self.buffer_size).decode(self.format)
                
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
                    
                    # Queue 227 and READY messages
                    if data.startswith("227") or data.startswith("READY"):
                        try:
                            self.ready_queue.put_nowait(data)
                        except queue.Full:
                            logging.warning(f"Queue dolu, mesaj atlanıyor: {data[:5]}")
                        continue
                    
                    # Queue login responses (331, 230, 530, 550)
                    if data.startswith("331") or data.startswith("230") or data.startswith("530") or (data.startswith("550") and ("SINAV_BASLADI" in data or "ZATEN_BAGLI" in data)):
                        try:
                            logging.debug(f"Login yanıtı queue'ya ekleniyor: {data[:50]}")
                            self.login_response_queue.put_nowait(data)
                            logging.debug(f"Login yanıtı queue'ya eklendi: {data[:50]}")
                        except queue.Full:
                            logging.warning(f"Login queue dolu, mesaj atlanıyor: {data[:5]}")
                        continue
                    
                    logging.info(f"Sunucudan komut alındı: {data}")
                    
                    handled = False
                    for cmd_prefix, handler in cmd_handlers.items():
                        if data.startswith(cmd_prefix):
                            handler(data)
                            handled = True
                            break
                    
                    if not handled:
                        logging.debug(f"Komut işlenmedi: {data}")
                        
            except socket.timeout:
                continue
            except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
                # Server closed connection
                logging.warning(f"Sunucu bağlantısı kapatıldı: {e}")
                if self.app_running:
                    self.handle_connection_lost()
                break
            except Exception as e:
                logging.error(f"Server listener hatası: {e}")
                if self.app_running:
                    self.handle_connection_lost()
                break
    
    def _handle_cmd_msg(self, data: str):
        msg = data.split("CMD:MSG:", 1)[1]
        if self.ui_message_callback:
            self.ui_message_callback(msg, "DUYURU", "info")
    
    def _handle_cmd_time_seconds(self, data: str):
        try:
            seconds = int(data.split(":")[2])
            self.activate_exam_mode()
            self.start_countdown(seconds)
        except (ValueError, IndexError) as e:
            logging.error(f"Zaman parse hatası: {e}")
    
    def _handle_cmd_sync(self, data: str):
        try:
            server_time = int(data.split(":")[2])
            self.activate_exam_mode()
            self.start_countdown(server_time)
        except (ValueError, IndexError) as e:
            logging.error(f"Sync parse hatası: {e}")
    
    def _handle_cmd_time_up(self, data: str):
        """Handle CMD:TIME_UP command"""
        if not self.time_up_shutdown_called:
            self.time_up_shutdown()
    
    def _handle_server_shutdown(self, data: str):
        """Handle CMD:SERVER_SHUTDOWN command - server is closing"""
        logging.info("Sunucu kapatılıyor - yeniden bağlanma denemeleri durduruluyor")
        self.is_connected = False
        self.app_running = False  # Stop all operations
        
        if self.ui_message_callback:
            self.ui_message_callback(
                "Sunucu kapatıldı.\n\n"
                "Bağlantı kesildi ve yeniden bağlanma denemeleri durduruldu.\n\n"
                "Lütfen öğretmeninizle iletişime geçin.",
                "Sunucu Kapatıldı",
                "warning"
            )
        
        if self.ui_status_callback:
            self.ui_status_callback("Sunucu Kapatıldı", "red")
    
    def activate_exam_mode(self):
        if not self.exam_started:
            self.exam_started = True
            self.one_minute_warned = False
            self.time_up_shutdown_called = False
            # Notify UI to enable upload button
            if self.ui_exam_started_callback:
                self.ui_exam_started_callback()
    
    def start_countdown(self, seconds: int):
        """Start countdown timer"""
        # Cancel existing timer if any (for time extension)
        if self.current_timer:
            try:
                self.current_timer.cancel()
            except:
                pass
            self.current_timer = None
        
        self.exam_time_remaining = seconds
        
        # Update UI immediately
        if self.ui_timer_callback:
            mins, secs = divmod(seconds, 60)
            color = "red" if seconds <= 300 else "orange" if seconds <= 600 else "green"
            self.ui_timer_callback(seconds, color)
        
        # One minute warning (reset if time extended)
        if seconds > 60:
            self.one_minute_warned = False
        elif seconds == 60 and not self.one_minute_warned:
            self.one_minute_warned = True
            if self.ui_message_callback:
                self.ui_message_callback("Sınavın bitmesine 1 dakika kaldı!", "Süre Uyarısı", "warning")
        
        # If time is up, call shutdown
        if seconds <= 0:
            if not self.time_up_shutdown_called:
                self.time_up_shutdown()
            return
        
        # Schedule next update (only if seconds > 0)
        if self.app_running and seconds > 0:
            self.current_timer = threading.Timer(1.0, lambda: self.start_countdown(seconds - 1))
            self.current_timer.start()
    
    def time_up_shutdown(self):
        """Handle time up"""
        if self.time_up_shutdown_called:
            return
        self.time_up_shutdown_called = True
        logging.info("Sınav süresi doldu - sistem kapatılıyor")
        if self.ui_message_callback:
            self.ui_message_callback("Sınav süresi doldu! Sistem kapatılıyor.", "SÜRE BİTTİ", "warning")
    
    def login(self, student_no: str, password: str) -> bool:
        """Login to server with retry mechanism"""
        if not self.is_connected:
            if self.ui_message_callback:
                self.ui_message_callback("Sunucuya bağlı değilsiniz!", "Hata", "error")
            return False
        
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                # Clear any old login responses from queue
                while not self.login_response_queue.empty():
                    try:
                        self.login_response_queue.get_nowait()
                    except queue.Empty:
                        break
                
                # Send USER command
                self.control_socket.send(f"USER {student_no}\n".encode(self.format))
                logging.info(f"USER {student_no} gönderildi")
                
                # Wait for response from queue (handled by server_listener)
                try:
                    resp_user = self.login_response_queue.get(timeout=15.0)
                    logging.info(f"USER {student_no} -> {resp_user}")
                except queue.Empty:
                    logging.warning(f"USER yanıtı zaman aşımı (deneme {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    else:
                        if self.ui_message_callback:
                            self.ui_message_callback(
                                "Giriş işlemi zaman aşımına uğradı!\n\n"
                                f"{max_retries} deneme yapıldı ancak sunucu yanıt vermedi.\n"
                                "Lütfen:\n"
                                "• İnternet bağlantınızı kontrol edin\n"
                                "• Sunucunun çalıştığından emin olun\n"
                                "• Tekrar deneyin",
                                "Zaman Aşımı",
                                "error"
                            )
                        return False
                
                # Check if USER command was rejected (550 ZATEN_BAGLI)
                if "550" in resp_user and "ZATEN_BAGLI" in resp_user:
                    logging.warning(f"USER komutu reddedildi - zaten giriş yapılmış: {student_no}")
                    if self.ui_message_callback:
                        self.ui_message_callback(
                            f"Giriş yapılamadı!\n\n"
                            f"Bu öğrenci numarası ({student_no}) ile zaten giriş yapılmış.\n\n"
                            "Aynı anda sadece bir yerden giriş yapabilirsiniz.\n"
                            "Lütfen diğer cihazdan çıkış yapın veya bekleyin.",
                            "Giriş Reddedildi",
                            "error"
                        )
                    return False
                
                if "331" in resp_user:
                    # Server expects password
                    self.control_socket.send(f"PASS {password}\n".encode(self.format))
                    logging.info(f"PASS gönderildi")
                    
                    # Wait for password response
                    try:
                        resp_pass = self.login_response_queue.get(timeout=15.0)
                        logging.info(f"PASS -> {resp_pass}")
                        resp = resp_pass
                    except queue.Empty:
                        logging.warning(f"PASS yanıtı zaman aşımı (deneme {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        else:
                            if self.ui_message_callback:
                                self.ui_message_callback(
                                    "Giriş işlemi zaman aşımına uğradı!\n\n"
                                    f"{max_retries} deneme yapıldı ancak sunucu yanıt vermedi.",
                                    "Zaman Aşımı",
                                    "error"
                                )
                            return False
                else:
                    resp = resp_user
                
                # Process response
                if "230" in resp:
                    self.student_no = student_no
                    logging.info(f"Başarılı giriş: {student_no}")
                    if self.ui_message_callback:
                        self.ui_message_callback(f"Hoşgeldiniz {student_no}!\n\nSınav sistemi hazırlanıyor...", "Başarılı", "info")
                    return True
                elif "550" in resp:
                    if "ZATEN_BAGLI" in resp:
                        # Already logged in - REJECT login attempt
                        logging.warning(f"Zaten giriş yapılmış - giriş reddedildi: {student_no}")
                        if self.ui_message_callback:
                            self.ui_message_callback(
                                f"Giriş yapılamadı!\n\n"
                                f"Bu öğrenci numarası ({student_no}) ile zaten giriş yapılmış.\n\n"
                                "Aynı anda sadece bir yerden giriş yapabilirsiniz.\n"
                                "Lütfen diğer cihazdan çıkış yapın veya bekleyin.",
                                "Giriş Reddedildi",
                                "error"
                            )
                        return False
                    elif "SINAV_BASLADI" in resp:
                        if self.ui_message_callback:
                            self.ui_message_callback(
                                "Sınav başladıktan sonra giriş yapamazsınız!\n\nLütfen öğretmeninizle iletişime geçin.",
                                "Giriş Yasak",
                                "error"
                            )
                        return False
                    else:
                        if self.ui_message_callback:
                            self.ui_message_callback(f"Giriş hatası!\n\nSunucu yanıtı: {resp}", "Hata", "error")
                        return False
                elif "530" in resp:
                    if attempt < max_retries - 1:
                        logging.warning(f"Yanlış şifre (deneme {attempt + 1}/{max_retries}), tekrar deneniyor...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        if self.ui_message_callback:
                            self.ui_message_callback(
                                "Yanlış öğrenci numarası veya şifre!\n\nLütfen bilgilerinizi kontrol edin.",
                                "Giriş Hatası",
                                "error"
                            )
                        return False
                else:
                    if self.ui_message_callback:
                        self.ui_message_callback(f"Bilinmeyen giriş hatası!\n\nSunucu yanıtı: {resp}", "Hata", "error")
                    return False
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    logging.warning(f"Giriş hatası (deneme {attempt + 1}/{max_retries}): {e}, tekrar deneniyor...")
                    time.sleep(retry_delay)
                    continue
                else:
                    if self.ui_message_callback:
                        self.ui_message_callback(
                            f"Sunucuyla iletişim kurulamadı!\n\n"
                            f"Hata: {str(e)}\n\n"
                            f"{max_retries} deneme yapıldı ancak başarısız oldu.",
                            "Bağlantı Hatası",
                            "error"
                        )
                    logging.error(f"Giriş hatası - {max_retries} deneme başarısız: {e}")
                    return False
        
        return False
    
    def get_file_list(self) -> list:
        if not self.is_connected:
            return []
        
        try:
            self.control_socket.send("LIST".encode(self.format))
            self.control_socket.settimeout(5.0)
            raw_data = self.control_socket.recv(self.buffer_size).decode(self.format)
            
            for part in raw_data.split("\n"):
                if part.startswith("DATA_LIST:"):
                    files_str = part.split(":", 1)[1] if ":" in part else ""
                    files = [f.strip() for f in files_str.split(",") if f.strip()]
                    return files
            return []
        except Exception as e:
            logging.error(f"Liste alma hatası: {e}")
            return []
    
    def download_file(self, filename: str, save_path: str) -> Tuple[bool, int]:
        if not self.is_connected or not self.transfer_handler:
            return False, 0
        
        if not self.exam_started:
            return False, 0
        
        try:
            logging.info(f"Dosya indiriliyor: {filename}")
            self.control_socket.send(f"RETR {filename}".encode(self.format))
            
            success, received = self.transfer_handler.download_file(filename, save_path, self.ready_queue)
            return success, received
        except Exception as e:
            logging.error(f"Dosya indirme hatası: {e}")
            return False, 0
    
    def upload_file(self, filepath: str, filename: str, progress_callback=None) -> Tuple[bool, int]:
        if not self.is_connected or not self.transfer_handler:
            return False, 0
        
        if not self.exam_started:
            return False, 0
        
        try:
            filesize = os.path.getsize(filepath)
            logging.info(f"Dosya yükleniyor: {filename} ({filesize} bytes)")
            
            upload_cmd = f"STOR {filename} {filesize}"
            self.control_socket.send(upload_cmd.encode(self.format))
            
            success, bytes_sent = self.transfer_handler.upload_file(
                filepath, filename, self.ready_queue, progress_callback
            )
            return success, bytes_sent
        except Exception as e:
            logging.error(f"Dosya yükleme hatası: {e}")
            return False, 0
    
    def quit(self):
        self.app_running = False
        if self.is_connected and self.control_socket:
            try:
                self.control_socket.send("QUIT\n".encode(self.format))
                self.control_socket.settimeout(2.0)
                resp = self.control_socket.recv(self.buffer_size).decode(self.format).strip()
                logging.info(f"QUIT yanıtı: {resp}")
            except Exception as e:
                logging.warning(f"QUIT komutu gönderilemedi: {e}")
        
        try:
            if self.control_socket:
                self.control_socket.close()
        except:
            pass


# SinavClientGUI moved to client_ui.py
# This file now only contains ClientCore and helper functions

if __name__ == "__main__":
    # Import and run UI
    from client_ui import SinavClientGUI
    import tkinter as tk
    root = tk.Tk()
    app = SinavClientGUI(root)
    root.mainloop()

