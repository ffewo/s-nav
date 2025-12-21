import socket
import logging
import time
import threading
from datetime import datetime
from typing import Dict, Optional, Tuple, Callable
from common import (
    get_config,
    get_secure_file_handler,
    get_question_file_manager,
    NetworkConnectionError,
    ProtocolViolationError,
    FileTransferError,
    AuthenticationError,
    FileOperationError
)
from common.network_utils import (
    bind_random_port, format_passive_response, get_server_ip_for_client,
    wait_for_data_connection, send_ready_message, receive_file_data, send_file_data
)

config = get_config()
BUFFER_SIZE = config.get("server.buffer_size", 4096)
FORMAT = "utf-8"
DATA_PORT_MIN = config.get("server.data_port_min", 49152)
DATA_PORT_MAX = config.get("server.data_port_max", 65535)
MAX_FILE_SIZE = config.get("server.max_file_size_mb", 50) * 1024 * 1024


class ProtocolHandler:

    _login_lock = threading.Lock()
    _pending_logins = {}
    _pending_login_timeout = 30
    
    @staticmethod
    def _safe_send(conn: socket.socket, message: str) -> bool:
        if not conn:
            return False
        try:
            conn.send(message.encode(FORMAT))
            return True
        except (socket.error, OSError, AttributeError):
            # Socket closed or invalid
            return False
        except Exception:
            return False
    
    @staticmethod
    def _force_disconnect(conn: socket.socket) -> None:
        if not conn:
            return
        try:
            # Try to shutdown the socket first
            conn.shutdown(socket.SHUT_RDWR)
        except:
            pass
        try:
            # Then close it
            conn.close()
        except:
            pass
    
    @staticmethod
    def _cleanup_stale_pending_logins() -> None:
        current_time = time.time()
        stale_keys = []
        for student_no, login_info in ProtocolHandler._pending_logins.items():
            if isinstance(login_info, tuple) and len(login_info) == 2:
                conn, timestamp = login_info
                if current_time - timestamp > ProtocolHandler._pending_login_timeout:
                    stale_keys.append(student_no)
            else:
                # Old format without timestamp - mark as stale
                stale_keys.append(student_no)
        
        for key in stale_keys:
            logging.warning(f"Pending login timeout için temizleniyor: {key}")
            ProtocolHandler._pending_logins.pop(key, None)
    
    @staticmethod
    def _safe_check_connection(conn: socket.socket) -> bool:
        if not conn:
            return False
        try:
            # Set a very short timeout for aggressive checking
            original_timeout = conn.gettimeout()
            conn.settimeout(0.05)  # 50ms timeout for aggressive check
            
            # Try multiple methods to verify connection is alive
            # Method 1: MSG_PEEK to check if socket is readable
            try:
                conn.recv(1, socket.MSG_PEEK)
            except (socket.error, OSError):
                # If MSG_PEEK fails, try sending a zero-byte (heartbeat)
                try:
                    conn.send(b'')  # Zero-byte heartbeat
                except (socket.error, OSError):
                    return False
            
            # Restore original timeout
            conn.settimeout(original_timeout)
            return True
        except (socket.error, OSError, AttributeError):
            return False
        except Exception:
            return False
    
    def __init__(self, server_socket: socket.socket, connected_students: Dict, 
                 log_student_activity: Callable, update_ui_list: Callable,
                 exam_started: Callable, get_exam_time_remaining: Callable,
                 verify_student_func: Callable):
        self.server_socket = server_socket
        self.connected_students = connected_students
        self.log_student_activity = log_student_activity
        self.update_ui_list = update_ui_list
        self.exam_started = exam_started
        self.get_exam_time_remaining = get_exam_time_remaining
        self.verify_student = verify_student_func
        
        # Command dispatcher dictionary
        self.commands = {
            "USER": self.handle_user,
            "PASS": self.handle_pass,
            "PASV": self.handle_pasv,
            "QUIT": self.handle_quit,
            "LIST": self.handle_list,
            "STOR": self.handle_stor,
            "RETR": self.handle_retr,
            "PING": self.handle_ping,
        }
    
    def handle_command(self, cmd: str, parts: list, conn: socket.socket, addr: Tuple[str, int],
                       student_no: str, student_name: str, connection_time: str,
                       pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                       passive_data_port: Optional[int]) -> Tuple[Optional[str], Optional[socket.socket], Optional[int], bool]:
        handler = self.commands.get(cmd.upper())
        if handler:
            return handler(parts, conn, addr, student_no, student_name, connection_time,
                          pending_username, passive_data_socket, passive_data_port)
        else:
            if not self._safe_send(conn, "500 Bilinmeyen komut\n"):
                return student_no, passive_data_socket, passive_data_port, True
            logging.warning(f"Bilinmeyen komut: {cmd} from {student_no}")
            return student_no, passive_data_socket, passive_data_port, False
    
    def handle_user(self, parts: list, conn: socket.socket, addr: Tuple[str, int],
                    student_no: str, student_name: str, connection_time: str,
                    pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                    passive_data_port: Optional[int]) -> Tuple[str, Optional[socket.socket], Optional[int], bool]:
        if self.exam_started():
            if not self._safe_send(conn, "550 SINAV_BASLADI_GIRIS_YASAK\n"):
                return student_no, passive_data_socket, passive_data_port, True
            logging.warning(f"Sınav sırasında giriş denemesi: {addr[0]}")
            # This is an expected protocol error, send response and return
            return student_no, passive_data_socket, passive_data_port, True
        
        if len(parts) < 2:
            if not self._safe_send(conn, "501 Syntax error in parameters or arguments.\n"):
                return student_no, passive_data_socket, passive_data_port, True
            raise ProtocolViolationError(
                "USER komutu eksik parametre",
                details="USER komutu öğrenci numarası gerektirir",
                command="USER"
            )
        
        pending_username = parts[1].strip()
        
        # Clean up stale pending logins first
        ProtocolHandler._cleanup_stale_pending_logins()
        
        # Use lock to prevent concurrent logins at USER stage
        with ProtocolHandler._login_lock:
            # Check if student is already connected - REJECT if connection is alive
            if pending_username in self.connected_students:
                old_conn = self.connected_students[pending_username].get("conn")
                if old_conn and old_conn is not conn:
                    # Check if old connection is still alive
                    if self._safe_check_connection(old_conn):
                        # Old connection is alive - REJECT new connection
                        if not self._safe_send(conn, "550 ZATEN_BAGLI\n"):
                            return student_no, passive_data_socket, passive_data_port, True
                        logging.warning(f"Zaten bağlı öğrenci USER denemesi reddedildi: {pending_username} from {addr[0]}")
                        return student_no, passive_data_socket, passive_data_port, True
                    else:
                        # Old connection is dead - clean it up
                        logging.info(f"Eski bağlantı ölü, temizleniyor: {pending_username}")
                        ProtocolHandler._force_disconnect(old_conn)
                        del self.connected_students[pending_username]
            
            # Check if another login is in progress for this student
            if pending_username in ProtocolHandler._pending_logins:
                login_info = ProtocolHandler._pending_logins[pending_username]
                # Handle both old format (conn) and new format (conn, timestamp)
                if isinstance(login_info, tuple):
                    other_conn, _ = login_info
                else:
                    other_conn = login_info
                
                if other_conn is not conn:
                    # Another connection is trying to login - REJECT this one
                    if not self._safe_send(conn, "550 ZATEN_BAGLI\n"):
                        return student_no, passive_data_socket, passive_data_port, True
                    logging.warning(f"Eşzamanlı USER denemesi reddedildi: {pending_username} from {addr[0]}")
                    return student_no, passive_data_socket, passive_data_port, True
            
            # Mark this connection as pending login (at USER stage) with timestamp
            ProtocolHandler._pending_logins[pending_username] = (conn, time.time())
        
        # Send response outside lock to avoid deadlock
        if not self._safe_send(conn, "331 Password required.\n"):
            # Socket closed, clean up pending login
            with ProtocolHandler._login_lock:
                ProtocolHandler._pending_logins.pop(pending_username, None)
            return student_no, passive_data_socket, passive_data_port, True
        logging.info(f"USER komutu alındı: {pending_username}")
        return pending_username, passive_data_socket, passive_data_port, False
    
    def handle_pass(self, parts: list, conn: socket.socket, addr: Tuple[str, int],
                    student_no: str, student_name: str, connection_time: str,
                    pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                    passive_data_port: Optional[int]) -> Tuple[str, Optional[socket.socket], Optional[int], bool]:
        """Handle PASS command"""
        if pending_username is None:
            if not self._safe_send(conn, "503 Bad sequence of commands. Use USER first.\n"):
                return student_no, passive_data_socket, passive_data_port, False
            return student_no, passive_data_socket, passive_data_port, False
        
        if len(parts) < 2:
            if not self._safe_send(conn, "501 Syntax error in parameters or arguments.\n"):
                return student_no, passive_data_socket, passive_data_port, False
            return student_no, passive_data_socket, passive_data_port, False
        
        password = parts[1].strip()
        student_no = pending_username
        
        # Clean up stale pending logins first
        ProtocolHandler._cleanup_stale_pending_logins()
        
        # Use lock to prevent concurrent logins - KEEP LOCK THROUGHOUT ENTIRE PASS OPERATION
        with ProtocolHandler._login_lock:
            # Check if student is already connected - REJECT if connection is alive
            if student_no in self.connected_students:
                old_conn = self.connected_students[student_no].get("conn")
                if old_conn and old_conn is not conn:
                    # Check if old connection is still alive
                    if self._safe_check_connection(old_conn):
                        # Old connection is alive - REJECT new connection
                        if not self._safe_send(conn, "550 ZATEN_BAGLI\n"):
                            return student_no, passive_data_socket, passive_data_port, True
                        logging.warning(f"Zaten bağlı öğrenci PASS denemesi reddedildi: {student_no} from {addr[0]}")
                        return student_no, passive_data_socket, passive_data_port, True
                    else:
                        # Old connection is dead - clean it up
                        logging.info(f"Eski bağlantı ölü, temizleniyor: {student_no}")
                        ProtocolHandler._force_disconnect(old_conn)
                        del self.connected_students[student_no]
            
            # Check if another login is in progress for this student
            if student_no in ProtocolHandler._pending_logins:
                login_info = ProtocolHandler._pending_logins[student_no]
                # Handle both old format (conn) and new format (conn, timestamp)
                if isinstance(login_info, tuple):
                    other_conn, _ = login_info
                else:
                    other_conn = login_info
                
                if other_conn is not conn:
                    # Another connection is trying to login - REJECT this one
                    if not self._safe_send(conn, "550 ZATEN_BAGLI\n"):
                        return student_no, passive_data_socket, passive_data_port, True
                    logging.warning(f"Eşzamanlı PASS denemesi reddedildi: {student_no} from {addr[0]}")
                    return student_no, passive_data_socket, passive_data_port, True
            
            # Mark this connection as pending login with timestamp
            ProtocolHandler._pending_logins[student_no] = (conn, time.time())
            
            # Verify credentials (this might take time, so we need to check again after)
            is_valid, student_name = self.verify_student(student_no, password)
            
            # CRITICAL: Check immediately after verification (still inside lock)
            # This prevents race conditions during credential verification
            if student_no in self.connected_students:
                old_conn = self.connected_students[student_no].get("conn")
                if old_conn and old_conn is not conn and self._safe_check_connection(old_conn):
                    # Someone else logged in during verification - REJECT this connection
                    if not self._safe_send(conn, "550 ZATEN_BAGLI\n"):
                        ProtocolHandler._pending_logins.pop(student_no, None)
                        return student_no, passive_data_socket, passive_data_port, True
                    logging.warning(f"Credential verification sonrası bağlantı reddedildi (zaten bağlı): {student_no} from {addr[0]}")
                    ProtocolHandler._pending_logins.pop(student_no, None)
                    return student_no, passive_data_socket, passive_data_port, True
            
            if is_valid:
                # Double-check: another connection might have logged in while we were verifying
                if student_no in self.connected_students:
                    old_conn = self.connected_students[student_no].get("conn")
                    if old_conn and old_conn is not conn:
                        if self._safe_check_connection(old_conn):
                            # Another connection is already logged in - REJECT this connection
                            if not self._safe_send(conn, "550 ZATEN_BAGLI\n"):
                                ProtocolHandler._pending_logins.pop(student_no, None)
                                return student_no, passive_data_socket, passive_data_port, True
                            logging.warning(f"PASS sırasında başka bağlantı tespit edildi - giriş reddedildi: {student_no} from {addr[0]}")
                            ProtocolHandler._pending_logins.pop(student_no, None)
                            return student_no, passive_data_socket, passive_data_port, True
                        else:
                            # Old connection is dead - remove it
                            ProtocolHandler._force_disconnect(old_conn)
                            del self.connected_students[student_no]
                
                # Final check: make sure we're still the pending login
                if student_no in ProtocolHandler._pending_logins:
                    login_info = ProtocolHandler._pending_logins[student_no]
                    if isinstance(login_info, tuple):
                        pending_conn, _ = login_info
                    else:
                        pending_conn = login_info
                    
                    if pending_conn is not conn:
                        # Someone else took our place - REJECT this connection
                        if not self._safe_send(conn, "550 ZATEN_BAGLI\n"):
                            return student_no, passive_data_socket, passive_data_port, True
                        logging.warning(f"PASS aşamasında başka bağlantı pending login'i aldı - giriş reddedildi: {student_no} from {addr[0]}")
                        return student_no, passive_data_socket, passive_data_port, True
                
                # ULTIMATE CHECK: Right before writing to connected_students, check one more time
                if student_no in self.connected_students:
                    old_conn = self.connected_students[student_no].get("conn")
                    if old_conn and old_conn is not conn:
                        if self._safe_check_connection(old_conn):
                            # Someone else just logged in RIGHT NOW - REJECT this connection
                            if not self._safe_send(conn, "550 ZATEN_BAGLI\n"):
                                ProtocolHandler._pending_logins.pop(student_no, None)
                                return student_no, passive_data_socket, passive_data_port, True
                            logging.warning(f"PASS aşamasında SON KONTROL - giriş reddedildi (zaten bağlı): {student_no} from {addr[0]}")
                            ProtocolHandler._pending_logins.pop(student_no, None)
                            return student_no, passive_data_socket, passive_data_port, True
                        else:
                            # Old connection is dead - remove it
                            ProtocolHandler._force_disconnect(old_conn)
                            del self.connected_students[student_no]
                
                # FINAL ULTIMATE CHECK: One last check right before writing
                # This is the absolute last chance to catch any race condition
                if student_no in self.connected_students:
                    old_conn = self.connected_students[student_no].get("conn")
                    if old_conn and old_conn is not conn:
                        if self._safe_check_connection(old_conn):
                            # Someone else just logged in at the very last moment - REJECT this connection
                            if not self._safe_send(conn, "550 ZATEN_BAGLI\n"):
                                ProtocolHandler._pending_logins.pop(student_no, None)
                                return student_no, passive_data_socket, passive_data_port, True
                            logging.warning(f"PASS aşamasında FINAL KONTROL - giriş reddedildi (zaten bağlı): {student_no} from {addr[0]}")
                            ProtocolHandler._pending_logins.pop(student_no, None)
                            return student_no, passive_data_socket, passive_data_port, True
                        else:
                            # Old connection is dead - remove it
                            ProtocolHandler._force_disconnect(old_conn)
                            del self.connected_students[student_no]
                
                # Register successful login - ATOMIC OPERATION
                # Remove from pending BEFORE adding to connected (to prevent race condition)
                ProtocolHandler._pending_logins.pop(student_no, None)
                # Now write to connected_students - this is the critical section
                # FINAL CHECK: One last time before writing
                if student_no in self.connected_students:
                    old_conn = self.connected_students[student_no].get("conn")
                    if old_conn and old_conn is not conn:
                        if self._safe_check_connection(old_conn):
                            # Someone else is still connected - REJECT this connection
                            if not self._safe_send(conn, "550 ZATEN_BAGLI\n"):
                                return student_no, passive_data_socket, passive_data_port, True
                            logging.warning(f"PASS yazma öncesi son kontrol - giriş reddedildi (zaten bağlı): {student_no} from {addr[0]}")
                            return student_no, passive_data_socket, passive_data_port, True
                        else:
                            # Old connection is dead - remove it
                            ProtocolHandler._force_disconnect(old_conn)
                            del self.connected_students[student_no]
                
                self.connected_students[student_no] = {
                    "conn": conn,
                    "addr": addr,
                    "name": student_name,
                    "login_time": connection_time,
                    "last_activity": datetime.now(),
                    "delivery_file": "",
                    "delivery_time": ""
                }
                
                # Verify we successfully wrote (one more check after writing)
                if self.connected_students[student_no].get("conn") is not conn:
                    # Someone else overwrote us - this should never happen but check anyway
                    logging.error(f"PASS aşamasında YAZMA SONRASI KONTROL: Başka bağlantı tespit edildi: {student_no} from {addr[0]}")
                    self.connected_students.pop(student_no, None)
                    if not self._safe_send(conn, "550 ZATEN_BAGLI\n"):
                        return student_no, passive_data_socket, passive_data_port, True
                    return student_no, passive_data_socket, passive_data_port, True
                
                if not self._safe_send(conn, "230 User logged in, proceed.\n"):
                    # Socket closed, remove from connected
                    self.connected_students.pop(student_no, None)
                    return student_no, passive_data_socket, passive_data_port, True
                
                activity_msg = f"Giriş Yaptı ({student_name})"
                self.update_ui_list(student_no, student_name, addr[0], "Aktif", connection_time, activity_msg)
                logging.info(f"Başarılı giriş: {student_no} - {student_name}")
                
                # Send timer if exam started
                if self.exam_started() and self.get_exam_time_remaining() > 0:
                    sync_msg = f"CMD:SYNC:{self.get_exam_time_remaining()}\n"
                    if self._safe_send(conn, sync_msg):
                        logging.info(f"Sınav timer gönderildi: {student_no}")
                
                return student_no, passive_data_socket, passive_data_port, False
            else:
                if not self._safe_send(conn, "530 Login incorrect.\n"):
                    ProtocolHandler._pending_logins.pop(student_no, None)
                    return "Bilinmiyor", passive_data_socket, passive_data_port, False
                logging.warning(f"Yanlış giriş denemesi: {student_no} from {addr[0]}")
                # Remove from pending logins on failure
                ProtocolHandler._pending_logins.pop(student_no, None)
                return "Bilinmiyor", passive_data_socket, passive_data_port, False
    
    def handle_pasv(self, parts: list, conn: socket.socket, addr: Tuple[str, int],
                    student_no: str, student_name: str, connection_time: str,
                    pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                    passive_data_port: Optional[int]) -> Tuple[str, Optional[socket.socket], Optional[int], bool]:
        if student_no == "Bilinmiyor":
            conn.send("530 Please login with USER and PASS.\n".encode(FORMAT))
            return student_no, passive_data_socket, passive_data_port, False
        
        # Close old passive socket
        if passive_data_socket:
            try:
                passive_data_socket.close()
            except:
                pass
        
        # Bind to random port
        HOST_IP = config.get("server.host", "0.0.0.0")
        try:
            new_socket, new_port = bind_random_port(HOST_IP, DATA_PORT_MIN, DATA_PORT_MAX)
        except NetworkConnectionError as e:
            try:
                conn.send("550 Can't open data connection.\n".encode(FORMAT))
            except:
                pass
            raise
        
        try:
            server_ip = get_server_ip_for_client(self.server_socket, HOST_IP, addr)
            pasv_response = format_passive_response(server_ip, new_port)
            conn.send(pasv_response.encode(FORMAT))
            logging.info(f"PASV yanıtı gönderildi: {new_port} (IP: {server_ip}, öğrenci: {student_no})")
            return student_no, new_socket, new_port, False
        except Exception as e:
            try:
                new_socket.close()
            except:
                pass
            try:
                conn.send("550 Can't open data connection.\n".encode(FORMAT))
            except:
                pass
            raise NetworkConnectionError(
                "PASV yanıtı gönderilemedi",
                details=str(e),
                host=addr[0],
                port=0
            ) from e
    
    def handle_quit(self, parts: list, conn: socket.socket, addr: Tuple[str, int],
                    student_no: str, student_name: str, connection_time: str,
                    pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                    passive_data_port: Optional[int]) -> Tuple[str, Optional[socket.socket], Optional[int], bool]:
        conn.send("221 Goodbye.\n".encode(FORMAT))
        logging.info(f"QUIT komutu alındı: {student_no} ({addr[0]})")
        return student_no, passive_data_socket, passive_data_port, True
    
    def handle_list(self, parts: list, conn: socket.socket, addr: Tuple[str, int],
                    student_no: str, student_name: str, connection_time: str,
                    pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                    passive_data_port: Optional[int]) -> Tuple[str, Optional[socket.socket], Optional[int], bool]:
        if student_no == "Bilinmiyor":
            conn.send("530 Please login with USER and PASS.\n".encode(FORMAT))
            return student_no, passive_data_socket, passive_data_port, False
        
        try:
            question_manager = get_question_file_manager()
            files_info = question_manager.list_question_files()
            files = [f["filename"] for f in files_info]
            files_str = ",".join(files) if files else ""
            conn.send(f"DATA_LIST:{files_str}\n".encode(FORMAT))
            
            self.update_ui_list(
                student_no, student_name, addr[0], "Aktif", connection_time,
                f"Sorular listelendi ({len(files)} dosya)"
            )
            
            if student_no in self.connected_students:
                self.connected_students[student_no]["last_activity"] = datetime.now()
        except Exception as e:
            logging.error(f"Dosya listeleme hatası: {e}")
            conn.send("550 Dosya listesi alinamadi\n".encode(FORMAT))
        
        return student_no, passive_data_socket, passive_data_port, False
    
    def handle_stor(self, parts: list, conn: socket.socket, addr: Tuple[str, int],
                    student_no: str, student_name: str, connection_time: str,
                    pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                    passive_data_port: Optional[int]) -> Tuple[str, Optional[socket.socket], Optional[int], bool]:
        if student_no == "Bilinmiyor":
            conn.send("530 Please login with USER and PASS.\n".encode(FORMAT))
            return student_no, passive_data_socket, passive_data_port, False
        
        if not self.exam_started():
            conn.send("550 SINAV_BASLAMADI_YUKLEME_YASAK\n".encode(FORMAT))
            logging.warning(f"Sınav başlamadan yükleme denemesi: {student_no}")
            return student_no, passive_data_socket, passive_data_port, False
        
        if len(parts) < 2:
            conn.send("501 Syntax error in parameters or arguments.\n".encode(FORMAT))
            return student_no, passive_data_socket, passive_data_port, False
        
        try:
            filename = parts[1]
            filesize = int(parts[2]) if len(parts) >= 3 else 0
            
            if filesize > 0 and filesize > MAX_FILE_SIZE:
                max_size_mb = config.get("server.max_file_size_mb", 50)
                conn.send(f"550 File too large (max {max_size_mb}MB).\n".encode(FORMAT))
                return student_no, passive_data_socket, passive_data_port, False
            
            # Use PASV port if available, otherwise create new
            try:
                data_server_socket, data_port, pasv_used = self._get_data_port(
                    passive_data_socket, passive_data_port, student_no
                )
            except NetworkConnectionError as e:
                try:
                    conn.send("550 Can't open data connection.\n".encode(FORMAT))
                except:
                    pass
                raise
            
            if not data_server_socket or not data_port:
                try:
                    conn.send("550 Can't open data connection.\n".encode(FORMAT))
                except:
                    pass
                raise NetworkConnectionError(
                    "Data port açılamadı",
                    details="PASV port veya yeni port oluşturulamadı",
                    host=addr[0],
                    port=0
                )
            
            # Send 227 if not using PASV
            HOST_IP = config.get("server.host", "0.0.0.0")
            try:
                if not pasv_used:
                    server_ip = get_server_ip_for_client(self.server_socket, HOST_IP, addr)
                    pasv_response = format_passive_response(server_ip, data_port)
                    conn.send(pasv_response.encode(FORMAT))
                
                conn.send(f"150 Opening binary mode data connection for {filename}.\n".encode(FORMAT))
            except Exception as e:
                try:
                    data_server_socket.close()
                except:
                    pass
                raise NetworkConnectionError(
                    "STOR yanıtı gönderilemedi",
                    details=str(e),
                    host=addr[0],
                    port=0
                ) from e
            
            time.sleep(0.1)  # Reduced from 0.2 for faster connection
            
            # Wait for data connection
            try:
                data_conn, data_addr = wait_for_data_connection(data_server_socket)
            except NetworkConnectionError as e:
                try:
                    conn.send("550 Data baglantisi zaman asimina ugradi\n".encode(FORMAT))
                    data_server_socket.close()
                except:
                    pass
                raise
            
            # Send READY
            try:
                send_ready_message(conn, None, student_no)
            except NetworkConnectionError as e:
                try:
                    data_conn.close()
                    data_server_socket.close()
                except:
                    pass
                raise
            
            # Update UI
            current_delivery_file = self.connected_students.get(student_no, {}).get("delivery_file", "")
            current_delivery_time = self.connected_students.get(student_no, {}).get("delivery_time", "")
            self.update_ui_list(
                student_no, student_name, addr[0], "Yüklüyor", connection_time,
                f"{filename} yükleniyor... ({filesize} bytes)",
                current_delivery_file, current_delivery_time
            )
            
            # Receive file
            try:
                file_data, received = receive_file_data(data_conn, filesize, BUFFER_SIZE)
            except FileTransferError as e:
                try:
                    data_conn.close()
                    data_server_socket.close()
                    conn.send("550 Transfer yarim kaldi\n".encode(FORMAT))
                except:
                    pass
                raise FileTransferError(
                    f"Dosya alınamadı: {filename}",
                    details=e.details,
                    filename=filename,
                    expected_size=filesize,
                    actual_size=e.actual_size
                ) from e
            
            # Close connections
            try:
                data_conn.close()
                data_server_socket.close()
            except:
                pass
            
            if received != filesize:
                try:
                    conn.send("550 Transfer yarim kaldi\n".encode(FORMAT))
                except:
                    pass
                raise FileTransferError(
                    f"Dosya transferi tamamlanamadı: {filename}",
                    details=f"Beklenen: {filesize} bytes, Alınan: {received} bytes",
                    filename=filename,
                    expected_size=filesize,
                    actual_size=received
                )
            
            # Save file securely
            secure_handler = get_secure_file_handler()
            success, save_path, safe_filename = secure_handler.save_file_securely(
                file_data, student_no, filename
            )
            
            if not success:
                try:
                    conn.send("550 Dosya kaydetme hatasi\n".encode(FORMAT))
                except:
                    pass
                raise FileOperationError(
                    f"Dosya kaydedilemedi: {filename}",
                    details=save_path if save_path else "Bilinmeyen hata",
                    filepath=save_path
                )
            
            try:
                conn.send("226 Transfer complete.\n".encode(FORMAT))
            except Exception as e:
                raise NetworkConnectionError(
                    "Transfer tamamlandı mesajı gönderilemedi",
                    details=str(e),
                    host=addr[0],
                    port=0
                ) from e
            
            delivery_time = datetime.now().strftime("%H:%M:%S")
            if student_no in self.connected_students:
                self.connected_students[student_no]["delivery_file"] = filename
                self.connected_students[student_no]["delivery_time"] = delivery_time
            
            self.update_ui_list(
                student_no, student_name, addr[0], "TESLİM EDİLDİ", connection_time,
                f"CEVAP TESLİM EDİLDİ: {filename}", filename, delivery_time
            )
            
            activity = {
                "timestamp": datetime.now().isoformat(),
                "action": "file_upload",
                "filename": filename,
                "filesize": filesize,
                "student_no": student_no,
                "saved_filename": safe_filename
            }
            self.log_student_activity(student_no, activity)
            
            return student_no, None, None, False
            
        except (NetworkConnectionError, FileTransferError, FileOperationError) as e:
            # These exceptions are already handled above, but re-raise for caller
            raise
        except ValueError:
            try:
                conn.send("550 Gecersiz dosya boyutu\n".encode(FORMAT))
            except:
                pass
            raise ProtocolViolationError(
                "Geçersiz dosya boyutu",
                details="Dosya boyutu integer olmalı",
                command="STOR"
            )
        except Exception as e:
            logging.error(f"Dosya yükleme hatası: {e}")
            try:
                conn.send("550 Yukleme hatasi\n".encode(FORMAT))
            except:
                pass
            raise FileTransferError(
                "Beklenmeyen dosya yükleme hatası",
                details=str(e),
                filename=parts[1] if len(parts) >= 2 else "",
                expected_size=0,
                actual_size=0
            ) from e
    
    def handle_retr(self, parts: list, conn: socket.socket, addr: Tuple[str, int],
                    student_no: str, student_name: str, connection_time: str,
                    pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                    passive_data_port: Optional[int]) -> Tuple[str, Optional[socket.socket], Optional[int], bool]:
        """Handle RETR (download) command"""
        if student_no == "Bilinmiyor":
            conn.send("530 Please login with USER and PASS.\n".encode(FORMAT))
            return student_no, passive_data_socket, passive_data_port, False
        
        if not self.exam_started():
            conn.send("550 SINAV_BASLAMADI_INDIRME_YASAK\n".encode(FORMAT))
            logging.warning(f"Sınav başlamadan indirme denemesi: {student_no}")
            return student_no, passive_data_socket, passive_data_port, False
        
        if len(parts) < 2:
            conn.send("501 Syntax error in parameters or arguments.\n".encode(FORMAT))
            return student_no, passive_data_socket, passive_data_port, False
        
        try:
            filename = parts[1]
            question_manager = get_question_file_manager()
            file_data = question_manager.get_file_content(filename)
            
            if file_data is None:
                conn.send("550 File not found.\n".encode(FORMAT))
                return student_no, passive_data_socket, passive_data_port, False
            
            filesize = len(file_data)
            
            # Use PASV port if available, otherwise create new
            try:
                data_server_socket, data_port, pasv_used = self._get_data_port(
                    passive_data_socket, passive_data_port, student_no
                )
            except NetworkConnectionError as e:
                try:
                    conn.send("550 Can't open data connection.\n".encode(FORMAT))
                except:
                    pass
                raise
            
            if not data_server_socket or not data_port:
                try:
                    conn.send("550 Can't open data connection.\n".encode(FORMAT))
                except:
                    pass
                raise NetworkConnectionError(
                    "Data port açılamadı",
                    details="PASV port veya yeni port oluşturulamadı",
                    host=addr[0],
                    port=0
                )
            
            # Send 227 if not using PASV
            HOST_IP = config.get("server.host", "0.0.0.0")
            try:
                if not pasv_used:
                    server_ip = get_server_ip_for_client(self.server_socket, HOST_IP, addr)
                    pasv_response = format_passive_response(server_ip, data_port)
                    conn.send(pasv_response.encode(FORMAT))
                
                conn.send(f"150 Opening binary mode data connection for {filename} ({filesize} bytes).\n".encode(FORMAT))
            except Exception as e:
                try:
                    data_server_socket.close()
                except:
                    pass
                raise NetworkConnectionError(
                    "RETR yanıtı gönderilemedi",
                    details=str(e),
                    host=addr[0],
                    port=0
                ) from e
            
            time.sleep(0.1)  # Reduced from 0.2 for faster connection
            
            # Wait for data connection
            try:
                data_conn, data_addr = wait_for_data_connection(data_server_socket)
            except NetworkConnectionError as e:
                try:
                    conn.send("550 Data baglantisi zaman asimina ugradi\n".encode(FORMAT))
                    data_server_socket.close()
                except:
                    pass
                raise
            
            # Send READY with filesize
            try:
                send_ready_message(conn, filesize, student_no)
            except NetworkConnectionError as e:
                try:
                    data_conn.close()
                    data_server_socket.close()
                except:
                    pass
                raise
            
            # Update UI
            if student_no in self.connected_students:
                self.connected_students[student_no]["last_activity"] = datetime.now()
            
            self.update_ui_list(
                student_no, student_name, addr[0], "İndiriyor", connection_time,
                f"{filename} indiriliyor... ({filesize} bytes)"
            )
            
            # Send file
            try:
                sent = send_file_data(data_conn, file_data, BUFFER_SIZE)
            except FileTransferError as e:
                try:
                    data_conn.close()
                    data_server_socket.close()
                    conn.send("550 Transfer yarim kaldi\n".encode(FORMAT))
                except:
                    pass
                raise FileTransferError(
                    f"Dosya gönderilemedi: {filename}",
                    details=e.details,
                    filename=filename,
                    expected_size=filesize,
                    actual_size=e.actual_size
                ) from e
            
            # Close connections
            try:
                data_conn.close()
                data_server_socket.close()
            except:
                pass
            
            try:
                conn.send("226 Transfer complete.\n".encode(FORMAT))
            except Exception as e:
                raise NetworkConnectionError(
                    "Transfer tamamlandı mesajı gönderilemedi",
                    details=str(e),
                    host=addr[0],
                    port=0
                ) from e
            
            self.update_ui_list(
                student_no, student_name, addr[0], "Aktif", connection_time,
                f"{filename} indirildi"
            )
            
            activity = {
                "timestamp": datetime.now().isoformat(),
                "action": "file_download",
                "filename": filename,
                "filesize": filesize,
                "student_no": student_no
            }
            self.log_student_activity(student_no, activity)
            
            return student_no, None, None, False
            
        except (NetworkConnectionError, FileTransferError) as e:
            # These exceptions are already handled above, but re-raise for caller
            raise
        except Exception as e:
            logging.error(f"Dosya indirme hatası: {e}")
            try:
                conn.send("550 Indirme hatasi\n".encode(FORMAT))
            except:
                pass
            raise FileTransferError(
                "Beklenmeyen dosya indirme hatası",
                details=str(e),
                filename=parts[1] if len(parts) >= 2 else "",
                expected_size=0,
                actual_size=0
            ) from e
    
    def handle_ping(self, parts: list, conn: socket.socket, addr: Tuple[str, int],
                    student_no: str, student_name: str, connection_time: str,
                    pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                    passive_data_port: Optional[int]) -> Tuple[str, Optional[socket.socket], Optional[int], bool]:
        conn.send("PONG\n".encode(FORMAT))
        if student_no in self.connected_students:
            self.connected_students[student_no]["last_activity"] = datetime.now()
        return student_no, passive_data_socket, passive_data_port, False
    
    def _get_data_port(self, passive_socket: Optional[socket.socket], 
                      passive_port: Optional[int], student_no: str) -> Tuple[socket.socket, int, bool]:
        if passive_socket and passive_port:
            logging.info(f"PASV ile açılmış data port kullanılıyor: {passive_port} (öğrenci: {student_no})")
            return passive_socket, passive_port, True
        
        HOST_IP = config.get("server.host", "0.0.0.0")
        new_socket, new_port = bind_random_port(HOST_IP, DATA_PORT_MIN, DATA_PORT_MAX)
        logging.info(f"Yeni data port açıldı: {new_port} (öğrenci: {student_no})")
        return new_socket, new_port, False

