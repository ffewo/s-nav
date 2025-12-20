import socket
import logging
import time
from datetime import datetime
from typing import Dict, Optional, Tuple, Callable
from config_manager import get_config
from file_manager import get_secure_file_handler, get_question_file_manager
from network_utils import (
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
    """Handles FTP-like protocol commands"""
    
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
            "LOGIN": self.handle_login_legacy,
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
        """
        Dispatch command to appropriate handler
        
        Returns: (new_student_no, new_passive_socket, new_passive_port, should_break)
        """
        handler = self.commands.get(cmd.upper())
        if handler:
            return handler(parts, conn, addr, student_no, student_name, connection_time,
                          pending_username, passive_data_socket, passive_data_port)
        else:
            conn.send("500 Bilinmeyen komut\n".encode(FORMAT))
            logging.warning(f"Bilinmeyen komut: {cmd} from {student_no}")
            return student_no, passive_data_socket, passive_data_port, False
    
    def handle_user(self, parts: list, conn: socket.socket, addr: Tuple[str, int],
                    student_no: str, student_name: str, connection_time: str,
                    pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                    passive_data_port: Optional[int]) -> Tuple[str, Optional[socket.socket], Optional[int], bool]:
        """Handle USER command"""
        if self.exam_started():
            conn.send("550 SINAV_BASLADI_GIRIS_YASAK\n".encode(FORMAT))
            logging.warning(f"Sınav sırasında giriş denemesi: {addr[0]}")
            return student_no, passive_data_socket, passive_data_port, True
        
        if len(parts) < 2:
            conn.send("501 Syntax error in parameters or arguments.\n".encode(FORMAT))
            return student_no, passive_data_socket, passive_data_port, False
        
        pending_username = parts[1].strip()
        conn.send("331 Password required.\n".encode(FORMAT))
        logging.info(f"USER komutu alındı: {pending_username}")
        return pending_username, passive_data_socket, passive_data_port, False
    
    def handle_pass(self, parts: list, conn: socket.socket, addr: Tuple[str, int],
                    student_no: str, student_name: str, connection_time: str,
                    pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                    passive_data_port: Optional[int]) -> Tuple[str, Optional[socket.socket], Optional[int], bool]:
        """Handle PASS command"""
        if pending_username is None:
            conn.send("503 Bad sequence of commands. Use USER first.\n".encode(FORMAT))
            return student_no, passive_data_socket, passive_data_port, False
        
        if len(parts) < 2:
            conn.send("501 Syntax error in parameters or arguments.\n".encode(FORMAT))
            return student_no, passive_data_socket, passive_data_port, False
        
        password = parts[1].strip()
        student_no = pending_username
        
        # Check if already connected
        if student_no in self.connected_students:
            conn.send("550 ZATEN_BAGLI\n".encode(FORMAT))
            logging.warning(f"Zaten bağlı öğrenci giriş denemesi: {student_no}")
            return student_no, passive_data_socket, passive_data_port, True
        
        # Verify credentials
        is_valid, student_name = self.verify_student(student_no, password)
        
        if is_valid:
            from datetime import datetime
            self.connected_students[student_no] = {
                "conn": conn,
                "addr": addr,
                "name": student_name,
                "login_time": connection_time,
                "last_activity": datetime.now(),
                "delivery_file": "",
                "delivery_time": ""
            }
            conn.send("230 User logged in, proceed.\n".encode(FORMAT))
            
            activity_msg = f"Giriş Yaptı ({student_name})"
            self.update_ui_list(student_no, student_name, addr[0], "Aktif", connection_time, activity_msg)
            logging.info(f"Başarılı giriş: {student_no} - {student_name}")
            
            # Send timer if exam started
            if self.exam_started() and self.get_exam_time_remaining() > 0:
                try:
                    sync_msg = f"CMD:SYNC:{self.get_exam_time_remaining()}\n"
                    conn.send(sync_msg.encode(FORMAT))
                    logging.info(f"Sınav timer gönderildi: {student_no}")
                except Exception as e:
                    logging.error(f"Timer gönderme hatası: {e}")
            
            return student_no, passive_data_socket, passive_data_port, False
        else:
            conn.send("530 Login incorrect.\n".encode(FORMAT))
            logging.warning(f"Yanlış giriş denemesi: {student_no} from {addr[0]}")
            return "Bilinmiyor", passive_data_socket, passive_data_port, False
    
    def handle_login_legacy(self, parts: list, conn: socket.socket, addr: Tuple[str, int],
                            student_no: str, student_name: str, connection_time: str,
                            pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                            passive_data_port: Optional[int]) -> Tuple[str, Optional[socket.socket], Optional[int], bool]:
        """Handle legacy LOGIN command"""
        if self.exam_started():
            conn.send("550 SINAV_BASLADI_GIRIS_YASAK\n".encode(FORMAT))
            logging.warning(f"Sınav sırasında giriş denemesi: {addr[0]}")
            return student_no, passive_data_socket, passive_data_port, True
        
        if len(parts) < 3:
            conn.send("530 Eksik bilgi. LOGIN <no> <sifre>\n".encode(FORMAT))
            return student_no, passive_data_socket, passive_data_port, False
        
        student_no = parts[1].strip()
        password = parts[2].strip()
        
        # Check if already connected
        if student_no in self.connected_students:
            conn.send("550 ZATEN_BAGLI\n".encode(FORMAT))
            logging.warning(f"Zaten bağlı öğrenci giriş denemesi: {student_no}")
            return student_no, passive_data_socket, passive_data_port, True
        
        # Verify credentials
        is_valid, student_name = self.verify_student(student_no, password)
        
        if is_valid:
            from datetime import datetime
            self.connected_students[student_no] = {
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
            
            # Send timer if exam started
            if self.exam_started() and self.get_exam_time_remaining() > 0:
                try:
                    sync_msg = f"CMD:SYNC:{self.get_exam_time_remaining()}\n"
                    conn.send(sync_msg.encode(FORMAT))
                    logging.info(f"Sınav timer gönderildi: {student_no}")
                except Exception as e:
                    logging.error(f"Timer gönderme hatası: {e}")
            
            return student_no, passive_data_socket, passive_data_port, False
        else:
            conn.send("530 Hatali numara veya sifre\n".encode(FORMAT))
            logging.warning(f"Yanlış giriş denemesi: {student_no} from {addr[0]}")
            return "Bilinmiyor", passive_data_socket, passive_data_port, False
    
    def handle_pasv(self, parts: list, conn: socket.socket, addr: Tuple[str, int],
                    student_no: str, student_name: str, connection_time: str,
                    pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                    passive_data_port: Optional[int]) -> Tuple[str, Optional[socket.socket], Optional[int], bool]:
        """Handle PASV command"""
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
        new_socket, new_port = bind_random_port(HOST_IP, DATA_PORT_MIN, DATA_PORT_MAX)
        
        if new_socket and new_port:
            server_ip = get_server_ip_for_client(self.server_socket, HOST_IP, addr)
            pasv_response = format_passive_response(server_ip, new_port)
            conn.send(pasv_response.encode(FORMAT))
            logging.info(f"PASV yanıtı gönderildi: {new_port} (IP: {server_ip}, öğrenci: {student_no})")
            return student_no, new_socket, new_port, False
        else:
            conn.send("550 Can't open data connection.\n".encode(FORMAT))
            return student_no, None, None, False
    
    def handle_quit(self, parts: list, conn: socket.socket, addr: Tuple[str, int],
                    student_no: str, student_name: str, connection_time: str,
                    pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                    passive_data_port: Optional[int]) -> Tuple[str, Optional[socket.socket], Optional[int], bool]:
        """Handle QUIT command"""
        conn.send("221 Goodbye.\n".encode(FORMAT))
        logging.info(f"QUIT komutu alındı: {student_no} ({addr[0]})")
        return student_no, passive_data_socket, passive_data_port, True
    
    def handle_list(self, parts: list, conn: socket.socket, addr: Tuple[str, int],
                    student_no: str, student_name: str, connection_time: str,
                    pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                    passive_data_port: Optional[int]) -> Tuple[str, Optional[socket.socket], Optional[int], bool]:
        """Handle LIST command"""
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
        """Handle STOR (upload) command"""
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
            data_server_socket, data_port, pasv_used = self._get_data_port(
                passive_data_socket, passive_data_port, student_no
            )
            
            if not data_server_socket or not data_port:
                conn.send("550 Can't open data connection.\n".encode(FORMAT))
                return student_no, None, None, False
            
            # Send 227 if not using PASV
            HOST_IP = config.get("server.host", "0.0.0.0")
            if not pasv_used:
                server_ip = get_server_ip_for_client(self.server_socket, HOST_IP, addr)
                pasv_response = format_passive_response(server_ip, data_port)
                conn.send(pasv_response.encode(FORMAT))
            
            conn.send(f"150 Opening binary mode data connection for {filename}.\n".encode(FORMAT))
            time.sleep(0.1)  # Reduced from 0.2 for faster connection
            
            # Wait for data connection
            data_conn, data_addr = wait_for_data_connection(data_server_socket)
            if not data_conn:
                conn.send("550 Data baglantisi zaman asimina ugradi\n".encode(FORMAT))
                try:
                    data_server_socket.close()
                except:
                    pass
                return student_no, None, None, False
            
            # Send READY
            if not send_ready_message(conn, None, student_no):
                try:
                    data_conn.close()
                    data_server_socket.close()
                except:
                    pass
                return student_no, None, None, False
            
            # Update UI
            current_delivery_file = self.connected_students.get(student_no, {}).get("delivery_file", "")
            current_delivery_time = self.connected_students.get(student_no, {}).get("delivery_time", "")
            self.update_ui_list(
                student_no, student_name, addr[0], "Yüklüyor", connection_time,
                f"{filename} yükleniyor... ({filesize} bytes)",
                current_delivery_file, current_delivery_time
            )
            
            # Receive file
            file_data, received = receive_file_data(data_conn, filesize, BUFFER_SIZE)
            
            # Close connections
            try:
                data_conn.close()
                data_server_socket.close()
            except:
                pass
            
            if received == filesize:
                # Save file securely
                secure_handler = get_secure_file_handler()
                success, save_path, safe_filename = secure_handler.save_file_securely(
                    file_data, student_no, filename
                )
                
                if success:
                    conn.send("226 Transfer complete.\n".encode(FORMAT))
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
                else:
                    conn.send("550 Dosya kaydetme hatasi\n".encode(FORMAT))
            else:
                conn.send("550 Transfer yarim kaldi\n".encode(FORMAT))
            
            return student_no, None, None, False
            
        except ValueError:
            conn.send("550 Gecersiz dosya boyutu\n".encode(FORMAT))
        except Exception as e:
            logging.error(f"Dosya yükleme hatası: {e}")
            conn.send("550 Yukleme hatasi\n".encode(FORMAT))
        
        return student_no, None, None, False
    
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
            data_server_socket, data_port, pasv_used = self._get_data_port(
                passive_data_socket, passive_data_port, student_no
            )
            
            if not data_server_socket or not data_port:
                conn.send("550 Can't open data connection.\n".encode(FORMAT))
                return student_no, None, None, False
            
            # Send 227 if not using PASV
            HOST_IP = config.get("server.host", "0.0.0.0")
            if not pasv_used:
                server_ip = get_server_ip_for_client(self.server_socket, HOST_IP, addr)
                pasv_response = format_passive_response(server_ip, data_port)
                conn.send(pasv_response.encode(FORMAT))
            
            conn.send(f"150 Opening binary mode data connection for {filename} ({filesize} bytes).\n".encode(FORMAT))
            time.sleep(0.1)  # Reduced from 0.2 for faster connection
            
            # Wait for data connection
            data_conn, data_addr = wait_for_data_connection(data_server_socket)
            if not data_conn:
                conn.send("550 Data baglantisi zaman asimina ugradi\n".encode(FORMAT))
                try:
                    data_server_socket.close()
                except:
                    pass
                return student_no, None, None, False
            
            # Send READY with filesize
            if not send_ready_message(conn, filesize, student_no):
                try:
                    data_conn.close()
                    data_server_socket.close()
                except:
                    pass
                return student_no, None, None, False
            
            # Update UI
            if student_no in self.connected_students:
                self.connected_students[student_no]["last_activity"] = datetime.now()
            
            self.update_ui_list(
                student_no, student_name, addr[0], "İndiriyor", connection_time,
                f"{filename} indiriliyor... ({filesize} bytes)"
            )
            
            # Send file
            sent = send_file_data(data_conn, file_data, BUFFER_SIZE)
            
            # Close connections
            try:
                data_conn.close()
                data_server_socket.close()
            except:
                pass
            
            if sent == filesize:
                conn.send("226 Transfer complete.\n".encode(FORMAT))
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
            else:
                conn.send("550 Transfer yarim kaldi\n".encode(FORMAT))
            
            return student_no, None, None, False
            
        except Exception as e:
            logging.error(f"Dosya indirme hatası: {e}")
            conn.send("550 Indirme hatasi\n".encode(FORMAT))
        
        return student_no, None, None, False
    
    def handle_ping(self, parts: list, conn: socket.socket, addr: Tuple[str, int],
                    student_no: str, student_name: str, connection_time: str,
                    pending_username: Optional[str], passive_data_socket: Optional[socket.socket],
                    passive_data_port: Optional[int]) -> Tuple[str, Optional[socket.socket], Optional[int], bool]:
        """Handle PING command"""
        conn.send("PONG\n".encode(FORMAT))
        if student_no in self.connected_students:
            self.connected_students[student_no]["last_activity"] = datetime.now()
        return student_no, passive_data_socket, passive_data_port, False
    
    def _get_data_port(self, passive_socket: Optional[socket.socket], 
                      passive_port: Optional[int], student_no: str) -> Tuple[Optional[socket.socket], Optional[int], bool]:
        """Get data port - use PASV if available, otherwise create new"""
        if passive_socket and passive_port:
            logging.info(f"PASV ile açılmış data port kullanılıyor: {passive_port} (öğrenci: {student_no})")
            return passive_socket, passive_port, True
        
        HOST_IP = config.get("server.host", "0.0.0.0")
        new_socket, new_port = bind_random_port(HOST_IP, DATA_PORT_MIN, DATA_PORT_MAX)
        if new_socket and new_port:
            logging.info(f"Yeni data port açıldı: {new_port} (öğrenci: {student_no})")
        return new_socket, new_port, False

