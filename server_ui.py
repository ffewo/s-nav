"""Sınav Sistemi - Öğretmen Sunucu UI"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import logging
import os
from datetime import datetime
from config_manager import get_config
from server import ServerCore, load_students, connected_students
from exceptions import NetworkConnectionError

config = get_config()


class TeacherServerGUI:
    """Teacher Server UI - Uses ServerCore for all business logic"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Öğretmen Kontrol Paneli - Sınav Sistemi")
        width = config.get("ui.window_width", 900)
        height = config.get("ui.window_height", 600)
        self.root.geometry(f"{width}x{height}")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Initialize ServerCore with UI update callback
        self.core = ServerCore(ui_update_callback=self.update_ui_list)
        self.start_time = None
        
        logging.info("Öğretmen kontrol paneli başlatıldı")
        self.setup_ui()
        self.start_server()
        self.update_connection_count()
        self.update_timer_display()
    
    def setup_ui(self):
        """UI bileşenlerini oluştur"""
        # Üst kontrol paneli
        top_frame = tk.Frame(self.root, pady=10, bg="#f0f0f0")
        top_frame.pack(side=tk.TOP, fill=tk.X)
        
        left_buttons = tk.Frame(top_frame, bg="#f0f0f0")
        left_buttons.pack(side=tk.LEFT)
        
        tk.Button(left_buttons, text="🚀 Sınavı Başlat", bg="#d32f2f", fg="white", 
                 font=("Arial", 10, "bold"), command=self.start_exam_timer).pack(side=tk.LEFT, padx=5)
        tk.Button(left_buttons, text="⏱️ Süre Uzat", bg="#9C27B0", fg="white", 
                 font=("Arial", 10), command=self.extend_exam_time).pack(side=tk.LEFT, padx=5)
        tk.Button(left_buttons, text="📢 Duyuru Gönder", bg="#2196F3", fg="white", 
                 font=("Arial", 10), command=self.send_broadcast).pack(side=tk.LEFT, padx=5)
        tk.Button(left_buttons, text="🔓 Girişleri Aç", bg="#4CAF50", fg="white",
                 font=("Arial", 10), command=self.unlock_entries).pack(side=tk.LEFT, padx=5)
        tk.Button(left_buttons, text="📊 İstatistikler", bg="#FF9800", fg="white",
                 font=("Arial", 10), command=self.show_statistics).pack(side=tk.LEFT, padx=5)
        
        right_info = tk.Frame(top_frame, bg="#f0f0f0")
        right_info.pack(side=tk.RIGHT)
        
        self.timer_lbl = tk.Label(right_info, text="⏰ Süre: --:--", fg="blue", 
                                 font=("Arial", 12, "bold"), bg="#f0f0f0")
        self.timer_lbl.pack(side=tk.RIGHT, padx=10)
        
        self.status_lbl = tk.Label(right_info, text="✅ Durum: Girişler AÇIK", fg="green", 
                                  font=("Arial", 10, "bold"), bg="#f0f0f0")
        self.status_lbl.pack(side=tk.RIGHT, padx=10)
        
        # Bağlantı sayısı - daha görünür bir yerde (başlık çubuğunda)
        self.connection_lbl = tk.Label(right_info, text="👥 0", 
                                      fg="#1976D2", font=("Arial", 16, "bold"), bg="#f0f0f0")
        self.connection_lbl.pack(side=tk.RIGHT, padx=15)
        
        # Bağlantı sayısı banner (büyük ve görünür)
        connection_banner = tk.Frame(self.root, bg="#E3F2FD", pady=8)
        connection_banner.pack(fill=tk.X, padx=10, pady=(5, 0))
        
        self.connection_banner_lbl = tk.Label(
            connection_banner, 
            text="🌐 BAĞLI ÖĞRENCİ SAYISI: 0", 
            font=("Arial", 14, "bold"), 
            fg="#1976D2", 
            bg="#E3F2FD"
        )
        self.connection_banner_lbl.pack()
        
        # Öğrenci listesi
        list_frame = tk.Frame(self.root)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tk.Label(list_frame, text="👥 Bağlı Öğrenciler", font=("Arial", 12, "bold")).pack(anchor="w")
        
        tree_frame = tk.Frame(list_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("No", "Ad", "IP", "Durum", "Bağlantı", "Son İşlem", "Teslim Dosyası", "Teslim Zamanı"),
            show='headings'
        )
        
        for col, text in [("No", "Öğrenci No"), ("Ad", "Ad Soyad"), ("IP", "IP Adresi"),
                          ("Durum", "Durum"), ("Bağlantı", "Bağlantı Zamanı"),
                          ("Son İşlem", "Son Aktivite"), ("Teslim Dosyası", "Teslim Dosyası"),
                          ("Teslim Zamanı", "Teslim Zamanı")]:
            self.tree.heading(col, text=text)
        
        widths = [80, 140, 110, 90, 120, 220, 160, 110]
        for col, width in zip(self.tree["columns"], widths):
            self.tree.column(col, width=width)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def start_server(self):
        """Sunucuyu başlat - uses ServerCore"""
        try:
            if self.core.start_server():
                HOST_IP = config.get("server.host", "0.0.0.0")
                CONTROL_PORT = config.get("server.port", 2121)
                MAX_CONNECTIONS = config.get("server.max_connections", 50)
                messagebox.showinfo("Sunucu Başlatıldı", 
                                  f"Sınav sunucusu başarıyla başlatıldı!\n\n"
                                  f"IP: {HOST_IP}\n"
                                  f"Control Port: {CONTROL_PORT}\n"
                                  f"Maksimum bağlantı: {MAX_CONNECTIONS}")
            else:
                raise Exception("Sunucu başlatılamadı")
        except NetworkConnectionError as e:
            error_msg = f"Sunucu başlatılamadı: {e.message}\n\nDetaylar: {e.details}\n\nMuhtemel nedenler:\n• Port zaten kullanımda\n• Yönetici izni gerekli"
            logging.error(error_msg)
            messagebox.showerror("Sunucu Hatası", error_msg)
            self.root.destroy()
        except Exception as e:
            CONTROL_PORT = config.get("server.port", 2121)
            error_msg = f"Sunucu başlatılamadı: {e}\n\nMuhtemel nedenler:\n• Port {CONTROL_PORT} zaten kullanımda\n• Yönetici izni gerekli"
            logging.error(error_msg)
            messagebox.showerror("Sunucu Hatası", error_msg)
            self.root.destroy()
    
    def update_connection_count(self):
        """Bağlantı sayısını güncelle"""
        if self.core.server_running:
            count = self.core.get_connection_count()
            # Başlık çubuğundaki küçük gösterge
            self.connection_lbl.config(text=f"👥 {count}")
            # Banner'daki büyük gösterge
            if hasattr(self, 'connection_banner_lbl'):
                self.connection_banner_lbl.config(text=f"🌐 BAĞLI ÖĞRENCİ SAYISI: {count}")
            # Başlık çubuğunu da güncelle
            self.root.title(f"Öğretmen Kontrol Paneli - Sınav Sistemi | Bağlı: {count} öğrenci")
            self.root.after(5000, self.update_connection_count)
    
    def update_timer_display(self):
        """Timer display'ini güncelle"""
        status = self.core.get_exam_status()
        if status["timer_running"] and status["time_remaining"] > 0:
            mins, secs = divmod(status["time_remaining"], 60)
            self.timer_lbl.config(text=f"Süre: {mins:02}:{secs:02}", fg="red")
            self.root.after(1000, self.update_timer_display)
        elif status["timer_running"] and status["time_remaining"] <= 0:
            self.timer_lbl.config(text="Süre: 00:00", fg="red")
            messagebox.showinfo("Sınav Bitti", "Sınav süresi doldu!")
    
    def show_statistics(self):
        """İstatistikleri göster"""
        stats_window = tk.Toplevel(self.root)
        stats_window.title("📊 Sınav İstatistikleri")
        stats_window.geometry("500x400")
        
        stats_text = tk.Text(stats_window, wrap=tk.WORD, padx=10, pady=10)
        stats_text.pack(fill=tk.BOTH, expand=True)
        
        total_students = len(load_students())
        connected_count = self.core.get_connection_count()
        status = self.core.get_exam_status()
        start_time_display = status.get("start_time") if status.get("start_time") else "Henüz başlamadı"
        
        stats_content = f"""📊 SINAV SİSTEMİ İSTATİSTİKLERİ
{'='*50}

👥 Öğrenci Bilgileri:
• Toplam kayıtlı öğrenci: {total_students}
• Şu anda bağlı: {connected_count}
• Bağlantı oranı: %{(connected_count/total_students*100) if total_students > 0 else 0:.1f}

⏰ Sınav Durumu:
• Sınav durumu: {'BAŞLADI' if status['exam_started'] else 'BAŞLAMADI'}
• Kalan süre: {status['time_remaining']//60:02d}:{status['time_remaining']%60:02d}
• Başlangıç zamanı: {start_time_display}

📁 Dosya Durumu:
• Soru dosyası sayısı: {len(os.listdir('Sorular')) if os.path.exists('Sorular') else 0}
• Teslim edilen cevap: {len(os.listdir('Cevaplar')) if os.path.exists('Cevaplar') else 0}

🔗 Bağlantı Detayları:"""
        
        for student_no, data in connected_students.items():
            stats_content += f"\n• {student_no} ({data.get('name', 'Bilinmiyor')}) - {data['addr'][0]}"
        
        stats_text.insert(tk.END, stats_content)
        stats_text.config(state=tk.DISABLED)
    
    def on_closing(self):
        """Uygulama kapatılırken"""
        if messagebox.askokcancel("Çıkış", "Sınav sunucusunu kapatmak istediğinizden emin misiniz?"):
            self.core.stop_server()
            logging.info("Sunucu kapatılıyor...")
            self.root.destroy()
    
    def start_exam_timer(self):
        """Sınav timer'ını başlat - uses ServerCore"""
        mins = simpledialog.askinteger("Süre", "Sınav süresi kaç dakika?")
        if mins:
            if self.core.start_exam_timer(mins):
                self.start_time = datetime.now().strftime("%H:%M:%S")
                self.status_lbl.config(text="Durum: SINAV BAŞLADI", fg="red")
                self.update_timer_display()
            else:
                messagebox.showerror("Hata", "Sınav timer'ı başlatılamadı!")
    
    def extend_exam_time(self):
        """Sınav süresini uzat - uses ServerCore"""
        status = self.core.get_exam_status()
        if not status["exam_started"] or not status["timer_running"]:
            messagebox.showwarning("Uyarı", "Sınav başlamadı! Önce sınavı başlatmalısınız.")
            return
        
        current_minutes = status["time_remaining"] // 60
        additional = simpledialog.askinteger(
            "Süre Uzat", 
            f"Mevcut süre: {current_minutes} dakika\n\nKaç dakika eklemek istersiniz?",
            minvalue=1,
            maxvalue=120
        )
        
        if additional:
            if self.core.extend_exam_time(additional):
                new_total = (status["time_remaining"] + (additional * 60)) // 60
                messagebox.showinfo(
                    "Başarılı", 
                    f"Sınav süresi {additional} dakika uzatıldı!\n\n"
                    f"Yeni toplam süre: {new_total} dakika"
                )
                logging.info(f"Sınav süresi {additional} dakika uzatıldı")
            else:
                messagebox.showerror("Hata", "Süre uzatılamadı!")
    
    def unlock_entries(self):
        """Girişleri aç - uses ServerCore"""
        self.core.unlock_entries()
        self.status_lbl.config(text="Durum: Girişler AÇIK", fg="green")
        self.timer_lbl.config(text="Süre: --:--", fg="blue")
    
    def send_broadcast(self):
        """Duyuru gönder - uses ServerCore"""
        msg = simpledialog.askstring("Duyuru", "Mesaj:")
        if msg:
            self.core.send_broadcast(msg)
    
    def update_ui_list(self, no, name, ip, status, connection_time, action, delivery_file=None, delivery_time=None):
        """UI listesini güncelle - callback from ServerCore"""
        def safe_update():
            try:
                if self.root.winfo_exists():
                    self._update_tree_safe(no, name, ip, status, connection_time, action, delivery_file, delivery_time)
            except (tk.TclError, RuntimeError):
                # Root destroyed or not in main loop, ignore
                pass
        try:
            self.root.after(0, safe_update)
        except (tk.TclError, RuntimeError):
            # Root destroyed or not in main loop, ignore
            pass
    
    def _update_tree_safe(self, no, name, ip, status, connection_time, action, delivery_file=None, delivery_time=None):
        """Thread-safe UI güncellemesi"""
        try:
            if not self.root.winfo_exists():
                return
            
            str_no = str(no).strip()
            found_item = None
            
            for item in self.tree.get_children():
                try:
                    item_vals = self.tree.item(item)['values']
                    if len(item_vals) > 0 and str(item_vals[0]).strip() == str_no:
                        found_item = item
                        break
                except (tk.TclError, RuntimeError):
                    continue
            
            if delivery_file is None and str_no in connected_students:
                delivery_file = connected_students[str_no].get("delivery_file", "")
            if delivery_time is None and str_no in connected_students:
                delivery_time = connected_students[str_no].get("delivery_time", "")
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            action_with_time = f"[{timestamp}] {action}"
            
            values = (str_no, name, ip, status, connection_time, action_with_time, delivery_file or "", delivery_time or "")
            
            if found_item:
                self.tree.item(found_item, values=values)
            else:
                self.tree.insert("", "end", values=values)
        except (tk.TclError, RuntimeError):
            # Root destroyed or not in main loop, ignore
            pass


if __name__ == "__main__":
    root = tk.Tk()
    app = TeacherServerGUI(root)
    root.mainloop()

