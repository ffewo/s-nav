"""Client-side file transfer utilities"""
import socket
import logging
import time
import queue
from typing import Optional, Tuple
from network_utils import parse_passive_port, create_client_socket

FORMAT = "utf-8"


class ClientTransferHandler:
    """Handles file uploads and downloads for the client"""
    
    def __init__(self, control_socket: socket.socket, server_ip: str, buffer_size: int = 65536):
        """
        Initialize transfer handler with optimized buffer size
        
        Args:
            buffer_size: Default 64KB (65536 bytes) for faster transfers
        """
        self.control_socket = control_socket
        self.server_ip = server_ip
        # Use at least 64KB buffer for better performance
        self.buffer_size = max(buffer_size, 65536)
    
    def wait_for_227_message(self, ready_queue: queue.Queue, max_attempts: int = 20, 
                            timeout: float = 2.0) -> Optional[int]:
        """
        Wait for 227 passive mode message and return data port
        
        Returns: data_port or None if failed
        """
        attempt = 0
        while attempt < max_attempts:
            # Check queue first
            try:
                resp = ready_queue.get(timeout=1.0)
                if resp.startswith("227"):
                    port = parse_passive_port(resp)
                    if port:
                        logging.info(f"227 mesajı queue'dan alındı: {resp}")
                        return port
                    # Put back if not 227
                    try:
                        ready_queue.put_nowait(resp)
                    except queue.Full:
                        pass
                elif resp.startswith("550"):
                    logging.error(f"Hata mesajı alındı: {resp}")
                    return None
                elif resp.startswith("150"):
                    # 150 message - continue waiting
                    attempt += 1
                    continue
                else:
                    # Put back other messages
                    try:
                        ready_queue.put_nowait(resp)
                    except queue.Full:
                        pass
                    attempt += 1
                    continue
            except queue.Empty:
                # Try reading from socket
                try:
                    self.control_socket.settimeout(timeout)
                    raw_resp = self.control_socket.recv(self.buffer_size).decode(FORMAT).strip()
                    
                    if raw_resp.startswith("227"):
                        port = parse_passive_port(raw_resp)
                        if port:
                            logging.info(f"227 mesajı socket'ten alındı: {raw_resp}")
                            return port
                    elif raw_resp.startswith("550"):
                        logging.error(f"Hata mesajı alındı: {raw_resp}")
                        return None
                    elif raw_resp.startswith("150") or raw_resp.startswith("CMD:"):
                        # Continue waiting
                        attempt += 1
                        continue
                except socket.timeout:
                    attempt += 1
                    if attempt >= max_attempts:
                        logging.error("227 mesajı alınamadı - zaman aşımı")
                        return None
                    continue
                except Exception as e:
                    logging.error(f"227 mesajı okuma hatası: {e}")
                    attempt += 1
                    continue
        
        return None
    
    def wait_for_ready_message(self, ready_queue: queue.Queue, timeout: float = 5.0) -> Optional[int]:
        """
        Wait for READY message and return filesize if present
        
        Returns: filesize (int) or None if no filesize in message
        """
        # Check queue first
        try:
            ready_resp = ready_queue.get_nowait()
            if "READY" in ready_resp:
                try:
                    parts = ready_resp.split()
                    if len(parts) >= 2:
                        filesize = int(parts[1])
                        logging.info(f"READY mesajı queue'dan alındı: {ready_resp}")
                        return filesize
                except (ValueError, IndexError):
                    pass
        except queue.Empty:
            pass
        
        # Try reading from socket
        try:
            self.control_socket.settimeout(timeout)
            time.sleep(0.05)  # Reduced wait time (was 0.2)
            
            # Check queue again (server_listener might have added it)
            try:
                ready_resp = ready_queue.get(timeout=0.1)
                if "READY" in ready_resp:
                    try:
                        parts = ready_resp.split()
                        if len(parts) >= 2:
                            filesize = int(parts[1])
                            logging.info(f"READY mesajı queue'dan alındı (ikinci deneme): {ready_resp}")
                            return filesize
                    except (ValueError, IndexError):
                        pass
            except queue.Empty:
                pass
            
            # Read from socket
            raw_data = self.control_socket.recv(self.buffer_size)
            if raw_data:
                ready_resp = raw_data.decode(FORMAT).strip()
                if "READY" in ready_resp:
                    try:
                        parts = ready_resp.split()
                        if len(parts) >= 2:
                            filesize = int(parts[1])
                            logging.info(f"READY mesajı socket'ten alındı: {ready_resp}")
                            return filesize
                    except (ValueError, IndexError):
                        pass
        except socket.timeout:
            logging.warning("READY mesajı zaman aşımı")
        except Exception as e:
            logging.error(f"READY mesajı okuma hatası: {e}")
        
        return None
    
    def connect_to_data_port(self, data_port: int, timeout: float = 10.0) -> Optional[socket.socket]:
        """Connect to server data port with optimized settings"""
        time.sleep(0.1)  # Reduced wait time (was 0.3)
        
        try:
            data_socket = create_client_socket(timeout)
            # Additional optimizations for data socket
            try:
                data_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024)  # 256KB
                data_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)  # 256KB
                data_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except:
                pass
            
            logging.info(f"Data port'a bağlanılıyor: {self.server_ip}:{data_port}")
            data_socket.connect((self.server_ip, data_port))
            logging.info(f"Data port'a bağlandı: {self.server_ip}:{data_port}")
            return data_socket
        except Exception as e:
            logging.error(f"Data port bağlantı hatası: {e}")
            return None
    
    def download_file(self, filename: str, save_path: str, ready_queue: queue.Queue,
                     filesize: Optional[int] = None, timeout: float = 300.0) -> Tuple[bool, int]:
        """
        Download file from server
        
        Returns: (success, bytes_received)
        """
        # Wait for 227 message
        data_port = self.wait_for_227_message(ready_queue)
        if not data_port:
            return False, 0
        
        # Connect to data port
        data_socket = self.connect_to_data_port(data_port)
        if not data_socket:
            return False, 0
        
        try:
            # Wait for READY message (reduced wait time)
            time.sleep(0.05)  # Reduced from 0.1
            ready_filesize = self.wait_for_ready_message(ready_queue)
            if ready_filesize is not None:
                filesize = ready_filesize
            
            # Calculate timeout
            if filesize:
                timeout_seconds = max(30, (filesize / (1024 * 1024)) * 60)
                timeout_seconds = min(timeout_seconds, 600)
            else:
                timeout_seconds = timeout
            
            data_socket.settimeout(timeout_seconds)
            logging.info(f"Dosya indirme başlıyor - timeout: {timeout_seconds:.1f} saniye (dosya boyutu: {filesize} bytes)")
            
            # Download file
            received = 0
            last_progress_time = time.time()
            download_start_time = time.time()
            
            with open(save_path, "wb") as f:
                if filesize:
                    while received < filesize:
                        remaining = filesize - received
                        chunk_size = min(self.buffer_size, remaining)
                        try:
                            chunk = data_socket.recv(chunk_size)
                            if not chunk:
                                logging.warning(f"Beklenmedik veri sonu: {received}/{filesize} bytes")
                                break
                            f.write(chunk)
                            received += len(chunk)
                            
                            # Log progress less frequently for better performance (every 10 seconds or 5MB)
                            current_time = time.time()
                            if received == len(chunk) or current_time - last_progress_time >= 10.0 or received % (5 * 1024 * 1024) == 0:
                                progress = (received / filesize) * 100 if filesize > 0 else 0
                                elapsed = current_time - download_start_time
                                speed = received / elapsed if elapsed > 0 else 0
                                logging.info(f"İndirme ilerlemesi: %{progress:.1f} ({received}/{filesize} bytes, {speed/1024:.1f} KB/s)")
                                last_progress_time = current_time
                        except socket.timeout:
                            logging.error(f"İndirme zaman aşımı: {received}/{filesize} bytes")
                            break
                else:
                    # Unknown size
                    while True:
                        try:
                            chunk = data_socket.recv(self.buffer_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            received += len(chunk)
                        except socket.timeout:
                            if received > 0:
                                logging.info(f"İndirme tamamlandı (bilinmeyen boyut): {received} bytes")
                                break
                            raise
            
            # Wait for completion message
            try:
                self.control_socket.settimeout(5.0)
                final_resp = self.control_socket.recv(self.buffer_size).decode(FORMAT).strip()
                logging.info(f"İndirme tamamlandı: {final_resp}")
            except socket.timeout:
                logging.warning("İndirme onayı zaman aşımı (dosya indirildi olabilir)")
            
            return True, received
            
        finally:
            try:
                data_socket.close()
            except:
                pass
    
    def upload_file(self, filepath: str, filename: str, ready_queue: queue.Queue,
                   progress_callback=None, timeout: float = 300.0) -> Tuple[bool, int]:
        """
        Upload file to server
        
        Args:
            filepath: Local file path
            filename: Remote filename
            ready_queue: Queue for receiving messages
            progress_callback: Optional callback(percent, filename) for progress updates
            timeout: Timeout in seconds
        
        Returns: (success, bytes_sent)
        """
        import os
        filesize = os.path.getsize(filepath)
        
        # Wait for 227 message
        data_port = self.wait_for_227_message(ready_queue)
        if not data_port:
            return False, 0
        
        # Connect to data port
        data_socket = self.connect_to_data_port(data_port)
        if not data_socket:
            return False, 0
        
        try:
            # Wait for READY message (reduced wait time)
            time.sleep(0.1)  # Reduced from 0.2
            ready_filesize = self.wait_for_ready_message(ready_queue, timeout=20.0)
            if ready_filesize is None and not ready_filesize:
                logging.warning("READY mesajı alınamadı, devam ediliyor...")
            
            # Calculate timeout
            timeout_seconds = max(30, (filesize / (1024 * 1024)) * 60)
            timeout_seconds = min(timeout_seconds, 600)
            data_socket.settimeout(timeout_seconds)
            
            # Upload file
            bytes_sent = 0
            with open(filepath, "rb") as f:
                while bytes_sent < filesize:
                    chunk = f.read(min(self.buffer_size, filesize - bytes_sent))
                    if not chunk:
                        break
                    try:
                        data_socket.sendall(chunk)
                        bytes_sent += len(chunk)
                    except socket.timeout:
                        logging.error(f"Yükleme zaman aşımı: {bytes_sent}/{filesize} bytes")
                        break
                    
                    # Progress callback (less frequent for better performance)
                    if progress_callback:
                        progress = (bytes_sent / filesize) * 100 if filesize > 0 else 100
                        # Update progress every 5MB or at completion
                        if bytes_sent % (5 * 1024 * 1024) == 0 or bytes_sent == filesize:
                            logging.info(f"Yükleme ilerlemesi: %{progress:.1f}")
                            progress_callback(progress, filename)
            
            # Wait for completion message
            try:
                self.control_socket.settimeout(5.0)
                final_resp = self.control_socket.recv(self.buffer_size).decode(FORMAT)
                logging.info(f"Yükleme tamamlandı: {final_resp.strip()}")
            except socket.timeout:
                logging.warning("Yükleme onayı zaman aşımı")
            
            return True, bytes_sent
            
        finally:
            try:
                data_socket.close()
            except:
                pass

