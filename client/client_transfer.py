import socket
import logging
import time
import queue
from typing import Optional, Tuple
from common.network_utils import parse_passive_port, create_client_socket
from common import NetworkConnectionError, FileTransferError, ProtocolViolationError

FORMAT = "utf-8"


class ClientTransferHandler:
    
    def __init__(self, control_socket: socket.socket, server_ip: str, buffer_size: int = 65536):

        self.control_socket = control_socket
        self.server_ip = server_ip
        # Use at least 64KB buffer for better performance
        self.buffer_size = max(buffer_size, 65536)
    
    def wait_for_227_message(self, ready_queue: queue.Queue, max_attempts: int = 20, 
                            timeout: float = 2.0) -> int:

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
                    raise ProtocolViolationError(
                        "Sunucu hata mesajı gönderdi",
                        details=resp,
                        command="227"
                    )
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
                        raise ProtocolViolationError(
                            "Sunucu hata mesajı gönderdi",
                            details=raw_resp,
                            command="227"
                        )
                    elif raw_resp.startswith("150") or raw_resp.startswith("CMD:"):
                        # Continue waiting
                        attempt += 1
                        continue
                except socket.timeout:
                    attempt += 1
                    if attempt >= max_attempts:
                        raise NetworkConnectionError(
                            "227 mesajı alınamadı - zaman aşımı",
                            details=f"{max_attempts} deneme sonrası",
                            host="",
                            port=0
                        )
                    continue
                except ProtocolViolationError:
                    raise
                except Exception as e:
                    raise NetworkConnectionError(
                        "227 mesajı okunamadı",
                        details=str(e),
                        host="",
                        port=0
                    ) from e
        
        raise NetworkConnectionError(
            "227 mesajı alınamadı",
            details=f"{max_attempts} deneme sonrası",
            host="",
            port=0
        )
    
    def wait_for_ready_message(self, ready_queue: queue.Queue, timeout: float = 5.0) -> Optional[int]:
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
                    else:
                        # READY without filesize
                        return None
                except (ValueError, IndexError):
                    return None
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
                        else:
                            return None
                    except (ValueError, IndexError):
                        return None
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
                        else:
                            return None
                    except (ValueError, IndexError):
                        return None
        except socket.timeout:
            # Timeout is acceptable for READY (may not have filesize)
            logging.warning("READY mesajı zaman aşımı (normal olabilir)")
            return None
        except Exception as e:
            raise NetworkConnectionError(
                "READY mesajı okunamadı",
                details=str(e),
                host="",
                port=0
            ) from e
        
        return None
    
    def connect_to_data_port(self, data_port: int, timeout: float = 10.0) -> socket.socket:
        time.sleep(0.1)
        
        try:
            data_socket = create_client_socket(timeout)
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
        except socket.timeout:
            raise NetworkConnectionError(
                f"Data port bağlantısı zaman aşımı",
                details=f"{self.server_ip}:{data_port}",
                host=self.server_ip,
                port=data_port
            )
        except Exception as e:
            raise NetworkConnectionError(
                f"Data port bağlantı hatası",
                details=str(e),
                host=self.server_ip,
                port=data_port
            ) from e
    
    def download_file(self, filename: str, save_path: str, ready_queue: queue.Queue,
                     filesize: Optional[int] = None, timeout: float = 300.0) -> Tuple[bool, int]:
        try:
            data_port = self.wait_for_227_message(ready_queue)
        except (NetworkConnectionError, ProtocolViolationError) as e:
            raise FileTransferError(
                f"Dosya indirme başlatılamadı: {filename}",
                details=e.details,
                filename=filename,
                expected_size=0,
                actual_size=0
            ) from e
        
        # Connect to data port
        try:
            data_socket = self.connect_to_data_port(data_port)
        except NetworkConnectionError as e:
            raise FileTransferError(
                f"Data port'a bağlanılamadı: {filename}",
                details=e.details,
                filename=filename,
                expected_size=0,
                actual_size=0
            ) from e
        
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
                            raise FileTransferError(
                                f"Dosya indirme zaman aşımı: {filename}",
                                details=f"Alınan: {received}/{filesize} bytes",
                                filename=filename,
                                expected_size=filesize,
                                actual_size=received
                            )
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
                            raise FileTransferError(
                                f"Dosya indirme zaman aşımı: {filename}",
                                details=f"Alınan: {received} bytes (bilinmeyen boyut)",
                                filename=filename,
                                expected_size=0,
                                actual_size=received
                            )
            
            # Wait for completion message
            try:
                self.control_socket.settimeout(5.0)
                final_resp = self.control_socket.recv(self.buffer_size).decode(FORMAT).strip()
                logging.info(f"İndirme tamamlandı: {final_resp}")
            except socket.timeout:
                logging.warning("İndirme onayı zaman aşımı (dosya indirildi olabilir)")
            
            if filesize and received != filesize:
                raise FileTransferError(
                    f"Dosya indirme tamamlanamadı: {filename}",
                    details=f"Beklenen: {filesize} bytes, Alınan: {received} bytes",
                    filename=filename,
                    expected_size=filesize,
                    actual_size=received
                )
            
            return True, received
            
        except (FileTransferError, NetworkConnectionError):
            raise
        except Exception as e:
            raise FileTransferError(
                f"Dosya indirme hatası: {filename}",
                details=str(e),
                filename=filename,
                expected_size=filesize or 0,
                actual_size=0
            ) from e
        finally:
            try:
                data_socket.close()
            except:
                pass
    
    def upload_file(self, filepath: str, filename: str, ready_queue: queue.Queue,
                   progress_callback=None, timeout: float = 300.0) -> Tuple[bool, int]:
        import os
        filesize = os.path.getsize(filepath)
        
        # Wait for 227 message
        try:
            data_port = self.wait_for_227_message(ready_queue)
        except (NetworkConnectionError, ProtocolViolationError) as e:
            raise FileTransferError(
                f"Dosya yükleme başlatılamadı: {filename}",
                details=e.details,
                filename=filename,
                expected_size=filesize,
                actual_size=0
            ) from e
        
        # Connect to data port
        try:
            data_socket = self.connect_to_data_port(data_port)
        except NetworkConnectionError as e:
            raise FileTransferError(
                f"Data port'a bağlanılamadı: {filename}",
                details=e.details,
                filename=filename,
                expected_size=filesize,
                actual_size=0
            ) from e
        
        try:
            # Wait for READY message (reduced wait time)
            time.sleep(0.1)  # Reduced from 0.2
            try:
                ready_filesize = self.wait_for_ready_message(ready_queue, timeout=20.0)
            except NetworkConnectionError:
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
                        raise FileTransferError(
                            f"Dosya yükleme zaman aşımı: {filename}",
                            details=f"Gönderilen: {bytes_sent}/{filesize} bytes",
                            filename=filename,
                            expected_size=filesize,
                            actual_size=bytes_sent
                        )
                    
                    # Progress callback (less frequent for better performance)
                    if progress_callback:
                        progress = (bytes_sent / filesize) * 100 if filesize > 0 else 100
                        # Update progress every 5MB or at completion
                        if bytes_sent % (5 * 1024 * 1024) == 0 or bytes_sent == filesize:
                            logging.info(f"Yükleme ilerlemesi: %{progress:.1f}")
                            progress_callback(progress, filename)
            
            if bytes_sent != filesize:
                raise FileTransferError(
                    f"Dosya yükleme tamamlanamadı: {filename}",
                    details=f"Gönderilen: {bytes_sent}/{filesize} bytes",
                    filename=filename,
                    expected_size=filesize,
                    actual_size=bytes_sent
                )
            
            # Wait for completion message
            try:
                self.control_socket.settimeout(5.0)
                final_resp = self.control_socket.recv(self.buffer_size).decode(FORMAT)
                logging.info(f"Yükleme tamamlandı: {final_resp.strip()}")
            except socket.timeout:
                logging.warning("Yükleme onayı zaman aşımı")
            
            return True, bytes_sent
            
        except (FileTransferError, NetworkConnectionError):
            raise
        except Exception as e:
            raise FileTransferError(
                f"Dosya yükleme hatası: {filename}",
                details=str(e),
                filename=filename,
                expected_size=filesize,
                actual_size=0
            ) from e
        finally:
            try:
                data_socket.close()
            except:
                pass

