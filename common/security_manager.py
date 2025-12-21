import psutil
import logging
import time
from typing import List


class SecurityManager:

    def __init__(self, banned_apps: List[str], check_interval: float = 2.0):

        self.banned_apps = banned_apps
        self.check_interval = check_interval
        self.running = False
    
    def start_monitoring(self, app_running_callback):

        self.running = True
        
        def monitor_loop():
            while self.running and app_running_callback():
                try:
                    self._kill_banned_apps()
                except Exception as e:
                    logging.error(f"Security monitor hatası: {e}")
                time.sleep(self.check_interval)
        
        import threading
        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()
        return thread
    
    def stop_monitoring(self):
        self.running = False
    
    def _kill_banned_apps(self):
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

