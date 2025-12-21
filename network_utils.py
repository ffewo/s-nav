"""Network utilities for socket operations and data transfer"""
import socket
import random
import logging
import time
from typing import Tuple, Optional
from exceptions import NetworkConnectionError, FileTransferError

FORMAT = "utf-8"


def create_server_socket(host: str, port: int, max_connections: int = 50) -> socket.socket:
    """Create and bind a server socket with optimized settings"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Optimize socket buffers for faster transfers
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024)  # 256KB send buffer
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)  # 256KB receive buffer
        except:
            pass
        sock.bind((host, port))
        sock.listen(max_connections)
        return sock
    except OSError as e:
        raise NetworkConnectionError(
            f"Sunucu soketi oluşturulamadı",
            details=str(e),
            host=host,
            port=port
        ) from e
    except Exception as e:
        raise NetworkConnectionError(
            f"Sunucu soketi oluşturulurken beklenmeyen hata",
            details=str(e),
            host=host,
            port=port
        ) from e


def create_client_socket(timeout: float = 10.0) -> socket.socket:
    """Create a client socket with timeout and optimized settings"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    # Optimize socket buffers for faster transfers
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024)  # 256KB send buffer
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)  # 256KB receive buffer
        # Disable Nagle's algorithm for lower latency
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except:
        pass
    return sock


def bind_random_port(host: str, port_min: int, port_max: int, max_attempts: int = 10) -> Tuple[socket.socket, int]:
    """Bind to a random port in the specified range"""
    sock = None
    for attempt in range(max_attempts):
        try:
            port = random.randint(port_min, port_max)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            sock.listen(1)
            sock.settimeout(30)
            logging.info(f"Random port açıldı: {port}")
            return sock, port
        except OSError as e:
            if sock:
                try:
                    sock.close()
                except:
                    pass
            if attempt == max_attempts - 1:
                raise NetworkConnectionError(
                    f"Port açılamadı ({max_attempts} deneme sonrası)",
                    details=str(e),
                    host=host,
                    port=0
                ) from e
    raise NetworkConnectionError(
        f"Port açılamadı",
        details=f"{max_attempts} deneme başarısız",
        host=host,
        port=0
    )


def parse_passive_port(passive_msg: str) -> Optional[int]:
    """Parse data port from FTP 227 passive mode message"""
    try:
        start_idx = passive_msg.find("(")
        end_idx = passive_msg.find(")")
        if start_idx != -1 and end_idx != -1:
            port_str = passive_msg[start_idx+1:end_idx]
            parts = port_str.split(",")
            if len(parts) >= 6:
                return int(parts[4]) * 256 + int(parts[5])
    except Exception as e:
        logging.warning(f"Port parse hatası: {e}")
    return None


def format_passive_response(ip: str, port: int) -> str:
    """Format FTP 227 passive mode response"""
    ip_parts = ip.replace('.', ',')
    return f"227 Entering Passive Mode ({ip_parts},{port//256},{port%256})\n"


def get_server_ip_for_client(server_socket: socket.socket, host_ip: str, client_addr: Tuple[str, int]) -> str:
    """Get the server IP address to send to client (handles 0.0.0.0 case)"""
    if host_ip != "0.0.0.0":
        return host_ip
    
    try:
        server_ip = server_socket.getsockname()[0]
        if server_ip == "0.0.0.0":
            return client_addr[0]
        return server_ip
    except:
        return client_addr[0]


def wait_for_data_connection(data_server_socket: socket.socket, timeout: float = 30.0) -> Tuple[socket.socket, Tuple[str, int]]:
    """Wait for client to connect to data port with optimized settings"""
    try:
        data_conn, data_addr = data_server_socket.accept()
        # Optimize data connection for faster transfers
        try:
            data_conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024)  # 256KB send buffer
            data_conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)  # 256KB receive buffer
            data_conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # Disable Nagle
        except:
            pass
        logging.info(f"Data bağlantısı kuruldu: {data_addr[0]}:{data_addr[1]}")
        return data_conn, data_addr
    except socket.timeout:
        raise NetworkConnectionError(
            f"Data bağlantısı zaman aşımı ({timeout} saniye)",
            details="İstemci data port'a bağlanamadı",
            host="",
            port=0
        )
    except Exception as e:
        raise NetworkConnectionError(
            f"Data bağlantısı kurulamadı",
            details=str(e),
            host="",
            port=0
        ) from e


def send_ready_message(control_conn: socket.socket, filesize: Optional[int] = None, student_no: str = "") -> None:
    """Send READY message to client after data connection is established"""
    try:
        control_conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except:
        pass
    
    try:
        if filesize is not None:
            ready_msg = f"READY {filesize}\n"
        else:
            ready_msg = "READY\n"
        
        control_conn.send(ready_msg.encode(FORMAT))
        # No sleep needed - TCP_NODELAY ensures immediate send
        logging.info(f"READY mesajı gönderildi (öğrenci: {student_no}, filesize: {filesize})")
    except Exception as e:
        raise NetworkConnectionError(
            f"READY mesajı gönderilemedi",
            details=str(e),
            host="",
            port=0
        ) from e


def receive_file_data(data_conn: socket.socket, expected_size: int, buffer_size: int = 65536, timeout: float = 300.0) -> Tuple[bytes, int]:
    """
    Receive file data from data connection with optimized buffer size
    
    Args:
        buffer_size: Default 64KB for faster transfers (can be overridden)
    
    Returns:
        Tuple of (file_data, bytes_received)
        Note: May return less than expected_size if connection closes early
    """
    data_conn.settimeout(timeout)
    received = 0
    file_data_chunks = []
    
    # Use larger buffer for better performance
    optimal_buffer = max(buffer_size, 65536)  # At least 64KB
    
    while received < expected_size:
        remaining = expected_size - received
        chunk_size = min(optimal_buffer, remaining)
        try:
            chunk = data_conn.recv(chunk_size)
            if not chunk:
                break
            file_data_chunks.append(chunk)
            received += len(chunk)
        except socket.timeout:
            raise FileTransferError(
                f"Dosya alma zaman aşımı",
                details=f"Beklenen: {expected_size} bytes, Alınan: {received} bytes",
                filename="",
                expected_size=expected_size,
                actual_size=received
            )
    
    return b''.join(file_data_chunks), received


def send_file_data(data_conn: socket.socket, file_data: bytes, buffer_size: int = 65536, timeout: float = 300.0) -> int:
    """
    Send file data through data connection with optimized buffer size
    
    Args:
        buffer_size: Default 64KB for faster transfers (can be overridden)
    """
    data_conn.settimeout(timeout)
    sent = 0
    total_size = len(file_data)
    
    # Use larger buffer for better performance
    optimal_buffer = max(buffer_size, 65536)  # At least 64KB
    
    while sent < total_size:
        remaining = total_size - sent
        chunk_size = min(optimal_buffer, remaining)
        chunk = file_data[sent:sent + chunk_size]
        if not chunk:
            break
        
        try:
            data_conn.sendall(chunk)
            sent += len(chunk)
            
            # Log progress less frequently for better performance (every 5MB instead of 1MB)
            if total_size > 5 * 1024 * 1024 and sent % (5 * 1024 * 1024) == 0:
                logging.info(f"Dosya gönderiliyor: {sent}/{total_size} bytes ({sent*100//total_size}%)")
        except socket.timeout:
            raise FileTransferError(
                f"Dosya gönderme zaman aşımı",
                details=f"Gönderilen: {sent}/{total_size} bytes",
                filename="",
                expected_size=total_size,
                actual_size=sent
            )
        except Exception as e:
            raise FileTransferError(
                f"Dosya gönderme hatası",
                details=str(e),
                filename="",
                expected_size=total_size,
                actual_size=sent
            ) from e
    
    if sent < total_size:
        raise FileTransferError(
            f"Dosya transferi tamamlanamadı",
            details=f"Gönderilen: {sent}/{total_size} bytes",
            filename="",
            expected_size=total_size,
            actual_size=sent
        )
    
    return sent

