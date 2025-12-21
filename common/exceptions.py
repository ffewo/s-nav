"""
Sınav Sistemi - Özel Exception Hiyerarşisi
Bu modül tüm özel exception'ları tanımlar.
"""


class ExamSystemError(Exception):
    """Tüm sınav sistemi exception'larının temel sınıfı"""
    
    def __init__(self, message: str, details: str = ""):
        super().__init__(message)
        self.message = message
        self.details = details
    
    def __str__(self):
        if self.details:
            return f"{self.message} | Detaylar: {self.details}"
        return self.message


class NetworkConnectionError(ExamSystemError):
    """Ağ bağlantı hataları"""
    
    def __init__(self, message: str, details: str = "", host: str = "", port: int = 0):
        super().__init__(message, details)
        self.host = host
        self.port = port


class ProtocolViolationError(ExamSystemError):
    """Protokol ihlali hataları (yanlış FTP komutları, format hataları)"""
    
    def __init__(self, message: str, details: str = "", command: str = ""):
        super().__init__(message, details)
        self.command = command


class FileTransferError(ExamSystemError):
    """Dosya transfer hataları (upload/download başarısız)"""
    
    def __init__(self, message: str, details: str = "", filename: str = "", 
                 expected_size: int = 0, actual_size: int = 0):
        super().__init__(message, details)
        self.filename = filename
        self.expected_size = expected_size
        self.actual_size = actual_size


class AuthenticationError(ExamSystemError):
    """Kimlik doğrulama hataları (login başarısız)"""
    
    def __init__(self, message: str, details: str = "", student_no: str = ""):
        super().__init__(message, details)
        self.student_no = student_no


class FileOperationError(ExamSystemError):
    """Dosya işlem hataları (okuma, yazma, kaydetme)"""
    
    def __init__(self, message: str, details: str = "", filepath: str = ""):
        super().__init__(message, details)
        self.filepath = filepath


class ConfigurationError(ExamSystemError):
    """Konfigürasyon hataları"""
    
    def __init__(self, message: str, details: str = "", config_key: str = ""):
        super().__init__(message, details)
        self.config_key = config_key


class SecurityError(ExamSystemError):
    """Güvenlik hataları (yasaklı uygulamalar, yetkisiz erişim)"""
    
    def __init__(self, message: str, details: str = "", action: str = ""):
        super().__init__(message, details)
        self.action = action

