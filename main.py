import sys
import json
import os
import calendar
import uuid
import urllib.request
import tkinter as ttk_lib # type: ignore
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime, timedelta
from supabase import create_client, Client
from PIL import Image, ImageTk 

SUPABASE_URL = "https://hmjqpfvedzacedrpusfo.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhtanFwZnZlZHphY2VkcnB1c2ZvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODkxMzAwNDQsImV4cCI6MjEwNDcwNjA0NH0.lY3Q6aadK-IZ_rqw-AoPiXKwxP0BSlqAMZ9gTBzlv0k"

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print("Supabase bağlantı hatası:", e)
    supabase = None

DATA_FILE = "data.json"

class ToolTip:
    def __init__(self, widget):
        self.widget = widget
        self.tipwindow = None

    def showtip(self, text, x, y):
        if self.tipwindow:
            return
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(1)
        tw.wm_geometry(f"+{x+15}+{y+15}")
        
        label = tk.Label(tw, text=text, justify=tk.LEFT,
                         background="#ffffe0", foreground="#000000",
                         relief=tk.SOLID, borderwidth=1,
                         font=("Segoe UI", 9, "bold"), padx=6, pady=3)
        label.pack()

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

class CNCPlanningApp:
    def __init__(self, root):
        self.root = root
        self.root.title("EAGEAN DYNAMICS - CNC Atölyesi Üretim Planlama ve Kapasite Yönetimi (Cloud)")
        
        try:
            self.root.iconbitmap("logo.ico")
        except Exception:
            pass

        self.root.geometry("1400x900")
        self.root.configure(bg="#ffffff")
        
        self.root.rowconfigure(2, weight=1)
        self.root.columnconfigure(0, weight=1)

        self.jobs = []
        self.editing_job_id = None
        self.part_library = {}
        self.users_list = [] 
        self.machines_list = []  

        self.work_min_weekday = 500       
        self.overtime_min_weekday = 150   
        self.overtime_min_weekend = 500   

        self.days_count = 90
        self.overtime_schedule = {}  

        self.setup_ui()
        self.load_data_from_file()
        
        self.guncelleme_kontrol_et()
        self.root.after(500, self.cloud_veri_senkronizasyon_dongusu)

    def guncelleme_kontrol_et(self):
        try:
            # Doğru kullanıcı adı (egedinamik2026) ile güncellendi[cite: 2]
            url = "https://raw.githubusercontent.com/egedinamik2026/eagean-mobile/main/version.json"
            
            req = urllib.request.urlopen(url, timeout=3)
            data = json.loads(req.read().decode('utf-8'))
            bulut_versiyon = data.get("version", "1.0")
            
            yerel_versiyon = "1.0" 
            
            if bulut_versiyon != yerel_versiyon:
                cevap = messagebox.askyesno(
                    "Güncelleme Var!", 
                    f"Yeni bir sürüm tespit edildi (v{bulut_versiyon}). Güncellemeyi kontrol etmek ister misiniz?"
                )
                if cevap:
                    messagebox.showinfo("Bilgi", "Güncelleme onaylandı.")
        except Exception as e:
            print("Sürüm kontrol edilemedi:", e)

    def cloud_veri_senkronizasyon_dongusu(self):
        try:
            if supabase:
                res = supabase.table("cnc_is_emirleri").select("*").execute()
                if res.data is not None:
                    cloud_orders = res.data
                    updated = False
                    
                    existing_isemris = [str(j.get("isemri", "")).strip() for j in self.jobs]
                    
                    for c_order in cloud_orders:
                        c_isemri = str(c_order.get("malzeme_kodu", "")).strip()
                        durum_val = c_order.get("durum", "{}")
                        try:
                            durum_dict = json.loads(durum_val) if isinstance(durum_val, str) else (durum_val or {})
                        except Exception:
                            durum_dict = {}

                        if durum_dict.get("isStarted") == True and not durum_dict.get("isCompleted", False):
                            if c_isemri and c_isemri not in existing_isemris:
                                unplanned_hours = 4.0 
                                
                                tezgah_adi = str(durum_dict.get("torna_tezgah", "") or durum_dict.get("dik_tezgah", "")).upper()
                                bolum = "dik" if "DİK" in tezgah_adi or "DIK" in tezgah_adi else "torna"
                                
                                if "dik" in str(durum_dict).lower() and "torna" not in str(durum_dict).lower():
                                    bolum = "dik"

                                new_unplanned_job = {
                                    "id": len(self.jobs) + 1,
                                    "unique_id": c_order.get("unique_id", str(uuid.uuid4())),
                                    "qty": c_order.get("hedef_adet", 1),
                                    "isemri": c_isemri,
                                    "material": "PLANSIZ-SAHA",
                                    "t_setup": 0, "t_op1": 0, "t_op2": 0, "t_op3": 0,
                                    "d_setup": 0, "d_op1": 0, "d_op2": 0, "d_op3": 0,
                                    "torna_total_hours": unplanned_hours if bolum == "torna" else 0.0,
                                    "dik_total_hours": unplanned_hours if bolum == "dik" else 0.0,
                                    "total_hours": unplanned_hours,
                                    "torna_rank": 1,
                                    "dik_rank": 1,
                                    "torna_finished": True if bolum != "torna" else False,
                                    "dik_finished": True if bolum != "dik" else False,
                                    "cloud_durum": durum_dict
                                }
                                self.jobs.insert(0, new_unplanned_job)
                                updated = True

                    for job in self.jobs:
                        job_isemri = str(job.get("isemri", "")).strip()
                        if not job_isemri:
                            continue

                        matched_c_order = None
                        for c_order in cloud_orders:
                            c_isemri = str(c_order.get("malzeme_kodu", "")).strip()
                            if c_isemri and job_isemri == c_isemri:
                                matched_c_order = c_order
                                break

                        if matched_c_order:
                            try:
                                durum_val = matched_c_order.get("durum", "{}")
                                durum_dict = json.loads(durum_val) if isinstance(durum_val, str) else (durum_val or {})
                                job["cloud_durum"] = durum_dict

                                torna_bitti_sinyal = (durum_dict.get("tornaCompleted") == True)
                                dik_bitti_sinyal = (durum_dict.get("dikCompleted") == True)

                                if job.get("torna_total_hours", 0) > 0:
                                    if torna_bitti_sinyal and not job.get("torna_finished", False):
                                        job["torna_finished"] = True
                                        updated = True
                                        
                                        if job.get("material") == "PLANSIZ-SAHA":
                                            job["torna_total_hours"] = 0.0
                                            job["total_hours"] = 0.0

                                if job.get("dik_total_hours", 0) > 0:
                                    if dik_bitti_sinyal and not job.get("dik_finished", False):
                                        job["dik_finished"] = True
                                        updated = True
                                        
                                        if job.get("material") == "PLANSIZ-SAHA":
                                            job["dik_total_hours"] = 0.0
                                            job["total_hours"] = 0.0

                            except Exception as e:
                                print("Senkronizasyon ayrıştırma hatası:", e)

                    if updated:
                        self.refresh_all_views()
                        self.save_data_to_file()
        except Exception as e:
            print("Cloud senkronizasyon hatası:", e)
        
        self.root.after(500, self.cloud_veri_senkronizasyon_dongusu)

    def fmt_num(self, val):
        try:
            val_float = float(val)
            if val_float.is_integer():
                return str(int(val_float))
            return str(round(val_float, 2))
        except Exception:
            return str(val)

    def format_tarih_tr(self, tarih_str):
        if not tarih_str: return '-'
        try:
            parts = tarih_str.split('T')
            if len(parts) == 2:
                date_parts = parts[0].split('-')
                if len(date_parts) == 3:
                    return f"{date_parts[2]}.{date_parts[1]}.{date_parts[0]} {parts[1]}"
            return tarih_str
        except Exception:
            return tarih_str

    def is_public_holiday(self, date_obj):
        m, d, y = date_obj.month, date_obj.day, date_obj.year
        date_str = date_obj.strftime("%Y-%m-%d")
        
        fixed_holidays = [(1, 1), (4, 23), (5, 1), (5, 19), (7, 15), (8, 30), (10, 29)]
        if (m, d) in fixed_holidays:
            return True
            
        holidays_2026 = ["2026-03-20", "2026-03-21", "2026-03-22", "2026-05-27", "2026-05-28", "2026-05-29", "2026-05-30"]
        holidays_2027 = ["2027-03-10", "2027-03-11", "2027-03-12", "2027-05-16", "2027-05-17", "2027-05-18", "2027-05-19"]
        
        if y == 2026 and date_str in holidays_2026: return True
        if y == 2027 and date_str in holidays_2027: return True
        return False

    def load_data_from_file(self):
        if supabase:
            try:
                res_u = supabase.table("kullanıcılar").select("*").execute()
                if res_u.data:
                    self.users_list = res_u.data
                
                res_m = supabase.table("tezgahlar").select("*").execute()
                if res_m.data:
                    self.machines_list = res_m.data
            except Exception as e:
                print("Cloud verileri yüklenirken hata:", e)

        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.jobs = data.get("jobs", [])
                    
                    for j in self.jobs:
                        if not j.get("unique_id"):
                            j["unique_id"] = str(uuid.uuid4())
                        if "torna_finished" not in j:
                            j["torna_finished"] = False if j.get("torna_total_hours", 0) > 0 else True
                        if "dik_finished" not in j:
                            j["dik_finished"] = False if j.get("dik_total_hours", 0) > 0 else True

                    if not self.users_list:
                        self.users_list = data.get("users_list", [])
                    if not self.machines_list:
                        self.machines_list = data.get("machines_list", [])
                    
                    raw_lib = data.get("part_library", {})
                    self.part_library = {}
                    for k, v in raw_lib.items():
                        self.part_library[str(k).upper()] = v
                            
                    raw_overtime = data.get("overtime_schedule", {})
                    self.overtime_schedule = {}
                    for k, v in raw_overtime.items():
                        if isinstance(v, bool):
                            self.overtime_schedule[k] = {"torna": v, "dik": v}
                        else:
                            self.overtime_schedule[k] = v

                    settings = data.get("settings", {})
                    self.work_min_weekday = int(settings.get("work_min_weekday", 500))
                    self.overtime_min_weekday = int(settings.get("overtime_min_weekday", 150))
                    self.overtime_min_weekend = int(settings.get("overtime_min_weekend", 500))

                self.check_overdue_jobs()
                self.refresh_all_views()
            except Exception as e:
                print("Veriler yüklenirken hata oluştu:", e)

    def save_data_to_file(self):
        try:
            data = {
                "jobs": self.jobs,
                "users_list": self.users_list,
                "machines_list": self.machines_list,
                "part_library": self.part_library,
                "overtime_schedule": self.overtime_schedule,
                "settings": {
                    "work_min_weekday": self.work_min_weekday,
                    "overtime_min_weekday": self.overtime_min_weekday,
                    "overtime_min_weekend": self.overtime_min_weekend
                }
            }
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print("Veriler kaydedilirken hata oluştu:", e)

    def check_overdue_jobs(self):
        now = datetime.now()
        updated_jobs = []
        for job in self.jobs:
            overdue_start = job.get("overdue_start_date")
            if overdue_start:
                start_dt = datetime.strptime(overdue_start, "%Y-%m-%d %H:%M")
                if (now - start_dt).days >= 2:
                    continue  
            updated_jobs.append(job)
        self.jobs = updated_jobs

    def refresh_all_views(self):
        self.refresh_job_list()
        self.refresh_kontrol_tab()
        self.refresh_ic_torna_tab()
        self.refresh_ic_dik_tab()
        self.refresh_yuk_tab()
        self.refresh_mesai_tab()
        self.refresh_bitmis_isler_tab()
        self.refresh_kullanici_tab()

    def on_hover_tooltip(self, event, tree_widget, tooltip_obj):
        item = tree_widget.identify_row(event.y)
        if item:
            item_values = tree_widget.item(item, "values")
            if item_values:
                text_to_show = " | ".join(str(val) for val in item_values)
                tooltip_obj.showtip(text_to_show, event.x_root, event.y_root)
                return
        tooltip_obj.hidetip()

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        style.configure(".", font=("Segoe UI", 10, "bold"), background="#ffffff", foreground="#000000")
        style.configure("TFrame", background="#ffffff")
        
        style.configure("TLabelframe", background="#f5f5f5", foreground="#000000", font=("Segoe UI", 11, "bold"))
        style.configure("TLabelframe.Label", background="#f5f5f5", foreground="#000000", font=("Segoe UI", 11, "bold"))
        style.configure("TLabel", background="#f5f5f5", foreground="#000000", font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", fieldbackground="#ffffff", foreground="#000000", insertcolor="#000000")

        style.configure("Grey.TLabelframe", background="#f5f5f5", foreground="#000000", font=("Segoe UI", 11, "bold"))
        style.configure("Grey.TLabelframe.Label", background="#f5f5f5", foreground="#000000", font=("Segoe UI", 11, "bold"))
        style.configure("Grey.TLabel", background="#f5f5f5", foreground="#000000", font=("Segoe UI", 10, "bold"))
        style.configure("Grey.TEntry", fieldbackground="#ffffff", foreground="#000000", insertcolor="#000000")

        style.configure("TButton", font=("Segoe UI", 9, "bold"), background="#e0e0e0", foreground="#000000", padding=5)
        style.map("TButton", background=[("active", "#d0d0d0")])
        
        style.configure("Treeview", font=("Segoe UI", 9, "bold"), rowheight=34, background="#ffffff", fieldbackground="#ffffff", foreground="#000000")
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#e0e0e0", foreground="#000000")
        style.map("Treeview", background=[("selected", "#d0d0d0")], foreground=[("selected", "#000000")])

        self.top_control_frame = ttk.Frame(self.root)
        self.top_control_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 0))
        self.top_control_frame.bind("<Button-3>", self.genel_sag_tik_menu_ac)

        logo_container = ttk.Frame(self.top_control_frame)
        logo_container.pack(side=tk.LEFT, padx=5, pady=2)
        
        try:
            pil_img = Image.open("logo.png").resize((32, 32), Image.Resampling.LANCZOS)
            self.app_logo_img = ImageTk.PhotoImage(pil_img)
            lbl_logo = ttk.Label(logo_container, image=self.app_logo_img)
            lbl_logo.pack(side=tk.LEFT, padx=(0, 5))
        except Exception:
            pass

        lbl_brand = ttk.Label(logo_container, text="EAGEAN DYNAMICS", font=("Segoe UI", 11, "bold"), foreground="#2980b9")
        lbl_brand.pack(side=tk.LEFT)

        self.btn_geri_getir = ttk.Button(self.top_control_frame, text="➕ Gizlenen 'KULLANICILAR & TEZGAHLAR' Sekmesini Geri Getir", command=self.kullanici_sekmesini_goster)
        self.btn_geri_getir.pack(side=tk.LEFT, padx=15, pady=2)
        self.btn_geri_getir.pack_forget() 

        self.nav_frame = tk.Frame(self.root, bg="#e0e0e0", height=45)
        self.nav_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 0))
        
        self.tab_names = [
            (" İŞ EMRİ ", 0),
            (" PLAN KONTROLÜ ", 1),
            (" TORNA ", 2),
            (" DİK İŞLEM ", 3),
            (" MAKİNA YÜKÜ ", 4),
            (" MESAİ LİSTESİ ", 5),
            (" BİTMİŞ İŞLER ", 6),
            (" AYARLAR ", 7),
            (" KULLANICILAR & TEZGAHLAR ", 8)
        ]
        
        self.nav_buttons = []
        for idx, (t_text, t_index) in enumerate(self.tab_names):
            self.nav_frame.columnconfigure(idx, weight=1)
            btn = tk.Button(
                self.nav_frame, text=t_text, font=("Segoe UI", 10, "bold"),
                bg="#e0e0e0", fg="#000000", bd=0, relief=tk.FLAT,
                activebackground="#ffffff", activeforeground="#000000",
                command=lambda idx=t_index: self.change_custom_tab(idx)
            )
            btn.grid(row=0, column=idx, sticky="nsew", padx=1, pady=1)
            self.nav_buttons.append(btn)

        self.content_frame = ttk.Frame(self.root)
        self.content_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        self.content_frame.rowconfigure(0, weight=1)
        self.content_frame.columnconfigure(0, weight=1)

        self.tab_veri = ttk.Frame(self.content_frame)
        self.tab_kontrol = ttk.Frame(self.content_frame)
        self.tab_ic_torna = ttk.Frame(self.content_frame)
        self.tab_ic_dik = ttk.Frame(self.content_frame)
        self.tab_yuk = ttk.Frame(self.content_frame)
        self.tab_mesai = ttk.Frame(self.content_frame)
        self.tab_bitmis_isler = ttk.Frame(self.content_frame)
        self.tab_ayarlar = ttk.Frame(self.content_frame)
        self.tab_kullanicilar = ttk.Frame(self.content_frame) 

        self.all_tabs = [
            self.tab_veri, self.tab_kontrol, self.tab_ic_torna, self.tab_ic_dik,
            self.tab_yuk, self.tab_mesai, self.tab_bitmis_isler, self.tab_ayarlar, self.tab_kullanicilar
        ]

        self.context_menu_tab = tk.Menu(self.root, tearoff=0, font=("Segoe UI", 10, "bold"))
        self.context_menu_tab.add_command(label="🙈 'Kullanıcılar & Tezgahlar' Sekmesini Gizle", command=self.kullanici_sekmesini_gizle)
        self.context_menu_tab.add_command(label="➕ 'Kullanıcılar & Tezgahlar' Sekmesini Geri Getir", command=self.kullanici_sekmesini_goster)

        self.build_tab_veri()
        self.build_tab_kontrol()
        self.build_tab_ic_torna()
        self.build_tab_ic_dik()
        self.build_tab_yuk()
        self.build_tab_mesai()
        self.build_tab_bitmis_isler()
        self.build_tab_ayarlar()
        self.build_tab_kullanicilar()

        self.change_custom_tab(0)

    def change_custom_tab(self, index):
        for tab in self.all_tabs:
            tab.grid_forget()
        
        self.all_tabs[index].grid(row=0, column=0, sticky="nsew")

        for idx, btn in enumerate(self.nav_buttons):
            if idx == index:
                btn.config(bg="#ffffff", fg="#000000")
            else:
                btn.config(bg="#e0e0e0", fg="#555555")

        if index == 1: self.refresh_kontrol_tab()
        elif index == 2: self.refresh_ic_torna_tab()
        elif index == 3: self.refresh_ic_dik_tab()
        elif index == 4: self.refresh_yuk_tab()
        elif index == 5: self.refresh_mesai_tab()
        elif index == 6: self.refresh_bitmis_isler_tab()
        elif index == 8: self.refresh_kullanici_tab()

    def genel_sag_tik_menu_ac(self, event):
        self.context_menu_tab.post(event.x_root, event.y_root)

    def kullanici_sekmesini_gizle(self):
        try:
            self.nav_buttons[8].grid_remove()
            self.btn_geri_getir.pack(side=tk.LEFT, padx=5, pady=2) 
        except Exception:
            pass

    def kullanici_sekmesini_goster(self):
        try:
            self.nav_buttons[8].grid()
            self.btn_geri_getir.pack_forget() 
        except Exception:
            pass

    def build_tab_kullanicilar(self):
        self.tab_kullanicilar.columnconfigure(0, weight=1)
        self.tab_kullanicilar.columnconfigure(1, weight=1)
        self.tab_kullanicilar.rowconfigure(0, weight=1)
        self.tab_kullanicilar.rowconfigure(1, weight=1)

        f_sol_user = ttk.LabelFrame(self.tab_kullanicilar, text=" ➕ Yeni Kullanıcı Ekle ", style="Grey.TLabelframe")
        f_sol_user.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        ttk.Label(f_sol_user, text="Kullanıcı Adı:", style="Grey.TLabel").pack(anchor="w", padx=15, pady=(10, 2))
        self.ent_user_name = ttk.Entry(f_sol_user, font=("Segoe UI", 11, "bold"), style="Grey.TEntry", width=25)
        self.ent_user_name.pack(anchor="w", padx=15, pady=2)

        ttk.Label(f_sol_user, text="Şifre:", style="Grey.TLabel").pack(anchor="w", padx=15, pady=(5, 2))
        self.ent_user_pass = ttk.Entry(f_sol_user, font=("Segoe UI", 11, "bold"), style="Grey.TEntry", width=25, show="*")
        self.ent_user_pass.pack(anchor="w", padx=15, pady=2)

        ttk.Label(f_sol_user, text="Rol / Yetki:", style="Grey.TLabel").pack(anchor="w", padx=15, pady=(5, 2))
        self.cmb_user_role = ttk.Combobox(f_sol_user, values=["Operator", "Yonetici"], state="readonly", width=23, font=("Segoe UI", 11, "bold"))
        self.cmb_user_role.set("Operator")
        self.cmb_user_role.pack(anchor="w", padx=15, pady=2)

        btn_add_user = ttk.Button(f_sol_user, text="💾 Kullanıcıyı Kaydet", command=self.kullanici_ekle)
        btn_add_user.pack(anchor="w", padx=15, pady=10)

        f_sag_user = ttk.LabelFrame(self.tab_kullanicilar, text=" 👥 Kayıtlı Kullanıcılar Listesi ", style="Grey.TLabelframe")
        f_sag_user.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        f_sag_user.columnconfigure(0, weight=1)
        f_sag_user.rowconfigure(0, weight=1)

        cols_user = ("ID", "Kullanıcı Adı", "Rol")
        self.tree_users = ttk.Treeview(f_sag_user, columns=cols_user, show="headings", height=5)
        for col in cols_user:
            self.tree_users.heading(col, text=col)
            w = 60 if col == "ID" else 130
            self.tree_users.column(col, anchor="center", width=w)
        self.tree_users.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        scrollbar_user = ttk.Scrollbar(f_sag_user, orient=tk.VERTICAL, command=self.tree_users.yview)
        self.tree_users.configure(yscroll=scrollbar_user.set)
        scrollbar_user.grid(row=0, column=1, sticky="ns", pady=5)

        btn_del_user = ttk.Button(f_sag_user, text="🗑️ Seçili Kullanıcıyı Sil", command=self.kullanici_sil)
        btn_del_user.grid(row=1, column=0, columnspan=2, pady=5)

        f_sol_machine = ttk.LabelFrame(self.tab_kullanicilar, text=" ⚙️ CNC Tezgah Ekle ", style="Grey.TLabelframe")
        f_sol_machine.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        ttk.Label(f_sol_machine, text="Tezgah Adı (Örn: TORNA1):", style="Grey.TLabel").pack(anchor="w", padx=15, pady=(10, 2))
        self.ent_machine_name = ttk.Entry(f_sol_machine, font=("Segoe UI", 11, "bold"), style="Grey.TEntry", width=25)
        self.ent_machine_name.pack(anchor="w", padx=15, pady=2)

        ttk.Label(f_sol_machine, text="Tezgah Grubu / Tipi:", style="Grey.TLabel").pack(anchor="w", padx=15, pady=(5, 2))
        self.cmb_machine_type = ttk.Combobox(f_sol_machine, values=["Torna", "Dik İşlem"], state="readonly", width=23, font=("Segoe UI", 11, "bold"))
        self.cmb_machine_type.set("Torna")
        self.cmb_machine_type.pack(anchor="w", padx=15, pady=2)

        btn_add_machine = ttk.Button(f_sol_machine, text="💾 Tezgahı Kaydet ve Buluta Eşle", command=self.tezgah_ekle)
        btn_add_machine.pack(anchor="w", padx=15, pady=10)

        f_sag_machine = ttk.LabelFrame(self.tab_kullanicilar, text=" 🏭 Atölye Kayıtlı Tezgahlar Listesi ", style="Grey.TLabelframe")
        f_sag_machine.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)
        f_sag_machine.columnconfigure(0, weight=1)
        f_sag_machine.rowconfigure(0, weight=1)

        cols_machine = ("ID", "Tezgah Adı", "Bağlı Olduğu Bölüm")
        self.tree_machines = ttk.Treeview(f_sag_machine, columns=cols_machine, show="headings", height=5)
        for col in cols_machine:
            self.tree_machines.heading(col, text=col)
            w = 60 if col == "ID" else 130
            self.tree_machines.column(col, anchor="center", width=w)
        self.tree_machines.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        scrollbar_machine = ttk.Scrollbar(f_sag_machine, orient=tk.VERTICAL, command=self.tree_machines.yview)
        self.tree_machines.configure(yscroll=scrollbar_machine.set)
        scrollbar_machine.grid(row=0, column=1, sticky="ns", pady=5)

        btn_del_machine = ttk.Button(f_sag_machine, text="🗑️ Seçili Tezgahı Sil", command=self.tezgah_sil)
        btn_del_machine.grid(row=1, column=0, columnspan=2, pady=5)

    def tezgah_ekle(self):
        mname = self.ent_machine_name.get().strip().upper()
        mtype = self.cmb_machine_type.get().strip()  

        if not mname:
            messagebox.showwarning("Uyarı", "Lütfen tezgah adını doldurun (Örn: TORNA1)!")
            return

        if any(m.get("name") == mname for m in self.machines_list):
            messagebox.showwarning("Uyarı", f"'{mname}' adında bir tezgah zaten kayıtlı!")
            return

        machine_record = {
            "name": mname,
            "type": mtype,  
            "linked_section": mtype 
        }

        if supabase:
            try:
                supabase.table("tezgahlar").insert(machine_record).execute()
            except Exception as e:
                print("Supabase tezgah kayıt hatası:", e)

        new_id = len(self.machines_list) + 1
        machine_record["id"] = new_id
        self.machines_list.append(machine_record)
        
        messagebox.showinfo("Başarılı", f"'{mname}' tezgahı buluta ve sisteme kaydedildi!")
        
        self.ent_machine_name.delete(0, tk.END)
        self.cmb_machine_type.set("Torna")

        self.refresh_kullanici_tab()
        self.save_data_to_file()

    def tezgah_sil(self):
        selected = self.tree_machines.selection()
        if not selected:
            messagebox.showwarning("Uyarı", "Lütfen silmek için bir tezgah seçin!")
            return

        item_values = self.tree_machines.item(selected[0], "values")
        m_id = int(item_values[0])
        m_name = item_values[1]

        confirm = messagebox.askyesno("Silme Onayı", f"'{m_name}' tezgahını silmek istediğinize emin misiniz?")
        if confirm:
            if supabase:
                try:
                    supabase.table("tezgahlar").delete().eq("name", m_name).execute()
                except Exception as e:
                    print("Supabase tezgah silme hatası:", e)

            self.machines_list = [m for m in self.machines_list if m.get("id") != m_id and m.get("name") != m_name]
            for idx, m in enumerate(self.machines_list, 1):
                m["id"] = idx
            self.refresh_kullanici_tab()
            self.save_data_to_file()
            messagebox.showinfo("Bilgi", "Tezgah sistemden silindi.")

    def kullanici_ekle(self):
        uname = self.ent_user_name.get().strip()
        upass = self.ent_user_pass.get().strip()
        urole = self.cmb_user_role.get().strip()

        if not uname or not upass:
            messagebox.showwarning("Uyarı", "Lütfen kullanıcı adı ve şifre alanlarını doldurun!")
            return

        user_record = {
            "username": uname,
            "password": upass,
            "role": urole
        }

        if supabase:
            try:
                supabase.table("kullanıcılar").insert(user_record).execute()
            except Exception as e:
                print("Supabase kullanıcı kayıt hatası:", e)

        new_id = len(self.users_list) + 1
        user_record["id"] = new_id
        self.users_list.append(user_record)
        messagebox.showinfo("Başarılı", f"'{uname}' adlı kullanıcı buluta kaydedildi!")
        
        self.ent_user_name.delete(0, tk.END)
        self.ent_user_pass.delete(0, tk.END)
        self.cmb_user_role.set("Operator")

        self.refresh_kullanici_tab()
        self.save_data_to_file()

    def kullanici_sil(self):
        selected = self.tree_users.selection()
        if not selected:
            messagebox.showwarning("Uyarı", "Lütfen silmek için bir kullanıcı seçin!")
            return

        item_values = self.tree_users.item(selected[0], "values")
        u_id = int(item_values[0])
        u_name = item_values[1]

        confirm = messagebox.askyesno("Silme Onayı", f"'{u_name}' adlı kullanıcıyı silmek istediğinize emin misiniz?")
        if confirm:
            if supabase:
                try:
                    supabase.table("kullanıcılar").delete().eq("username", u_name).execute()
                except Exception as e:
                    print("Supabase kullanıcı silme hatası:", e)

            self.users_list = [u for u in self.users_list if u.get("id") != u_id and u.get("username") != u_name]
            self.refresh_kullanici_tab()
            self.save_data_to_file()
            messagebox.showinfo("Bilgi", "Kullanıcı sistemden silindi.")

    def refresh_kullanici_tab(self):
        if hasattr(self, "tree_users"):
            self.tree_users.delete(*self.tree_users.get_children())
            for idx, u in enumerate(self.users_list, 1):
                u["id"] = idx 
                uname_val = u.get("username", u.get("kullanıcı_adi", ""))
                urole_val = u.get("role", u.get("rol", ""))
                self.tree_users.insert("", tk.END, values=(u["id"], uname_val, urole_val))

        if hasattr(self, "tree_machines"):
            self.tree_machines.delete(*self.tree_machines.get_children())
            for idx, m in enumerate(self.machines_list, 1):
                m["id"] = idx
                m_type = m.get("type", "Torna")
                self.tree_machines.insert("", tk.END, values=(m["id"], m.get("name"), f"{m_type}"))

    def build_tab_veri(self):
        self.tab_veri.columnconfigure(0, weight=1)
        self.tab_veri.rowconfigure(1, weight=1)

        frame_form = ttk.LabelFrame(self.tab_veri, text=" İş Emri ve Malzeme Giriş Formu ", style="Grey.TLabelframe")
        frame_form.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        self.lbl_auto_fill_info = ttk.Label(frame_form, text="", font=("Segoe UI", 9, "bold italic"), foreground="#27ae60", style="Grey.TLabel")
        self.lbl_auto_fill_info.grid(row=4, column=0, columnspan=6, pady=2)

        ttk.Label(frame_form, text="İş Emri Numarası:", style="Grey.TLabel").grid(row=0, column=0, padx=8, pady=6, sticky="w")
        self.ent_isemri = ttk.Entry(frame_form, font=("Segoe UI", 11, "bold"), width=22, style="Grey.TEntry")
        self.ent_isemri.grid(row=0, column=1, padx=8, pady=6, sticky="ew")

        ttk.Label(frame_form, text="Malzeme Kodu:", style="Grey.TLabel").grid(row=0, column=2, padx=8, pady=6, sticky="w")
        self.ent_material = ttk.Entry(frame_form, font=("Segoe UI", 11, "bold"), width=22, style="Grey.TEntry")
        self.ent_material.grid(row=0, column=3, padx=8, pady=6, sticky="ew")

        ttk.Label(frame_form, text="📦 Üretilecek Adet:", style="Grey.TLabel").grid(row=0, column=4, padx=8, pady=6, sticky="w")
        self.ent_qty = ttk.Entry(frame_form, font=("Segoe UI", 11, "bold"), width=12, style="Grey.TEntry")
        self.ent_qty.grid(row=0, column=5, padx=8, pady=6, sticky="w")

        self.ent_material.bind("<FocusOut>", self.check_and_autofill_from_library)
        self.ent_material.bind("<KeyRelease>", self.check_and_autofill_from_library)

        frame_torna = ttk.LabelFrame(frame_form, text=" CNC Torna Süreleri (Dakika Cinsinden) ", style="Grey.TLabelframe")
        frame_torna.grid(row=1, column=0, columnspan=6, sticky="ew", padx=5, pady=5)

        ttk.Label(frame_torna, text="Setup (dk):", style="Grey.TLabel").grid(row=0, column=0, padx=6, pady=5)
        self.ent_t_setup = ttk.Entry(frame_torna, font=("Segoe UI", 11, "bold"), width=8, style="Grey.TEntry")
        self.ent_t_setup.grid(row=0, column=1, padx=6, pady=5)

        ttk.Label(frame_torna, text="Op1 (dk):", style="Grey.TLabel").grid(row=0, column=2, padx=6, pady=5)
        self.ent_t_op1 = ttk.Entry(frame_torna, font=("Segoe UI", 11, "bold"), width=8, style="Grey.TEntry")
        self.ent_t_op1.grid(row=0, column=3, padx=6, pady=5)

        ttk.Label(frame_torna, text="Op2 (dk):", style="Grey.TLabel").grid(row=0, column=4, padx=6, pady=5)
        self.ent_t_op2 = ttk.Entry(frame_torna, font=("Segoe UI", 11, "bold"), width=8, style="Grey.TEntry")
        self.ent_t_op2.grid(row=0, column=5, padx=6, pady=5)

        ttk.Label(frame_torna, text="Op3 (dk):", style="Grey.TLabel").grid(row=0, column=6, padx=6, pady=5)
        self.ent_t_op3 = ttk.Entry(frame_torna, font=("Segoe UI", 11, "bold"), width=8, style="Grey.TEntry")
        self.ent_t_op3.grid(row=0, column=7, padx=6, pady=5)

        frame_dik = ttk.LabelFrame(frame_form, text=" CNC Dik İşlem Süreleri (Dakika Cinsinden) ", style="Grey.TLabelframe")
        frame_dik.grid(row=2, column=0, columnspan=6, sticky="ew", padx=5, pady=5)

        ttk.Label(frame_dik, text="Setup (dk):", style="Grey.TLabel").grid(row=0, column=0, padx=6, pady=5)
        self.ent_d_setup = ttk.Entry(frame_dik, font=("Segoe UI", 11, "bold"), width=8, style="Grey.TEntry")
        self.ent_d_setup.grid(row=0, column=1, padx=6, pady=5)

        ttk.Label(frame_dik, text="Op1 (dk):", style="Grey.TLabel").grid(row=0, column=2, padx=6, pady=5)
        self.ent_d_op1 = ttk.Entry(frame_dik, font=("Segoe UI", 11, "bold"), width=8, style="Grey.TEntry")
        self.ent_d_op1.grid(row=0, column=3, padx=6, pady=5)

        ttk.Label(frame_dik, text="Op2 (dk):", style="Grey.TLabel").grid(row=0, column=4, padx=6, pady=5)
        self.ent_d_op2 = ttk.Entry(frame_dik, font=("Segoe UI", 11, "bold"), width=8, style="Grey.TEntry")
        self.ent_d_op2.grid(row=0, column=5, padx=6, pady=5)

        ttk.Label(frame_dik, text="Op3 (dk):", style="Grey.TLabel").grid(row=0, column=6, padx=6, pady=5)
        self.ent_d_op3 = ttk.Entry(frame_dik, font=("Segoe UI", 11, "bold"), width=8, style="Grey.TEntry")
        self.ent_d_op3.grid(row=0, column=7, padx=6, pady=5)

        self.entry_order = [
            self.ent_isemri, self.ent_material, self.ent_qty,
            self.ent_t_setup, self.ent_t_op1, self.ent_t_op2, self.ent_t_op3,
            self.ent_d_setup, self.ent_d_op1, self.ent_d_op2, self.ent_d_op3
        ]

        for idx, entry in enumerate(self.entry_order):
            if idx < len(self.entry_order) - 1:
                next_entry = self.entry_order[idx + 1]
                entry.bind("<Return>", lambda event, nxt=next_entry: nxt.focus())
            else:
                entry.bind("<Return>", lambda event: self.save_or_update_job())

        self.btn_add = ttk.Button(frame_form, text="➕ İş Emrini Listeye Kaydet ve Buluta Gönder", command=self.save_or_update_job)
        self.btn_add.grid(row=3, column=0, columnspan=6, pady=10)

        frame_list = ttk.LabelFrame(self.tab_veri, text=" Aktif İş Emirleri Listesi ", style="Grey.TLabelframe")
        frame_list.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        frame_list.columnconfigure(0, weight=1)
        frame_list.rowconfigure(0, weight=1)

        cols = ("İş Emri No", "Malzeme Kodu", "Adet", "Torna Setup (dk)", "Torna Op Top. (dk)", "Dik Setup (dk)", "Dik Op Top. (dk)", "Top. Saat")
        self.tree_jobs = ttk.Treeview(frame_list, columns=cols, show="headings")
        for col in cols:
            self.tree_jobs.heading(col, text=col)
            width = 150
            self.tree_jobs.column(col, anchor="center", width=width)
        
        self.tree_jobs.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(frame_list, orient=tk.VERTICAL, command=self.tree_jobs.yview)
        self.tree_jobs.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="✏️ Düzenle", command=self.edit_selected_job)
        self.context_menu.add_command(label="🗑️ Sil", command=self.delete_selected_job)

        self.tree_jobs.bind("<Button-3>", self.show_context_menu)

        self.tooltip_veri = ToolTip(self.tree_jobs)
        self.tree_jobs.bind("<Motion>", lambda e: self.on_hover_tooltip(e, self.tree_jobs, self.tooltip_veri))
        self.tree_jobs.bind("<Leave>", lambda e: self.tooltip_veri.hidetip())

    def check_and_autofill_from_library(self, event=None):
        if self.editing_job_id is not None:
            return

        material = self.ent_material.get().strip().upper()
        if not material:
            self.lbl_auto_fill_info.config(text="")
            return

        if material in self.part_library:
            times = self.part_library[material]
            
            self.ent_t_setup.delete(0, tk.END); self.ent_t_setup.insert(0, self.fmt_num(times["t_setup"]))
            self.ent_t_op1.delete(0, tk.END); self.ent_t_op1.insert(0, self.fmt_num(times["t_op1"]))
            self.ent_t_op2.delete(0, tk.END); self.ent_t_op2.insert(0, self.fmt_num(times["t_op2"]))
            self.ent_t_op3.delete(0, tk.END); self.ent_t_op3.insert(0, self.fmt_num(times.get("t_op3", 0)))

            self.ent_d_setup.delete(0, tk.END); self.ent_d_setup.insert(0, self.fmt_num(times["d_setup"]))
            self.ent_d_op1.delete(0, tk.END); self.ent_d_op1.insert(0, self.fmt_num(times["d_op1"]))
            self.ent_d_op2.delete(0, tk.END); self.ent_d_op2.insert(0, self.fmt_num(times["d_op2"]))
            self.ent_d_op3.delete(0, tk.END); self.ent_d_op3.insert(0, self.fmt_num(times["d_op3"]))

            self.lbl_auto_fill_info.config(text="ℹ️ Geçmiş malzeme hafızasından dakika süreleri otomatik dolduruldu.")
        else:
            self.lbl_auto_fill_info.config(text="")

    def show_context_menu(self, event):
        item = self.tree_jobs.identify_row(event.y)
        if item:
            self.tree_jobs.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def get_float_entry(self, entry_widget):
        val_str = entry_widget.get().strip()
        if not val_str:
            return 0.0
        return float(val_str)

    def get_int_entry(self, entry_widget):
        val_str = entry_widget.get().strip()
        if not val_str:
            return 0
        return int(val_str)

    def save_or_update_job(self):
        try:
            qty = self.get_int_entry(self.ent_qty)
            isemri = self.ent_isemri.get().strip()
            mat = self.ent_material.get().strip()

            t_setup = self.get_float_entry(self.ent_t_setup)
            t_op1 = self.get_float_entry(self.ent_t_op1)
            t_op2 = self.get_float_entry(self.ent_t_op2)
            t_op3 = self.get_float_entry(self.ent_t_op3)

            d_setup = self.get_float_entry(self.ent_d_setup)
            d_op1 = self.get_float_entry(self.ent_d_op1)
            d_op2 = self.get_float_entry(self.ent_d_op2)
            d_op3 = self.get_float_entry(self.ent_d_op3)

            torna_op_sum = t_op1 + t_op2 + t_op3
            dik_op_sum = d_op1 + d_op2 + d_op3

            torna_total_hours = round((t_setup + (torna_op_sum * qty)) / 60.0, 2)
            dik_total_hours = round((d_setup + (dik_op_sum * qty)) / 60.0, 2)
            total_hours = round(torna_total_hours + dik_total_hours, 2)

            torna_op_count = 0
            if t_op1 > 0: torna_op_count = 1
            if t_op2 > 0: torna_op_count = 2
            if t_op3 > 0: torna_op_count = 3

            lib_key = mat.upper()
            self.part_library[lib_key] = {
                "t_setup": t_setup, "t_op1": t_op1, "t_op2": t_op2, "t_op3": t_op3,
                "d_setup": d_setup, "d_op1": d_op1, "d_op2": d_op2, "d_op3": d_op3
            }

            added_or_edited_id = None
            assigned_uid = str(uuid.uuid4())

            if self.editing_job_id is None:
                job_id = len(self.jobs) + 1
                
                for j in self.jobs:
                    j["torna_rank"] = j.get("torna_rank", 0) + 1
                    j["dik_rank"] = j.get("dik_rank", 0) + 1

                job_data = {
                    "id": job_id,
                    "unique_id": assigned_uid,
                    "qty": qty, "isemri": isemri, "material": mat,
                    "t_setup": t_setup, "t_op1": t_op1, "t_op2": t_op2, "t_op3": t_op3,
                    "d_setup": d_setup, "d_op1": d_op1, "d_op2": d_op2, "d_op3": d_op3,
                    "torna_op_sum": torna_op_sum, "dik_op_sum": dik_op_sum,
                    "torna_total_hours": torna_total_hours, "dik_total_hours": dik_total_hours,
                    "total_hours": total_hours,
                    "note": "Açıklama girilmedi...",
                    "torna_rank": 1,
                    "dik_rank": 1,
                    "torna_op_count": max(1, torna_op_count),
                    "dik_finished": False if dik_total_hours > 0 else True,
                    "torna_finished": False if torna_total_hours > 0 else True
                }
                self.jobs.insert(0, job_data)
                added_or_edited_id = job_id

                if supabase:
                    try:
                        supabase.table("cnc_is_emirleri").insert({
                            "unique_id": assigned_uid,
                            "malzeme_kodu": isemri,
                            "hedef_adet": qty,
                            "durum": json.dumps({
                                "isStarted": False,
                                "isCompleted": False,
                                "isPaused": False,
                                "tezgah": "",
                                "operasyonlar": [],
                                "durusSebebi": ""
                            })
                        }).execute()
                    except Exception as e:
                        print("Supabase iş kayıt hatası:", e)
            else:
                for job in self.jobs:
                    if job["id"] == self.editing_job_id:
                        job.update({
                            "qty": qty, "isemri": isemri, "material": mat,
                            "t_setup": t_setup, "t_op1": t_op1, "t_op2": t_op2, "t_op3": t_op3,
                            "d_setup": d_setup, "d_op1": d_op1, "d_op2": d_op2, "d_op3": d_op3,
                            "torna_op_sum": torna_op_sum, "dik_op_sum": dik_op_sum,
                            "torna_total_hours": torna_total_hours, "dik_total_hours": dik_total_hours,
                            "total_hours": total_hours
                        })
                        added_or_edited_id = job["id"]
                        break
                self.editing_job_id = None
                self.btn_add.config(text="➕ İş Emrini Listeye Kaydet ve Buluta Gönder")

            self.refresh_job_list(highlight_id=added_or_edited_id)
            self.clear_form()
            self.ent_isemri.focus()
            self.save_data_to_file()

        except ValueError:
            messagebox.showerror("Hata", "Lütfen adet ve süre alanlarına geçerli sayısal değerler girin!")

    def edit_selected_job(self):
        selected_item = self.tree_jobs.selection()
        if not selected_item: return
        
        item_values = self.tree_jobs.item(selected_item[0], "values")
        isemri_val = item_values[0]
        material_val = item_values[1]

        target_job = None
        for job in self.jobs:
            if str(job.get("isemri", "")) == str(isemri_val) and str(job.get("material", "")) == str(material_val):
                target_job = job
                break

        if target_job:
            self.editing_job_id = target_job["id"]
            
            self.ent_qty.delete(0, tk.END); self.ent_qty.insert(0, str(target_job["qty"]))
            self.ent_isemri.delete(0, tk.END); self.ent_isemri.insert(0, target_job.get("isemri", ""))
            self.ent_material.delete(0, tk.END); self.ent_material.insert(0, target_job["material"])

            self.ent_t_setup.delete(0, tk.END); self.ent_t_setup.insert(0, self.fmt_num(target_job["t_setup"]))
            self.ent_t_op1.delete(0, tk.END); self.ent_t_op1.insert(0, self.fmt_num(target_job.get("t_op1", 0)))
            self.ent_t_op2.delete(0, tk.END); self.ent_t_op2.insert(0, self.fmt_num(target_job.get("t_op2", 0)))
            self.ent_t_op3.delete(0, tk.END); self.ent_t_op3.insert(0, self.fmt_num(target_job.get("t_op3", 0)))

            self.ent_d_setup.delete(0, tk.END); self.ent_d_setup.insert(0, self.fmt_num(target_job["d_setup"]))
            self.ent_d_op1.delete(0, tk.END); self.ent_d_op1.insert(0, self.fmt_num(target_job.get("d_op1", 0)))
            self.ent_d_op2.delete(0, tk.END); self.ent_d_op2.insert(0, self.fmt_num(target_job.get("d_op2", 0)))
            self.ent_d_op3.delete(0, tk.END); self.ent_d_op3.insert(0, self.fmt_num(target_job.get("d_op3", 0)))

            self.btn_add.config(text="🔄 İş Emrini Güncelle")
            self.ent_isemri.focus()

    def delete_selected_job(self):
        selected_item = self.tree_jobs.selection()
        if not selected_item: return
        
        item_values = self.tree_jobs.item(selected_item[0], "values")
        isemri_val = item_values[0]
        material_code = item_values[1]

        confirm = messagebox.askyesno("Silme Onayı", f"'{isemri_val}' numaralı iş emrini silmek istediğinize emin misiniz?")
        if confirm:
            target_uid = None
            for j in self.jobs:
                if str(j.get("isemri")) == str(isemri_val) and str(j.get("material")) == str(material_code):
                    target_uid = j.get("unique_id")
                    break

            if supabase and target_uid:
                try:
                    supabase.table("cnc_is_emirleri").delete().eq("unique_id", target_uid).execute()
                except Exception as e:
                    print("Supabase silme hatası:", e)

            self.jobs = [j for j in self.jobs if not (str(j.get("isemri")) == str(isemri_val) and str(j.get("material")) == str(material_code))]
            
            self.refresh_all_views()
            self.save_data_to_file()

    def refresh_job_list(self, highlight_id=None):
        self.tree_jobs.delete(*self.tree_jobs.get_children())
        target_item = None
        for job in self.jobs:
            torna_bitti = (job.get("torna_total_hours", 0) == 0) or job.get("torna_finished", False)
            dik_bitti = (job.get("dik_total_hours", 0) == 0) or job.get("dik_finished", False)
            
            if torna_bitti and dik_bitti:
                continue

            item = self.tree_jobs.insert("", tk.END, values=(
                job.get("isemri", ""), job["material"], job["qty"],
                self.fmt_num(job["t_setup"]), self.fmt_num(job.get("torna_op_sum", 0)),
                self.fmt_num(job["d_setup"]), self.fmt_num(job.get("dik_op_sum", 0)),
                self.fmt_num(job["total_hours"])
            ))
            if highlight_id and job["id"] == highlight_id:
                target_item = item

        if target_item:
            self.tree_jobs.selection_set(target_item)
            self.tree_jobs.see(target_item)

    def clear_form(self):
        self.lbl_auto_fill_info.config(text="")
        self.ent_qty.delete(0, tk.END)
        self.ent_isemri.delete(0, tk.END)
        self.ent_material.delete(0, tk.END)

        self.ent_t_setup.delete(0, tk.END)
        self.ent_t_op1.delete(0, tk.END)
        self.ent_t_op2.delete(0, tk.END)
        self.ent_t_op3.delete(0, tk.END)

        self.ent_d_setup.delete(0, tk.END)
        self.ent_d_op1.delete(0, tk.END)
        self.ent_d_op2.delete(0, tk.END)
        self.ent_d_op3.delete(0, tk.END)

    def build_tab_kontrol(self):
        self.tab_kontrol.columnconfigure(0, weight=1)
        self.tab_kontrol.rowconfigure(1, weight=1)

        top_bar = ttk.Frame(self.tab_kontrol, style="Grey.TLabelframe")
        top_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        lbl = ttk.Label(top_bar, text="📊 Kayıtlı İş Emirleri Listesi", font=("Segoe UI", 12, "bold"), style="Grey.TLabel")
        lbl.pack(side=tk.LEFT, padx=10, pady=10)

        frame_list = ttk.LabelFrame(self.tab_kontrol, text=" İş Emirleri Durum Tablosu ", style="Grey.TLabelframe")
        frame_list.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        frame_list.columnconfigure(0, weight=1)
        frame_list.rowconfigure(0, weight=1)

        self.cols_kontrol = ("İş Emri No", "Malzeme Kodu", "Adet", "Top. Süre (Saat)")
        self.tree_kontrol = ttk.Treeview(frame_list, columns=self.cols_kontrol, show="headings")
        
        for col in self.cols_kontrol:
            self.tree_kontrol.heading(col, text=col)
            width = 220
            self.tree_kontrol.column(col, anchor="center", width=width)

        self.tree_kontrol.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(frame_list, orient=tk.VERTICAL, command=self.tree_kontrol.yview)
        self.tree_kontrol.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

    def refresh_kontrol_tab(self):
        self.tree_kontrol.delete(*self.tree_kontrol.get_children())
        for job in self.jobs:
            torna_bitti = (job.get("torna_total_hours", 0) == 0) or job.get("torna_finished", False)
            dik_bitti = (job.get("dik_total_hours", 0) == 0) or job.get("dik_finished", False)
            if torna_bitti and dik_bitti:
                continue

            self.tree_kontrol.insert("", tk.END, values=(
                job.get('isemri', ''), job['material'],
                job['qty'], self.fmt_num(job['total_hours'])
            ))

    def build_tab_ic_torna(self):
        self.tab_ic_torna.columnconfigure(0, weight=1)
        self.tab_ic_torna.rowconfigure(0, weight=1)

        frame_list = ttk.LabelFrame(self.tab_ic_torna, text=" 🌀 TORNA (Çift Tıkla Sıra Değiştir) ", style="Grey.TLabelframe")
        frame_list.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        frame_list.columnconfigure(0, weight=1)
        frame_list.rowconfigure(0, weight=1)

        cols_ic = ("Torna Sıra No", "İş Emri No", "Malzeme Kodu", "Adet", "Torna Setup (dk)", "Torna Op Top. (dk)", "Torna Top. Saat")
        self.tree_ic_torna = ttk.Treeview(frame_list, columns=cols_ic, show="headings")
        
        for col in cols_ic:
            self.tree_ic_torna.heading(col, text=col)
            width = 150 if col == "Torna Sıra No" else 140
            self.tree_ic_torna.column(col, anchor="center", width=width)

        self.tree_ic_torna.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(frame_list, orient=tk.VERTICAL, command=self.tree_ic_torna.yview)
        self.tree_ic_torna.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.tree_ic_torna.bind("<Double-1>", self.change_torna_order)

    def change_torna_order(self, event):
        selected_item = self.tree_ic_torna.selection()
        if not selected_item: return

        item_values = self.tree_ic_torna.item(selected_item[0], "values")
        current_rank = int(item_values[0])
        isemri_val = item_values[1]

        torna_jobs = [j for j in self.jobs if (j["torna_total_hours"] > 0) and not j.get("torna_finished", False)]
        torna_jobs.sort(key=lambda x: x.get("torna_rank", 0))
        max_rank = len(torna_jobs)

        new_rank = simpledialog.askinteger(
            "Torna Sıralaması Değiştir", 
            f"'{isemri_val}' iş emrini Torna hat üzerinde kaçıncı sıraya almak istiyorsunuz? (1 - {max_rank}):",
            initialvalue=current_rank, minvalue=1, maxvalue=max_rank
        )

        if new_rank is not None and new_rank != current_rank:
            target_job = torna_jobs[current_rank - 1]
            torna_jobs.remove(target_job)
            torna_jobs.insert(new_rank - 1, target_job)

            for idx, job in enumerate(torna_jobs):
                job["torna_rank"] = idx + 1

            self.refresh_all_views()
            self.save_data_to_file()

    def refresh_ic_torna_tab(self):
        self.tree_ic_torna.delete(*self.tree_ic_torna.get_children())
        torna_jobs = [j for j in self.jobs if (j["torna_total_hours"] > 0) and not j.get("torna_finished", False)]
        
        torna_jobs.sort(key=lambda x: x.get("torna_rank", 0))

        for idx, job in enumerate(torna_jobs, 1):
            job["torna_rank"] = idx
            
            self.tree_ic_torna.insert("", tk.END, values=(
                idx, job.get("isemri", ""), job["material"], job["qty"],
                self.fmt_num(job["t_setup"]), self.fmt_num(job.get("torna_op_sum", 0)),
                self.fmt_num(job["torna_total_hours"])
            ))

    def build_tab_ic_dik(self):
        self.tab_ic_dik.columnconfigure(0, weight=1)
        self.tab_ic_dik.rowconfigure(0, weight=1)

        frame_list = ttk.LabelFrame(self.tab_ic_dik, text=" 📐 DİK İŞLEM (Çift Tıkla Sıra Değiştir) ", style="Grey.TLabelframe")
        frame_list.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        frame_list.columnconfigure(0, weight=1)
        frame_list.rowconfigure(0, weight=1)

        cols_ic = ("Dik İşlem Sıra No", "İş Emri No", "Malzeme Kodu", "Adet", "Dik Setup (dk)", "Dik Op Top. (dk)", "Dik Top. Saat")
        self.tree_ic_dik = ttk.Treeview(frame_list, columns=cols_ic, show="headings")
        
        for col in cols_ic:
            self.tree_ic_dik.heading(col, text=col)
            width = 150 if col == "Dik İşlem Sıra No" else 140
            self.tree_ic_dik.column(col, anchor="center", width=width)

        self.tree_ic_dik.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(frame_list, orient=tk.VERTICAL, command=self.tree_ic_dik.yview)
        self.tree_ic_dik.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.tree_ic_dik.bind("<Double-1>", self.change_dik_order)

    def change_dik_order(self, event):
        selected_item = self.tree_ic_dik.selection()
        if not selected_item: return

        item_values = self.tree_ic_dik.item(selected_item[0], "values")
        current_rank = int(item_values[0])
        isemri_val = item_values[1]

        dik_jobs = [j for j in self.jobs if (j["dik_total_hours"] > 0) and not j.get("dik_finished", False)]
        dik_jobs.sort(key=lambda x: x.get("dik_rank", 0))
        max_rank = len(dik_jobs)

        new_rank = simpledialog.askinteger(
            "Dik İşlem Sıralaması Değiştir", 
            f"'{isemri_val}' iş emrini Dik İşlem hat üzerinde kaçıncı sıraya almak istiyorsunuz? (1 - {max_rank}):",
            initialvalue=current_rank, minvalue=1, maxvalue=max_rank
        )

        if new_rank is not None and new_rank != current_rank:
            target_job = dik_jobs[current_rank - 1]
            dik_jobs.remove(target_job)
            dik_jobs.insert(new_rank - 1, target_job)

            for idx, job in enumerate(dik_jobs):
                job["dik_rank"] = idx + 1

            self.refresh_all_views()
            self.save_data_to_file()

    def refresh_ic_dik_tab(self):
        self.tree_ic_dik.delete(*self.tree_ic_dik.get_children())
        dik_jobs = [j for j in self.jobs if (j["dik_total_hours"] > 0) and not j.get("dik_finished", False)]

        dik_jobs.sort(key=lambda x: x.get("dik_rank", 0))

        for idx, job in enumerate(dik_jobs, 1):
            job["dik_rank"] = idx
            
            self.tree_ic_dik.insert("", tk.END, values=(
                idx, job.get("isemri", ""), job["material"], job["qty"],
                self.fmt_num(job["d_setup"]), self.fmt_num(job.get("dik_op_sum", 0)),
                self.fmt_num(job["dik_total_hours"])
            ))

    def build_tab_yuk(self):
        self.tab_yuk.columnconfigure(0, weight=1)
        self.tab_yuk.rowconfigure(1, weight=1)

        top_bar = ttk.Frame(self.tab_yuk, style="Grey.TLabelframe")
        top_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=5)

        ttk.Label(top_bar, text="🗓️ Çizelge Görünüm Aralığı:", style="Grey.TLabel").pack(side=tk.LEFT, padx=10, pady=8)
        self.cmb_period = ttk.Combobox(top_bar, values=["1 Ay (30 Gün)", "3 Ay (90 Gün)", "1 Yıl (365 Gün)"], state="readonly", width=15)
        self.cmb_period.set("3 Ay (90 Gün)")
        self.cmb_period.pack(side=tk.LEFT, padx=5, pady=8)
        self.cmb_period.bind("<<ComboboxSelected>>", self.on_period_change)

        frame_main = ttk.LabelFrame(self.tab_yuk, text=" ⚙️ MAKİNA KAPASİTE YÜKÜ (YEŞİL: DOLU - KREM: CUMARTESİ - LİLA: PAZAR - PEMBE: RESMİ TATİL) ", style="Grey.TLabelframe")
        frame_main.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        frame_main.columnconfigure(0, weight=1)
        frame_main.rowconfigure(0, weight=1)

        self.canvas_yuk = tk.Canvas(frame_main, bg="#ffffff", highlightthickness=0)
        self.canvas_yuk.grid(row=0, column=0, sticky="nsew")

        scrollbar_x = ttk.Scrollbar(frame_main, orient=tk.HORIZONTAL, command=self.canvas_yuk.xview)
        scrollbar_x.grid(row=1, column=0, sticky="ew")

        scrollbar_y = ttk.Scrollbar(frame_main, orient=tk.VERTICAL, command=self.canvas_yuk.yview)
        scrollbar_y.grid(row=0, column=1, sticky="ns")

        self.canvas_yuk.configure(xscrollcommand=scrollbar_x.set, yscrollcommand=scrollbar_y.set)

    def on_period_change(self, event):
        val = self.cmb_period.get()
        if "1 Ay" in val:
            self.days_count = 30
        elif "3 Ay" in val:
            self.days_count = 90
        elif "1 Yıl" in val:
            self.days_count = 365
        
        self.refresh_mesai_tab()
        self.refresh_yuk_tab()

    def get_day_capacity_hours(self, date_str, group_type="torna"):
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        ov_data = self.overtime_schedule.get(date_str, {"torna": False, "dik": False})
        is_overtime_selected = ov_data.get(group_type, False)
        
        is_weekend = date_obj.weekday() >= 5
        is_holiday = self.is_public_holiday(date_obj)

        if is_holiday:
            if is_overtime_selected:
                return (self.overtime_min_weekend / 60.0) if is_weekend else (self.overtime_min_weekday / 60.0)
            else:
                return 0.0
        elif is_weekend:
            return (self.overtime_min_weekend / 60.0) if is_overtime_selected else 0.0
        else:
            return ((self.work_min_weekday + self.overtime_min_weekday) / 60.0) if is_overtime_selected else (self.work_min_weekday / 60.0)

    def refresh_yuk_tab(self):
        self.canvas_yuk.delete("all")
        
        torna_jobs = [j for j in self.jobs if (j.get("torna_total_hours", 0) > 0 or j.get("material") == "PLANSIZ-SAHA") and not j.get("torna_finished", False)]
        torna_jobs.sort(key=lambda x: x.get("torna_rank", 0))

        dik_jobs = [j for j in self.jobs if (j.get("dik_total_hours", 0) > 0 or j.get("material") == "PLANSIZ-SAHA") and not j.get("dik_finished", False)]
        dik_jobs.sort(key=lambda x: x.get("dik_rank", 0))

        today = datetime.now()
        date_objs = [today + timedelta(days=i) for i in range(self.days_count)]
        date_keys = [d.strftime("%Y-%m-%d") for d in date_objs]
        date_labels = [d.strftime("%d.%m.%Y (%a)") for d in date_objs]

        torna_schedule = [[] for _ in range(self.days_count)]
        dik_schedule = [[] for _ in range(self.days_count)]

        torna_timeline_hour = 0.0
        job_torna_end_times = {}

        for job in torna_jobs:
            qty = job.get('qty', 1)
            t_setup = job.get("t_setup", 0.0)
            t_op1 = job.get("t_op1", 0.0)
            t_op2 = job.get("t_op2", 0.0)
            t_op3 = job.get("t_op3", 0.0)

            cloud_d = job.get("cloud_durum", {})
            torna_ops = cloud_d.get("torna_operasyonlar", [])
            
            op1_done = any(op.get("opNo") == 1 and op.get("durum") == "Bitti" for op in torna_ops)
            op2_done = any(op.get("opNo") == 2 and op.get("durum") == "Bitti" for op in torna_ops)
            op3_done = any(op.get("opNo") == 3 and op.get("durum") == "Bitti" for op in torna_ops)

            eff_t_setup = 0.0 if op1_done else t_setup
            eff_t_op1 = 0.0 if op1_done else t_op1
            eff_t_op2 = 0.0 if op2_done else t_op2
            eff_t_op3 = 0.0 if op3_done else t_op3

            if job.get("material") == "PLANSIZ-SAHA":
                t_op_total_hours = job.get("torna_total_hours", 4.0)
            else:
                t_op_total_hours = (eff_t_setup + (qty * (eff_t_op1 + eff_t_op2 + eff_t_op3))) / 60.0

            torna_tezgah_adi = cloud_d.get("torna_tezgah", "")
            if job.get("material") == "PLANSIZ-SAHA" and not torna_tezgah_adi:
                t_op_total_hours = 0.0

            t_start = torna_timeline_hour
            t_end = t_start + t_op_total_hours
            torna_timeline_hour = t_end

            job_torna_end_times[job["id"]] = t_end

            if t_op_total_hours > 0:
                accum_hours = 0.0
                for d, d_key in enumerate(date_keys):
                    cap = self.get_day_capacity_hours(d_key, "torna")
                    if cap == 0: continue
                    
                    day_start = accum_hours
                    day_end = accum_hours + cap
                    accum_hours = day_end

                    if max(t_start, day_start) < min(t_end, day_end):
                        torna_schedule[d].append(job.get('isemri', ''))

        dik_timeline_hour = 0.0
        for job in dik_jobs:
            qty = job.get('qty', 1)
            d_setup = job.get("d_setup", 0.0)
            d_op1 = job.get("d_op1", 0.0)
            d_op2 = job.get("d_op2", 0.0)
            d_op3 = job.get("d_op3", 0.0)

            cloud_d = job.get("cloud_durum", {})
            dik_ops = cloud_d.get("dik_operasyonlar", [])
            
            d_op1_done = any(op.get("opNo") == 1 and op.get("durum") == "Bitti" for op in dik_ops)
            d_op2_done = any(op.get("opNo") == 2 and op.get("durum") == "Bitti" for op in dik_ops)
            d_op3_done = any(op.get("opNo") == 3 and op.get("durum") == "Bitti" for op in dik_ops)

            eff_d_setup = 0.0 if d_op1_done else d_setup
            eff_d_op1 = 0.0 if d_op1_done else d_op1
            eff_d_op2 = 0.0 if d_op2_done else d_op2
            eff_d_op3 = 0.0 if d_op3_done else d_op3

            if job.get("material") == "PLANSIZ-SAHA":
                d_hours = job.get("dik_total_hours", 4.0)
            else:
                d_hours = (eff_d_setup + (qty * (eff_d_op1 + eff_d_op2 + eff_d_op3))) / 60.0

            dik_tezgah_adi = cloud_d.get("dik_tezgah", "")
            if job.get("material") == "PLANSIZ-SAHA" and not dik_tezgah_adi:
                d_hours = 0.0

            part_ready_hour = job_torna_end_times.get(job["id"], 0.0)

            d_start = max(dik_timeline_hour, part_ready_hour)
            d_end = d_start + d_hours
            dik_timeline_hour = d_end

            if d_hours > 0:
                accum_hours = 0.0
                for d, d_key in enumerate(date_keys):
                    cap = self.get_day_capacity_hours(d_key, "dik")
                    if cap == 0: continue

                    day_start = accum_hours
                    day_end = accum_hours + cap
                    accum_hours = day_end

                    if max(d_start, day_start) < min(d_end, day_end):
                        dik_schedule[d].append(job.get('isemri', ''))

        col_w = 120
        row_h = 45
        header_h = 40
        left_w = 230

        self.canvas_yuk.create_rectangle(0, 0, left_w, header_h, fill="#e0e0e0", outline="#cccccc")
        self.canvas_yuk.create_text(left_w/2, header_h/2, text="Tezgah Grubu", font=("Segoe UI", 11, "bold"), fill="#000000")

        for idx, (d_str, d_obj) in enumerate(zip(date_labels, date_objs)):
            x1 = left_w + (idx * col_w)
            x2 = x1 + col_w
            
            header_bg = "#e0e0e0"
            if self.is_public_holiday(d_obj):
                header_bg = "#ffb8b8"  
            elif d_obj.weekday() == 5:
                header_bg = "#ffeaa7"  
            elif d_obj.weekday() == 6:
                header_bg = "#fab1a0"  

            self.canvas_yuk.create_rectangle(x1, 0, x2, header_h, fill=header_bg, outline="#cccccc")
            self.canvas_yuk.create_text((x1 + x2)/2, header_h/2, text=d_str, font=("Segoe UI", 9, "bold"), fill="#000000")

        y1_t = header_h
        y2_t = y1_t + row_h
        self.canvas_yuk.create_rectangle(0, y1_t, left_w, y2_t, fill="#e0e0e0", outline="#cccccc")
        self.canvas_yuk.create_text(left_w/2, (y1_t + y2_t)/2, text="TORNA GRUBU", font=("Segoe UI", 11, "bold"), fill="#000000")

        for idx, (isemri_list, d_obj) in enumerate(zip(torna_schedule, date_objs)):
            x1 = left_w + (idx * col_w)
            x2 = x1 + col_w
            
            isemri_name = " / ".join(isemri_list) if isemri_list else ""

            if isemri_name:
                fill_color = "#2ecc71"
                text_color = "#ffffff"
            else:
                if self.is_public_holiday(d_obj):
                    fill_color = "#ffebeb"
                elif d_obj.weekday() == 5:
                    fill_color = "#fff5d7"
                elif d_obj.weekday() == 6:
                    fill_color = "#ffe3de"
                else:
                    fill_color = "#ffffff"
                text_color = "#000000"

            self.canvas_yuk.create_rectangle(x1, y1_t, x2, y2_t, fill=fill_color, outline="#cccccc", width=1)
            if isemri_name:
                self.canvas_yuk.create_text((x1 + x2)/2, (y1_t + y2_t)/2, text=isemri_name, font=("Segoe UI", 9, "bold"), fill=text_color)

        y1_d = y2_t
        y2_d = y1_d + row_h
        self.canvas_yuk.create_rectangle(0, y1_d, left_w, y2_d, fill="#e0e0e0", outline="#cccccc")
        self.canvas_yuk.create_text(left_w/2, (y1_d + y2_d)/2, text="DİK İŞLEM GRUBU", font=("Segoe UI", 11, "bold"), fill="#000000")

        for idx, (isemri_list, d_obj) in enumerate(zip(dik_schedule, date_objs)):
            x1 = left_w + (idx * col_w)
            x2 = x1 + col_w
            
            isemri_name = " / ".join(isemri_list) if isemri_list else ""

            if isemri_name:
                fill_color = "#2ecc71"
                text_color = "#ffffff"
            else:
                if self.is_public_holiday(d_obj):
                    fill_color = "#ffebeb"
                elif d_obj.weekday() == 5:
                    fill_color = "#fff5d7"
                elif d_obj.weekday() == 6:
                    fill_color = "#ffe3de"
                else:
                    fill_color = "#ffffff"
                text_color = "#000000"

            self.canvas_yuk.create_rectangle(x1, y1_d, x2, y2_d, fill=fill_color, outline="#cccccc", width=1)
            if isemri_name:
                self.canvas_yuk.create_text((x1 + x2)/2, (y1_d + y2_d)/2, text=isemri_name, font=("Segoe UI", 9, "bold"), fill=text_color)

        total_width = left_w + (self.days_count * col_w)
        self.canvas_yuk.config(scrollregion=(0, 0, total_width, y2_d + 20))

    def build_tab_mesai(self):
        self.tab_mesai.columnconfigure(0, weight=1)
        self.tab_mesai.rowconfigure(1, weight=1)

        frame_top = ttk.Frame(self.tab_mesai, style="Grey.TLabelframe")
        frame_top.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        lbl = ttk.Label(frame_top, text="📅 Torna ve Dik İşlem Ayrı Günlük Mesai ve Tatil Yönetimi", font=("Segoe UI", 12, "bold"), style="Grey.TLabel")
        lbl.pack(side=tk.LEFT, padx=10, pady=10)

        frame_list = ttk.LabelFrame(self.tab_mesai, text=" Gelecek Mesai ve Tatil Takvimi (Değiştirmek için üzerine tıklayın) ", style="Grey.TLabelframe")
        frame_list.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        frame_list.columnconfigure(0, weight=1)
        frame_list.rowconfigure(0, weight=1)

        cols_mesai = ("Tarih", "Gün", "Torna Mesaisi", "Dik İşlem Mesaisi")
        self.tree_mesai = ttk.Treeview(frame_list, columns=cols_mesai, show="headings")

        for col in cols_mesai:
            self.tree_mesai.heading(col, text=col)
            width = 250 if "Mesaisi" in col else 150
            self.tree_mesai.column(col, anchor="center", width=width)

        self.tree_mesai.tag_configure("holiday_row", background="#ffd1d1", foreground="#000000") 
        self.tree_mesai.tag_configure("sat_row", background="#fff5d7", foreground="#000000")     
        self.tree_mesai.tag_configure("sun_row", background="#ffe3de", foreground="#000000")     

        self.tree_mesai.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(frame_list, orient=tk.VERTICAL, command=self.tree_mesai.yview)
        self.tree_mesai.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.tree_mesai.bind("<Button-1>", self.toggle_mesai_status)

    def refresh_mesai_tab(self):
        self.tree_mesai.delete(*self.tree_mesai.get_children())
        today = datetime.now()

        for i in range(self.days_count):
            d_obj = today + timedelta(days=i)
            d_key = d_obj.strftime("%Y-%m-%d")
            d_str = d_obj.strftime("%d.%m.%Y")
            d_day = d_obj.strftime("%A")
            
            days_tr = {"Monday": "Pazartesi", "Tuesday": "Salı", "Wednesday": "Çarşamba", 
                       "Thursday": "Perşembe", "Friday": "Cuma", "Saturday": "Cumartesi", "Sunday": "Pazar"}
            d_day_tr = days_tr.get(d_day, d_day)

            is_holiday = self.is_public_holiday(d_obj)
            is_weekend = d_obj.weekday() >= 5

            if is_holiday:
                d_day_tr = f"🏛️ {d_day_tr} (RESMİ TATİL)"
                tag = ("holiday_row",)
            elif d_obj.weekday() == 5:
                tag = ("sat_row",)
            elif d_obj.weekday() == 6:
                tag = ("sun_row",)
            else:
                tag = ()

            ov_data = self.overtime_schedule.get(d_key, {"torna": False, "dik": False})
            
            torna_str = "🔥 ☑ MESAİ VAR" if ov_data.get("torna", False) else ("🏛️ Resmi Tatil (Tatil)" if is_holiday else ("💤 ☐ Hafta Sonu (Tatil)" if is_weekend else "💤 ☐ Mesai Yok"))
            dik_str = "🔥 ☑ MESAİ VAR" if ov_data.get("dik", False) else ("🏛️ Resmi Tatil (Tatil)" if is_holiday else ("💤 ☐ Hafta Sonu (Tatil)" if is_weekend else "💤 ☐ Mesai Yok"))

            self.tree_mesai.insert("", tk.END, iid=d_key, values=(d_str, d_day_tr, torna_str, dik_str), tags=tag)

    def toggle_mesai_status(self, event):
        region = self.tree_mesai.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree_mesai.identify_column(event.x)
            selected_item = self.tree_mesai.identify_row(event.y)
            if not selected_item: return

            ov_data = self.overtime_schedule.get(selected_item, {"torna": False, "dik": False})

            if column == "#3": 
                ov_data["torna"] = not ov_data.get("torna", False)
            elif column == "#4": 
                ov_data["dik"] = not ov_data.get("dik", False)

            self.overtime_schedule[selected_item] = ov_data
            self.refresh_all_views()
            self.save_data_to_file()

    def build_tab_bitmis_isler(self):
        self.tab_bitmis_isler.columnconfigure(0, weight=1)
        self.tab_bitmis_isler.rowconfigure(0, weight=1)

        frame_list = ttk.LabelFrame(self.tab_bitmis_isler, text=" 🏁 Biten ve Plan Kontrolden Silinen İşler (Detay için çift tıklayın, silmek için sağ tıklayın) ", style="Grey.TLabelframe")
        frame_list.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        frame_list.columnconfigure(0, weight=1)
        frame_list.rowconfigure(0, weight=1)

        cols_bitmis = ("İş Emri No", "Malzeme Kodu", "Adet", "Tamamlanma Durumu")
        self.tree_bitmis = ttk.Treeview(frame_list, columns=cols_bitmis, show="headings")
        for col in cols_bitmis:
            self.tree_bitmis.heading(col, text=col)
            self.tree_bitmis.column(col, anchor="center", width=220)
        self.tree_bitmis.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(frame_list, orient=tk.VERTICAL, command=self.tree_bitmis.yview)
        self.tree_bitmis.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.context_menu_bitmis = tk.Menu(self.root, tearoff=0)
        self.context_menu_bitmis.add_command(label="🗑️ Bu Bitmiş İşi Tamamen Sil", command=self.delete_selected_bitmis_job)

        self.tree_bitmis.bind("<Double-1>", self.bitmis_is_detay_goster)
        self.tree_bitmis.bind("<Button-3>", self.show_bitmis_context_menu)

    def show_bitmis_context_menu(self, event):
        item = self.tree_bitmis.identify_row(event.y)
        if item:
            self.tree_bitmis.selection_set(item)
            self.context_menu_bitmis.post(event.x_root, event.y_root)

    def delete_selected_bitmis_job(self):
        selected = self.tree_bitmis.selection()
        if not selected: return
        
        item_values = self.tree_bitmis.item(selected[0], "values")
        isemri_no = item_values[0]
        material_code = item_values[1]

        confirm = messagebox.askyesno("Silme Onayı", f"'{isemri_no}' numaralı bitmiş iş emrini sistemden tamamen silmek istediğinize emin misiniz?")
        if confirm:
            target_uid = None
            for j in self.jobs:
                if str(j.get("isemri")) == str(isemri_no) and str(j.get("material")) == str(material_code):
                    target_uid = j.get("unique_id")
                    break

            if supabase and target_uid:
                try:
                    supabase.table("cnc_is_emirleri").delete().eq("unique_id", target_uid).execute()
                except Exception as e:
                    print("Supabase bitmiş iş silme hatası:", e)

            self.jobs = [j for j in self.jobs if not (str(j.get("isemri")) == str(isemri_no) and str(j.get("material")) == str(material_code))]
            
            self.refresh_all_views()
            self.save_data_to_file()

    def refresh_bitmis_isler_tab(self):
        if not hasattr(self, "tree_bitmis"): return
        self.tree_bitmis.delete(*self.tree_bitmis.get_children())
        
        for job in self.jobs:
            torna_bitti = (job.get("torna_total_hours", 0) == 0) or job.get("torna_finished", False)
            dik_bitti = (job.get("dik_total_hours", 0) == 0) or job.get("dik_finished", False)

            if torna_bitti and dik_bitti:
                self.tree_bitmis.insert("", tk.END, values=(
                    job.get("isemri", "-"),
                    job.get("material", "-"),
                    job.get("qty", 0),
                    "Tüm Operasyonlar Tamamlandı"
                ))

    def bitmis_is_detay_goster(self, event):
        selected = self.tree_bitmis.selection()
        if not selected: return
        item_values = self.tree_bitmis.item(selected[0], "values")
        isemri_no = item_values[0]

        target_job = None
        for j in self.jobs:
            if str(j.get("isemri")) == str(isemri_no):
                target_job = j
                break

        if target_job:
            d = target_job.get("cloud_durum", {})
            
            operator_adi = d.get("torna_operator") or d.get("dik_operator") or d.get("username") or d.get("operator")
            if not operator_adi or operator_adi == "-":
                operator_adi = target_job.get("operator", "Saha Operatörü")

            detay = f"🏁 BİTMİŞ İŞ EMRİ DETAYI\n"
            detay += f"----------------------------------------\n"
            detay += f"• İş Emri No   : {target_job.get('isemri')}\n"
            detay += f"• Malzeme Kodu : {target_job.get('material')}\n"
            detay += f"• Hedef Adet   : {target_job.get('qty')}\n"
            detay += f"• İşlemi Yapan : {operator_adi}\n\n"

            torna_ops = d.get("torna_operasyonlar", [])
            if torna_ops:
                detay += "🌀 TORNA OPERASYONLARI:\n"
                for op in torna_ops:
                    detay += f"  - {op.get('opNo')}. Op | Başlangıç: {self.format_tarih_tr(op.get('baslangic'))}\n"
                    detay += f"    Bitiş: {self.format_tarih_tr(op.get('bitis'))}\n"
                detay += "\n"

            dik_ops = d.get("dik_operasyonlar", [])
            if dik_ops:
                detay += "📐 DİK İŞLEM OPERASYONLARI:\n"
                for op in dik_ops:
                    detay += f"  - {op.get('opNo')}. Op | Başlangıç: {self.format_tarih_tr(op.get('baslangic'))}\n"
                    detay += f"    Bitiş: {self.format_tarih_tr(op.get('bitis'))}\n"

            messagebox.showinfo(f"İş Emri Detayı: {isemri_no}", detay)

    def build_tab_ayarlar(self):
        self.tab_ayarlar.columnconfigure(0, weight=1)
        
        frame_settings = ttk.LabelFrame(self.tab_ayarlar, text=" ⚙️ Atölye Çalışma ve Mesai Saatleri Ayarları ", style="Grey.TLabelframe")
        frame_settings.pack(fill="x", padx=20, pady=20)

        ttk.Label(frame_settings, text="Hafta İçi Normal Çalışma Süresi (Dakika):", style="Grey.TLabel").grid(row=0, column=0, padx=15, pady=12, sticky="w")
        self.ent_work_weekday = ttk.Entry(frame_settings, font=("Segoe UI", 11, "bold"), width=12, style="Grey.TEntry")
        self.ent_work_weekday.grid(row=0, column=1, padx=15, pady=12, sticky="w")
        self.ent_work_weekday.insert(0, self.fmt_num(self.work_min_weekday))

        ttk.Label(frame_settings, text="Hafta İçi Fazla Mesai Süresi (Dakika):", style="Grey.TLabel").grid(row=1, column=0, padx=15, pady=12, sticky="w")
        self.ent_overtime_weekday = ttk.Entry(frame_settings, font=("Segoe UI", 11, "bold"), width=12, style="Grey.TEntry")
        self.ent_overtime_weekday.grid(row=1, column=1, padx=15, pady=12, sticky="w")
        self.ent_overtime_weekday.insert(0, self.fmt_num(self.overtime_min_weekday))

        ttk.Label(frame_settings, text="Hafta Sonu Mesai Süresi (Dakika):", style="Grey.TLabel").grid(row=2, column=0, padx=15, pady=12, sticky="w")
        self.ent_overtime_weekend = ttk.Entry(frame_settings, font=("Segoe UI", 11, "bold"), width=12, style="Grey.TEntry")
        self.ent_overtime_weekend.grid(row=2, column=1, padx=15, pady=12, sticky="w")
        self.ent_overtime_weekend.insert(0, self.fmt_num(self.overtime_min_weekend))

        btn_save = ttk.Button(frame_settings, text="💾 Ayarları Kaydet", command=self.save_settings)
        btn_save.grid(row=3, column=0, columnspan=2, pady=20)

    def save_settings(self):
        try:
            self.work_min_weekday = int(float(self.ent_work_weekday.get()))
            self.overtime_min_weekday = int(float(self.ent_overtime_weekday.get()))
            self.overtime_min_weekend = int(float(self.ent_overtime_weekend.get()))
            
            messagebox.showinfo("Başarılı", "Çalışma ve mesai ayarları başarıyla kaydedildi!")
            self.refresh_all_views()
            self.save_data_to_file()
        except ValueError:
            messagebox.showerror("Hata", "Lütfen sürelere geçerli sayısal değerler girin!")

if __name__ == "__main__":
    root = tk.Tk()
    app = CNCPlanningApp(root)
    root.mainloop()