import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import threading
import os
import sys
import time
import logging
from common import get_config, NetworkConnectionError, FileTransferError, ProtocolViolationError
from common.security_manager import SecurityManager
from client import ClientCore
try:
    import winsound
except ImportError:
    winsound = None

config = get_config()


class SinavClientGUI:
    
    def __init__(self, root):
        self.root = root
        self.root.title("Sınav Sistemi - Öğrenci")
        width = config.get("ui.window_width", 600)
        height = config.get("ui.window_height", 500)
        self.root.geometry(f"{width}x{height}")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Security manager - Use hardcoded list for security (not from config)
        # Config'den alınmaz çünkü öğrenciler config dosyasını değiştirebilir
        banned_apps = [
            "chrome.exe",
            "firefox.exe", 
            "msedge.exe",
            "opera.exe",
            "safari.exe",
            "brave.exe",
            "vivaldi.exe",
            "tor.exe",
            "tor-browser.exe"
        ]
        self.security_manager = SecurityManager(banned_apps)
        self.app_running = True
        self.security_manager.start_monitoring(lambda: self.app_running)
        
        # Upload progress UI state
        self.upload_progress_window = None
        self.upload_progress_var = tk.DoubleVar(value=0.0)
        self.upload_progress_label = None
        
        # Initialize ClientCore with callbacks
        self.core = ClientCore(
            ui_status_callback=self.update_status,
            ui_timer_callback=self.update_timer,
            ui_message_callback=self.show_message,
            ui_exam_started_callback=self.activate_upload_button,
            ui_shutdown_callback=self.on_close
        )
        
        logging.info("Sınav sistemi başlatıldı")
        self.setup_login_ui()
        
        # Connect to server in background
        threading.Thread(target=self._connect_background, daemon=True).start()
    
    def _connect_background(self):
        """Connect to server in background thread"""
        if not self.core.connect_to_server():
            # Connection failed, UI already shows error
            return
        # Start server listener
        threading.Thread(target=self.core.server_listener, daemon=True).start()
    
    def update_status(self, status_text: str, color: str):
        """Status callback from ClientCore"""
        def update():
            if hasattr(self, 'status_label') and self.status_label.winfo_exists():
                try:
                    self.status_label.config(text=status_text, fg=color)
                except tk.TclError:
                    # Widget destroyed, ignore
                    pass
        self.root.after(0, update)
    
    def update_timer(self, seconds: int, color: str):
        """Timer callback from ClientCore"""
        def update():
            if hasattr(self, 'timer_label') and self.timer_label.winfo_exists():
                try:
                    mins, secs = divmod(seconds, 60)
                    self.timer_label.config(text=f"Süre: {mins:02d}:{secs:02d}", fg=color)
                except tk.TclError:
                    # Widget destroyed, ignore
                    pass
        self.root.after(0, update)
    
    def show_message(self, message: str, title: str, msg_type: str):
        """Message callback from ClientCore"""
        def safe_show():
            try:
                if self.root.winfo_exists():
                    self._show_message_safe(message, title, msg_type)
            except (tk.TclError, RuntimeError):
                # Root destroyed or not in main loop, ignore
                pass
        try:
            self.root.after(0, safe_show)
        except (tk.TclError, RuntimeError):
            # Root destroyed or not in main loop, ignore
            pass
    
    def _show_message_safe(self, message: str, title: str, msg_type: str):
        """Thread-safe message display"""
        if msg_type == "error":
            messagebox.showerror(title, message)
        elif msg_type == "warning":
            messagebox.showwarning(title, message)
        else:
            messagebox.showinfo(title, message)
    
    def activate_upload_button(self):
        """Activate upload button when exam starts - callback from ClientCore"""
        if hasattr(self, 'upload_btn'):
            self.root.after(0, lambda: self.upload_btn.config(
                state="normal", bg="#FF5722", text="DOSYA YÜKLE / TESLİM ET"
            ))
    
    def setup_login_ui(self):
        """Setup login UI"""
        for w in self.root.winfo_children(): 
            w.destroy()
        f = tk.Frame(self.root, padx=20, pady=20)
        f.place(relx=0.5, rely=0.5, anchor="center")
        
        tk.Label(f, text="ÖĞRENCİ GİRİŞİ", font=("Arial", 16)).pack(pady=10)
        tk.Label(f, text="Numara:").pack(anchor="w")
        self.entry_no = tk.Entry(f, width=30)
        self.entry_no.pack(pady=5)
        tk.Label(f, text="Şifre:").pack(anchor="w")
        self.entry_pw = tk.Entry(f, width=30, show="*")
        self.entry_pw.pack(pady=5)
        self.status_label = tk.Label(f, text="Bağlanıyor...", fg="grey")
        self.status_label.pack()
        tk.Button(f, text="GİRİŞ", command=self.handle_login, bg="#4CAF50", fg="white", width=20).pack(pady=10)
    
    def setup_main_ui(self):
        """Setup main exam UI"""
        for w in self.root.winfo_children(): 
            w.destroy()
        
        info_frame = tk.Frame(self.root, bg="#eee", pady=10)
        info_frame.pack(fill="x")
        tk.Label(info_frame, text=f"Öğrenci: {self.core.student_no}", 
                 font=("Arial", 12, "bold"), bg="#eee").pack(side="left", padx=10)
        self.timer_label = tk.Label(info_frame, text="Süre: Bekliyor...", 
                                    font=("Arial", 14, "bold"), fg="blue", bg="#eee")
        self.timer_label.pack(side="right", padx=10)
        
        tk.Label(self.root, text="SINAV DOSYALARI", font=("Arial", 10)).pack(pady=5)
        
        list_frame = tk.Frame(self.root)
        list_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        self.file_listbox = tk.Listbox(list_frame, height=15)
        self.file_listbox.pack(side="left", fill="both", expand=True)
        
        btn_frame = tk.Frame(self.root, pady=10)
        btn_frame.pack(fill="x", padx=20)
        
        tk.Button(btn_frame, text="Listeyi Yenile", command=self.refresh_list).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Seçili Dosyayı İNDİR", command=self.download_and_open, 
                 bg="#2196F3", fg="white").pack(side="left", padx=5)
        
        # UPLOAD BUTONU (Başlangıçta KAPALI)
        self.upload_btn = tk.Button(btn_frame, text="DOSYA YÜKLE / TESLİM ET", 
                                   command=self.select_and_upload, bg="#FF5722", fg="white", height=2)
        self.upload_btn.pack(side="right", padx=5)
        self.upload_btn.config(state="disabled", bg="gray", text="SINAVIN BAŞLAMASINI BEKLEYİN")
        
        self.refresh_list()
    
    def handle_login(self):
        """Handle login - uses ClientCore"""
        no = self.entry_no.get().strip()
        pw = self.entry_pw.get().strip()
        
        # Validation
        if not no or not pw:
            messagebox.showwarning("Uyarı", "Geçerli bir öğrenci numarası ve şifre giriniz!")
            return
        
        if not no.isdigit():
            messagebox.showwarning("Uyarı", "Öğrenci numarası sadece rakamlardan oluşmalıdır!")
            return
        
        # Use ClientCore for login
        if self.core.login(no, pw):
            self.setup_main_ui()
        else:
            # Login failed, clear password field
            self.entry_pw.delete(0, 'end')
            self.entry_pw.focus()
    
    def refresh_list(self):
        """Refresh file list - uses ClientCore"""
        threading.Thread(target=self._refresh_thread, daemon=True).start()
    
    def _refresh_thread(self):
        """Refresh file list thread"""
        files = self.core.get_file_list()
        self.root.after(0, lambda f=files: self._update_list(f))
    
    def _update_list(self, files):
        """Update file listbox"""
        self.file_listbox.delete(0, tk.END)
        for f in files:
            if f:
                self.file_listbox.insert(tk.END, f)
    
    def download_and_open(self):
        """Download selected file - uses ClientCore"""
        if not self.core.exam_started:
            messagebox.showwarning("Uyarı", "Sınav henüz başlamadı! Dosya indiremezsiniz.")
            return
        
        selection = self.file_listbox.curselection()
        if not selection:
            messagebox.showwarning("Uyarı", "Dosya seçmediniz.")
            return
        
        filename = self.file_listbox.get(selection[0])
        threading.Thread(target=self._download_thread, args=(filename,), daemon=True).start()
    
    def _download_thread(self, filename):
        """Download file thread - uses ClientCore"""
        try:
            save_path = os.path.join(os.getcwd(), filename)
            success, received = self.core.download_file(filename, save_path)
            
            if success:
                self.root.after(0, lambda: messagebox.showinfo("Başarılı", 
                    f"{filename} başarıyla indirildi!\n\n"
                    f"Dosya çalışma dizinine kaydedildi:\n{save_path}"))
                logging.info(f"Dosya başarıyla indirildi: {filename} ({received} bytes)")
            else:
                self.root.after(0, lambda: messagebox.showerror("İndirme Hatası", 
                    "Dosya indirilemedi!"))
        except FileTransferError as e:
            self.root.after(0, lambda: messagebox.showerror("İndirme Hatası", 
                f"{e.message}\n\n{e.details}"))
        except NetworkConnectionError as e:
            self.root.after(0, lambda: messagebox.showerror("Bağlantı Hatası", 
                f"{e.message}\n\n{e.details}"))
        except Exception as e:
            logging.error(f"Dosya indirme hatası: {e}")
            self.root.after(0, lambda: messagebox.showerror("İndirme Hatası", 
                f"Dosya indirilemedi!\n\nHata: {str(e)}"))
    
    def select_and_upload(self):
        """Select and upload files - uses ClientCore"""
        if not self.core.exam_started:
            messagebox.showwarning("Uyarı", "Sınav henüz başlamadı!")
            return
        
        filepaths = filedialog.askopenfilenames(
            title="Gönderilecek Dosyaları Seçin (Birden fazla seçebilirsiniz)"
        )
        if not filepaths:
            return
        
        total_files = len(filepaths)
        threading.Thread(target=self._upload_multiple_files, args=(filepaths, total_files), daemon=True).start()
    
    def _upload_multiple_files(self, filepaths, total_files):
        """Upload multiple files - uses ClientCore"""
        uploaded_count = 0
        failed_files = []
        
        for idx, filepath in enumerate(filepaths):
            filename = os.path.basename(filepath)
            logging.info(f"Dosya {idx + 1}/{total_files} gönderiliyor: {filename}")
            
            try:
                # Show progress
                self.root.after(0, lambda fn=filename: self.show_upload_progress(fn))
                
                # Progress callback
                def progress_callback(percent, fn):
                    self.root.after(0, lambda p=percent, f=fn: self.update_upload_progress(p, f))
                
                success, bytes_sent = self.core.upload_file(filepath, filename, progress_callback)
                
                if success:
                    uploaded_count += 1
                    logging.info(f"Dosya {idx + 1}/{total_files} başarıyla gönderildi: {filename}")
                    if idx < total_files - 1:
                        time.sleep(0.5)
                else:
                    failed_files.append(filename)
            except FileTransferError as e:
                failed_files.append(filename)
                logging.error(f"Dosya {idx + 1}/{total_files} gönderilemedi: {filename} - {e.message}")
            except Exception as e:
                failed_files.append(filename)
                logging.error(f"Dosya {idx + 1}/{total_files} gönderilemedi: {filename} - {e}")
            finally:
                self.root.after(0, self.close_upload_progress)
        
        # Show summary
        if uploaded_count > 0:
            if len(failed_files) == 0:
                if total_files == 1:
                    self.root.after(0, self.finish_exam_shutdown)
                else:
                    self.root.after(0, lambda: messagebox.showinfo("Başarılı", 
                        f"Tüm dosyalar başarıyla gönderildi!\n\nGönderilen: {uploaded_count} dosya"))
                    self.root.after(0, self.finish_exam_shutdown)
            else:
                failed_list = "\n".join(failed_files)
                self.root.after(0, lambda: messagebox.showwarning("Kısmi Başarı", 
                    f"Gönderilen: {uploaded_count} dosya\n"
                    f"Başarısız: {len(failed_files)} dosya\n\n"
                    f"Başarısız dosyalar:\n{failed_list}"))
                self.root.after(0, self.finish_exam_shutdown)
    
    def show_upload_progress(self, filename):
        """Show upload progress window"""
        if self.upload_progress_window and self.upload_progress_window.winfo_exists():
            self.upload_progress_var.set(0)
            if self.upload_progress_label:
                self.upload_progress_label.config(text=f"{filename} yükleniyor... %0")
            return
        
        self.upload_progress_window = tk.Toplevel(self.root)
        self.upload_progress_window.title("Yükleniyor")
        self.upload_progress_window.geometry("350x120")
        self.upload_progress_window.resizable(False, False)
        self.upload_progress_window.grab_set()
        
        tk.Label(self.upload_progress_window, text="Dosya yükleniyor, lütfen bekleyin...", 
                font=("Arial", 10)).pack(pady=5)
        self.upload_progress_label = tk.Label(self.upload_progress_window, 
                                             text=f"{filename} yükleniyor... %0")
        self.upload_progress_label.pack(pady=5)
        
        pb = ttk.Progressbar(self.upload_progress_window, orient="horizontal", length=300,
                             mode="determinate", maximum=100, variable=self.upload_progress_var)
        pb.pack(pady=5)
    
    def update_upload_progress(self, percent, filename=None):
        """Update upload progress"""
        if not (self.upload_progress_window and self.upload_progress_window.winfo_exists()):
            return
        self.upload_progress_var.set(percent)
        if self.upload_progress_label:
            if filename:
                self.upload_progress_label.config(text=f"{filename} yükleniyor... %{percent:.1f}")
            else:
                self.upload_progress_label.config(text=f"Yükleniyor... %{percent:.1f}")
    
    def close_upload_progress(self):
        """Close upload progress window"""
        if self.upload_progress_window and self.upload_progress_window.winfo_exists():
            try:
                self.upload_progress_window.destroy()
            except Exception:
                pass
        self.upload_progress_window = None
        self.upload_progress_label = None
        self.upload_progress_var.set(0)
    
    def finish_exam_shutdown(self):
        """Finish exam and shutdown"""
        messagebox.showinfo("Başarılı", "Sınav dosyanız gönderildi. Sistem kapatılıyor.")
        self.on_close()
    
    def on_close(self):
        """Close application"""
        self.app_running = False
        self.core.quit()
        try:
            self.root.destroy()
        except:
            pass
        os._exit(0)


if __name__ == "__main__":
    root = tk.Tk()
    app = SinavClientGUI(root)
    root.mainloop()

