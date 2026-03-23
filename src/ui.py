import tkinter as tk
from tkinter import ttk
from .workflow import AutomationWorkflow, GLXHWorkflow
from .vision_core import find_image_box, find_numbers_in_range

class AppUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Auto GK")
        self.root.geometry("450x600")
        self.root.resizable(False, False)
        
        self.workflow_thread = None
        self.glxh_thread = None
        self.overlay_window = None
        self.build_ui()
        
    def build_ui(self):
        self.main_container = tk.Frame(self.root, padx=10, pady=5)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        font_default = ("Arial", 9)
        
        # ====== 0. Frame Giả Lập Xếp Hạng ======
        self.glxh_frame = tk.LabelFrame(self.main_container, text="Giả Lập Xếp Hạng", font=font_default, padx=5, pady=5)
        self.glxh_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.wins_var = tk.IntVar(value=0)
        self.draws_var = tk.IntVar(value=0)
        self.losses_var = tk.IntVar(value=0)
        
        glxh_stats = tk.Frame(self.glxh_frame)
        glxh_stats.pack(fill=tk.X, pady=2)
        
        tk.Label(glxh_stats, text="Thắng:", font=font_default, fg="green").pack(side=tk.LEFT, padx=(10, 2))
        tk.Label(glxh_stats, textvariable=self.wins_var, font=font_default, width=3).pack(side=tk.LEFT)
        
        tk.Label(glxh_stats, text="Hòa:", font=font_default, fg="#d9a51e").pack(side=tk.LEFT, padx=(15, 2))
        tk.Label(glxh_stats, textvariable=self.draws_var, font=font_default, width=3).pack(side=tk.LEFT)
        
        tk.Label(glxh_stats, text="Thua:", font=font_default, fg="red").pack(side=tk.LEFT, padx=(15, 2))
        tk.Label(glxh_stats, textvariable=self.losses_var, font=font_default, width=3).pack(side=tk.LEFT)
        
        glxh_btns = tk.Frame(self.glxh_frame)
        glxh_btns.pack(fill=tk.X, pady=5)
        
        glxh_btns_inner = tk.Frame(glxh_btns)
        glxh_btns_inner.pack(anchor=tk.CENTER)
        
        self.btn_start_glxh = tk.Button(glxh_btns_inner, text="Tự động GLXH", command=self.start_auto_glxh, bg="green", fg="white", width=16, font=("Arial", 9, "bold"))
        self.btn_start_glxh.pack(side=tk.LEFT, padx=10)
        
        self.btn_stop_glxh = tk.Button(glxh_btns_inner, text="Tắt tự động GLXH", command=self.stop_auto_glxh, bg="gray", width=16, font=("Arial", 9, "bold"), state=tk.DISABLED)
        self.btn_stop_glxh.pack(side=tk.LEFT, padx=10)

        # ====== 1. Frame Thiết lập ======
        self.setup_frame = tk.LabelFrame(self.main_container, text="Thiết lập", font=font_default, padx=5, pady=5)
        self.setup_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Row 1
        r1 = tk.Frame(self.setup_frame)
        r1.pack(fill=tk.X, pady=2)
        tk.Label(r1, text="Dừng nâng cấp khi đạt +", width=20, anchor="w", font=font_default).pack(side=tk.LEFT)
        self.target_level_var = tk.IntVar(value=13)
        tk.Spinbox(r1, from_=1, to=15, textvariable=self.target_level_var, width=5, font=font_default).pack(side=tk.LEFT, padx=(0, 15))
        tk.Checkbutton(r1, text="Âm báo", font=font_default).pack(side=tk.LEFT)
        
        # Row 2
        r2 = tk.Frame(self.setup_frame)
        r2.pack(fill=tk.X, pady=2)
        tk.Label(r2, text="Số lượng phôi nâng cấp:", width=20, anchor="w", font=font_default).pack(side=tk.LEFT)
        self.quantity_var = tk.IntVar(value=5)
        tk.Spinbox(r2, from_=1, to=10, textvariable=self.quantity_var, width=5, font=font_default).pack(side=tk.LEFT, padx=(0, 15))
        tk.Checkbutton(r2, text="Nâng cấp nhanh (Space)", font=font_default).pack(side=tk.LEFT)
        
        # Row 3
        r3 = tk.Frame(self.setup_frame)
        r3.pack(fill=tk.X, pady=2)
        tk.Checkbutton(r3, text='Dừng auto khi gặp thông báo "CHI PHÍ TIÊU HAO"', fg="red", font=font_default).pack(side=tk.LEFT)
        
        # Row 4
        r4 = tk.Frame(self.setup_frame)
        r4.pack(fill=tk.X, pady=2)
        tk.Checkbutton(r4, text="Bảo vệ nâng cấp bằng BP", fg="blue", font=font_default).pack(side=tk.LEFT)
        tk.Spinbox(r4, from_=1, to=100, width=5, font=font_default).pack(side=tk.LEFT, padx=(5, 5))
        tk.Label(r4, text="% từ +8 trở lên", fg="blue", font=font_default).pack(side=tk.LEFT)
        
        # Row 5
        r5 = tk.Frame(self.setup_frame)
        r5.pack(fill=tk.X, pady=2)
        
        self.ovr_from_var = tk.IntVar(value=110)
        self.ovr_to_var = tk.IntVar(value=115)
        
        tk.Checkbutton(r5, text="Chọn phôi OVR từ", font=font_default).pack(side=tk.LEFT)
        tk.Spinbox(r5, from_=50, to=150, textvariable=self.ovr_from_var, width=5, font=font_default).pack(side=tk.LEFT, padx=(0, 5))
        tk.Label(r5, text="đến", font=font_default).pack(side=tk.LEFT)
        tk.Spinbox(r5, from_=50, to=150, textvariable=self.ovr_to_var, width=5, font=font_default).pack(side=tk.LEFT, padx=5)

        # ====== 2. Frame Mua phôi tự động ======
        self.buy_frame = tk.LabelFrame(self.main_container, text="Mua phôi tự động", font=font_default, padx=5, pady=5)
        self.buy_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Row 1
        b1 = tk.Frame(self.buy_frame)
        b1.pack(fill=tk.X, pady=2)
        tk.Checkbutton(b1, text="Tự mua phôi đầy và tiếp tục đập thẻ", font=font_default).pack(side=tk.LEFT)
        
        # Row 2
        b2 = tk.Frame(self.buy_frame)
        b2.pack(fill=tk.X, pady=2)
        tk.Label(b2, text="OVR từ", width=8, anchor="w", font=font_default).pack(side=tk.LEFT)
        tk.Spinbox(b2, from_=50, to=150, width=5, font=font_default).pack(side=tk.LEFT)
        tk.Label(b2, text="đến", font=font_default).pack(side=tk.LEFT, padx=5)
        tk.Spinbox(b2, from_=50, to=150, width=5, font=font_default).pack(side=tk.LEFT)
        
        # Row 3
        b3 = tk.Frame(self.buy_frame)
        b3.pack(fill=tk.X, pady=2)
        tk.Label(b3, text="Giá", width=8, anchor="w", font=font_default).pack(side=tk.LEFT)
        tk.Spinbox(b3, from_=1, to=1000, width=8, font=font_default).pack(side=tk.LEFT)
        tk.Label(b3, text="= 9 tỷ BP", fg="red", font=font_default).pack(side=tk.LEFT, padx=5)
        
        # Row 4
        b4 = tk.Frame(self.buy_frame)
        b4.pack(fill=tk.X, pady=2)
        tk.Label(b4, text="Số lượng:", width=8, anchor="w", font=font_default).pack(side=tk.LEFT)
        tk.Spinbox(b4, from_=1, to=100, width=5, font=font_default).pack(side=tk.LEFT)
        
        # ====== 3. Frame Buttons ======
        self.btn_frame = tk.Frame(self.main_container)
        self.btn_frame.pack(fill=tk.X, pady=10)
        
        bc = tk.Frame(self.btn_frame)
        bc.pack(anchor=tk.CENTER)
        
        self.btn_start = tk.Button(bc, text="Bật Auto", command=self.start_auto, bg="green", fg="white", width=15, font=("Arial", 9, "bold"))
        self.btn_start.pack(side=tk.LEFT, padx=20)
        
        self.btn_stop = tk.Button(bc, text="Tắt Auto", command=self.stop_auto, bg="gray", width=15, font=("Arial", 9, "bold"), state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=20)
        
        # ====== 4. Status Labels ======
        self.st_frame = tk.Frame(self.main_container)
        self.st_frame.pack(fill=tk.BOTH, expand=True)
        
        s1 = tk.Frame(self.st_frame)
        s1.pack(fill=tk.X, anchor="w", pady=(0, 20))
        tk.Label(s1, text="Trạng thái:", font=font_default).pack(side=tk.LEFT, padx=(0,5))
        self.lbl_status = tk.Label(s1, text="chưa bật auto!", fg="red", font=font_default)
        self.lbl_status.pack(side=tk.LEFT)
        
        s2 = tk.Frame(self.st_frame)
        s2.pack(fill=tk.X, anchor="w")
        tk.Label(s2, text="Màn hình auto:", font=font_default).pack(side=tk.LEFT)
        tk.Label(s2, text=" Nâng cấp cầu thủ => Cầu thủ đang sở hữu", fg="purple", font=font_default).pack(side=tk.LEFT)
        
        s3 = tk.Frame(self.st_frame)
        s3.pack(fill=tk.X, anchor="w")
        tk.Label(s3, text="(Không chọn phôi trước khi bật auto)", fg="blue", font=font_default).pack(side=tk.LEFT)

    def log_message(self, msg: str):
        print(msg)

    def show_overlay(self):
        # Nếu chưa có cửa sổ overlay, tạo mới
        if self.overlay_window is None:
            self.overlay_window = tk.Toplevel(self.root)
            self.overlay_window.overrideredirect(True)
            self.overlay_window.attributes("-topmost", True)
            self.overlay_window.attributes("-transparentcolor", "white")
            self.overlay_window.config(bg="white")
            
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            self.overlay_window.geometry(f"{screen_w}x{screen_h}+0+0")
            
            self.overlay_canvas = tk.Canvas(self.overlay_window, bg="white", highlightthickness=0, width=screen_w, height=screen_h)
            self.overlay_canvas.pack(fill=tk.BOTH, expand=True)

        # Xóa các shape cũ trên Canvas
        self.overlay_canvas.delete("all")

        try:
            min_val = self.ovr_from_var.get()
            max_val = self.ovr_to_var.get()
        except Exception:
            min_val, max_val = 110, 115
            
        header_box = find_image_box("assets/upgradeHeader.png", confidence=0.7)
        bg_box = find_image_box("assets/upgradeBg.png", confidence=0.7)
        # Nâng confidence lên 0.9 để nhận diện tuyệt đối chính xác chữ iOvr.png, tránh bị dính rác sang các chữ OVR khác
        iovr_box = find_image_box("assets/iOvr.png", confidence=0.9)
        
        region = None
        if header_box and bg_box and iovr_box:
            y1 = min(header_box[1], bg_box[1])
            y2 = max(header_box[1] + header_box[3], bg_box[1] + bg_box[3])
            
            ix, iy, iw, ih = iovr_box
            # Gỡ bỏ lề âm/dương, ôm vừa khít 100% độ rộng ảnh iOvr.png như bạn muốn
            x1 = ix
            x2 = ix + iw
            region = (x1, y1, x2, y2)
            
            # Vẽ giới hạn quét cụ thể của cột OVR màu xanh
            self.overlay_canvas.create_rectangle(x1, y1, x2, y2, outline="blue", width=3, dash=(5, 5))
            
            # Vẽ khung lớn đỏ
            rx_min, ry_min = min(header_box[0], bg_box[0]), min(header_box[1], bg_box[1])
            rx_max, ry_max = max(header_box[0]+header_box[2], bg_box[0]+bg_box[2]), max(header_box[1]+header_box[3], bg_box[1]+bg_box[3])
            self.overlay_canvas.create_rectangle(rx_min, ry_min, rx_max, ry_max, outline="red", width=2, dash=(2, 4))

        elif header_box and bg_box:
            rx_min, ry_min = min(header_box[0], bg_box[0]), min(header_box[1], bg_box[1])
            rx_max, ry_max = max(header_box[0]+header_box[2], bg_box[0]+bg_box[2]), max(header_box[1]+header_box[3], bg_box[1]+bg_box[3])
            region = (rx_min, ry_min, rx_max, ry_max)
            self.overlay_canvas.create_rectangle(rx_min, ry_min, rx_max, ry_max, outline="red", width=3, dash=(5, 5))

        boxes = find_numbers_in_range(min_val, max_val, confidence=0.65, region=region)
            
        if boxes:
            for box in boxes:
                x, y, w, h = box
                pad = 4
                self.overlay_canvas.create_rectangle(x - pad, y - pad, x + w + pad, y + h + pad, outline="red", width=4)
                
        # Lặp lại sau mỗi 1000ms nếu auto đang bật
        if self.workflow_thread is not None and self.workflow_thread.is_alive():
            self.root.after(200, self.show_overlay)

    def hide_overlay(self):
        if self.overlay_window is not None:
            try:
                self.overlay_window.destroy()
            except:
                pass
            self.overlay_window = None

    def start_auto(self):
        if self.workflow_thread is not None and self.workflow_thread.is_alive():
            return 
            
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.lbl_status.config(text="đang chạy auto...", fg="green")
        
        try:
            target_lvl = self.target_level_var.get()
            qty = self.quantity_var.get()
            ovr_min = self.ovr_from_var.get()
            ovr_max = self.ovr_to_var.get()
        except ValueError:
            target_lvl, qty, ovr_min, ovr_max = 13, 5, 110, 115
            
        self.workflow_thread = AutomationWorkflow(
            target_level=target_lvl, 
            quantity=qty, 
            ovr_min=ovr_min, 
            ovr_max=ovr_max, 
            log_callback=self.log_message
        )
        self.workflow_thread.start()
        
        self.root.after(1500, self.show_overlay)

    def stop_auto(self):
        if self.workflow_thread is not None and self.workflow_thread.is_alive():
            self.workflow_thread.stop()
            self.btn_stop.config(state=tk.DISABLED)
            self.hide_overlay()
            
            self.check_thread_alive()

    def check_thread_alive(self):
        if self.workflow_thread.is_alive():
            self.root.after(500, self.check_thread_alive)
        else:
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            self.lbl_status.config(text="chưa bật auto!", fg="red")
            self.hide_overlay()

    def start_auto_glxh(self):
        if self.glxh_thread is not None and self.glxh_thread.is_alive():
            return
            
        self.btn_start_glxh.config(state=tk.DISABLED)
        self.btn_stop_glxh.config(state=tk.NORMAL)
        self.btn_start.config(state=tk.DISABLED) # Prevent mix UI interaction
        self.lbl_status.config(text="đang chạy auto GLXH...", fg="green")
        
        self.glxh_thread = GLXHWorkflow(log_callback=self.log_message)
        self.glxh_thread.start()
        
        self.check_glxh_thread_alive()

    def stop_auto_glxh(self):
        if self.glxh_thread is not None and self.glxh_thread.is_alive():
            self.glxh_thread.stop()
            self.btn_stop_glxh.config(state=tk.DISABLED)

    def check_glxh_thread_alive(self):
        if self.glxh_thread and self.glxh_thread.is_alive():
            self.root.after(500, self.check_glxh_thread_alive)
        else:
            self.btn_start_glxh.config(state=tk.NORMAL)
            self.btn_stop_glxh.config(state=tk.DISABLED)
            self.btn_start.config(state=tk.NORMAL)
            self.lbl_status.config(text="chưa bật auto!", fg="red")
