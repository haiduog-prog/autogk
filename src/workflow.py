import threading
import time
import ctypes
import pyautogui
import cv2
import numpy as np
from .vision_core import wait_for_image, click_image, find_image, find_image_box, draw_red_box_on_screen, safe_click, safe_scroll, capture_screen, is_upgrade_bar_full, click_dynamic_continue_button, parse_upgrade_screen, get_fc_window_rect
from .ocr import extract_ovr_from_rows, init_reader


def find_image_debug(image_path: str, screen_img, log_callback, confidence: float = 0.7) -> bool:
    """Template matching với debug log. Tự động crop template khi quá lớn so với screen."""
    try:
        import cv2
        from .vision_core import _TEMPLATE_CACHE
        
        sh, sw = screen_img.shape[:2]
        ctx_cache_key = f"_ctx_{image_path}_{sw}x{sh}"
        
        if ctx_cache_key in _TEMPLATE_CACHE:
            template_img = _TEMPLATE_CACHE[ctx_cache_key]
        else:
            raw_img = cv2.imread(image_path, cv2.IMREAD_COLOR)
            if raw_img is None:
                log_callback(f"[Context Debug] ❌ Không tìm thấy file: {image_path}")
                return False
            
            template_img = raw_img
            th, tw = template_img.shape[:2]
            
            # Nếu template quá lớn (>50% diện tích screen), crop góc trên-trái
            # Vùng này chứa header/navigation — ít thay đổi nhất
            if (th * tw) > (sh * sw) * 0.5:
                crop_h = int(th * 0.3)
                crop_w = int(tw * 0.5)
                template_img = template_img[0:crop_h, 0:crop_w]
                log_callback(f"[Context Debug] Template quá lớn → crop: ({tw}x{th}) → ({crop_w}x{crop_h})")
                th, tw = template_img.shape[:2]
            
            # Resize nếu vẫn lớn hơn screen
            if th > sh or tw > sw:
                scale = min(sw / tw, sh / th) * 0.95
                new_w = int(tw * scale)
                new_h = int(th * scale)
                template_img = cv2.resize(template_img, (new_w, new_h), interpolation=cv2.INTER_AREA)
                log_callback(f"[Context Debug] Resize: ({tw}x{th}) → ({new_w}x{new_h})")
            
            _TEMPLATE_CACHE[ctx_cache_key] = template_img
        
        result = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        
        log_callback(f"[Context Debug] Confidence: {max_val:.4f} (cần >= {confidence}) | Vị trí: {max_loc}")
        
        return max_val >= confidence
    except Exception as e:
        log_callback(f"[Context Debug] Lỗi: {e}")
        return False

def focus_game_window(log_callback=print):
    """Tìm, focus, và resize cửa sổ game FC Online về tỉ lệ 16:9 cố định."""
    user32 = ctypes.windll.user32
    EnumWindows = user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    GetWindowText = user32.GetWindowTextW
    GetWindowTextLength = user32.GetWindowTextLengthW
    IsWindowVisible = user32.IsWindowVisible
    SetForegroundWindow = user32.SetForegroundWindow
    ShowWindow = user32.ShowWindow
    MoveWindow = user32.MoveWindow

    # Kích thước 16:9 cố định
    TARGET_W = 1920
    TARGET_H = 1080

    # Lấy kích thước màn hình làm giới hạn
    screen_w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
    screen_h = user32.GetSystemMetrics(1)  # SM_CYSCREEN

    # Nếu màn hình nhỏ hơn 1920x1080, chọn kích thước 16:9 vừa nhất
    if screen_w < TARGET_W or screen_h < TARGET_H:
        scale = min(screen_w / TARGET_W, screen_h / TARGET_H)
        final_w = int(TARGET_W * scale)
        final_h = int(TARGET_H * scale)
    else:
        final_w = TARGET_W
        final_h = TARGET_H

    found_hwnd = [None]

    def foreach_window(hwnd, lParam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                GetWindowText(hwnd, buff, length + 1)
                title = buff.value.upper()
                if "FC ONLINE" in title or "FIFA ONLINE" in title or "EA SPORTS" in title:
                    found_hwnd[0] = hwnd
                    return False  # Stop enumerating
        return True

    EnumWindows(EnumWindowsProc(foreach_window), 0)

    if found_hwnd[0]:
        hwnd = found_hwnd[0]
        ShowWindow(hwnd, 9)  # SW_RESTORE
        SetForegroundWindow(hwnd)

        # Resize về 16:9 cố định, đặt góc trên-trái tại (0, 0)
        MoveWindow(hwnd, 0, 0, final_w, final_h, True)

        log_callback(f"[System] Đã focus + resize cửa sổ game FC Online → {final_w}x{final_h} (16:9)")
    else:
        log_callback("[System] Không tìm thấy cửa sổ game FC Online! Vui lòng bật game.")

class AutomationWorkflow(threading.Thread):
    def __init__(self, target_level: int = 5, quantity: int = 5, ovr_min: int = 110, ovr_max: int = 115, log_callback=None):
        super().__init__()
        self.daemon = True # Thread tự kill khi App thoát
        self._is_running = False
        self._is_paused = False
        self.target_level = target_level
        self.quantity = quantity
        self.ovr_min = ovr_min
        self.ovr_max = ovr_max
        self.log_callback = log_callback if log_callback else print

    def stop(self):
        self._is_running = False
        self.log_callback("[System] Đang gửi lệnh Dừng. Vui lòng đợi hoàn tất chu kỳ lệnh...")

    def pause(self):
        self._is_paused = True
        self.log_callback("[System] Đã TẠM DỪNG (Pause). Bấm Tiếp Tục để chạy tiếp.")

    def resume(self):
        self._is_paused = False
        self.log_callback("[System] Đã TIẾP TỤC chạy vòng lặp.")

    def _wait_if_paused(self):
        while getattr(self, '_is_paused', False) and self._is_running:
            time.sleep(0.5)

    def _check_upgrade_context(self) -> bool:
        """Kiểm tra người dùng đang ở đúng màn hình nâng cấp thẻ bằng OCR header detection."""
        import cv2
        screen_img = capture_screen(scale_percent=100)
        ui = parse_upgrade_screen(screen_img, debug_draw=False)

        if ui is None:
            self.log_callback("[Context] ❌ Không parse được giao diện!")
            return False

        # Dùng OCR quét vùng header, tìm text 'OVR'
        init_reader()
        from . import ocr as _ocr_module
        reader = _ocr_module._reader
        
        # materials_header chứa {x, y, w, h} của vùng header
        hdr = ui["materials_header"]
        
        # Tính toán viewport thật (offset ox, oy của cuờng sổ game)
        ox = ui.get("window_rect", (0, 0, 0, 0))[0]
        oy = ui.get("window_rect", (0, 0, 0, 0))[1]
        hx = max(hdr["x"] - ox, 0)
        hy = max(hdr["y"] - oy, 0)
        hw = hdr["w"]
        hh = hdr["h"]
        
        # Crop vùng header từ ảnh screen
        header_crop = screen_img[hy:hy+hh, hx:hx+hw]
        if header_crop.size == 0:
            self.log_callback("[Context] ❌ Vùng header rỗng!")
            return False
        
        # Upscale 2x để EasyOCR đọc chính xác (đúng chuẩn như ocr.py)
        hc, wc = header_crop.shape[:2]
        header_big = cv2.resize(header_crop, (wc * 2, hc * 2), interpolation=cv2.INTER_CUBIC)
        
        results = reader.readtext(header_big, detail=1)
        
        for (bbox, text, conf) in results:
            if "OVR" in text.upper() and conf > 0.4:
                self.log_callback(f"[Context] ✅ Tìm thấy '{text}' (conf={conf:.4f}) → Đúng màn hình Nâng Cấp Thẻ!")
                return True
        
        header_texts = [t for (_, t, _) in results]
        self.log_callback(f"[Context] ❌ Không tìm thấy 'OVR' trong header. Texts: {header_texts}")
        self.log_callback("[Context] Hãy vào Giao diện Nâng Cấp thẻ!")
        return False

    def _prepare_materials(self) -> list[dict]:
        """Cuộn xuống cuối danh sách phôi và quét thông tin từng item bằng OCR.

        Returns:
            Danh sách dict chứa thông tin row, ovr, vạch, center cho mỗi phôi.
            Trả về list rỗng nếu không quét được phôi nào.
        """
        from .vision_core import get_fc_window_rect

        rect = get_fc_window_rect()
        if rect:
            # Nhắm vào giữa vùng danh sách phôi (bên phải màn hình)
            list_x = rect[0] + int(rect[2] * 0.60)
            list_y = rect[1] + int(rect[3] * 0.55)
        else:
            screen_w, screen_h = pyautogui.size()
            list_x = int(screen_w * 0.60)
            list_y = int(screen_h * 0.55)

        self.log_callback(f"► Di chuột (hover) vào vùng danh sách tại ({list_x}, {list_y}) để chuẩn bị cuộn...")
        import pydirectinput
        pydirectinput.moveTo(list_x, list_y)
        time.sleep(0.5)

        # Cuộn chuột nhiều lần với tốc độ nhanh.
        # Ở các game DirectX, nếu gửi SCROLL = -5000 trong 1 frame, game sẽ ghim lại 
        # (clamp) thành 1 nấc cuộn duy nhất. Do đó cách đúng phải là gửi liên tiếp các 
        # lệnh cuộn nhỏ (-120 unit) trong nhiều khung hình liên tiếp.
        self.log_callback(f"  [Scroll] Đang lăn chuột 200 lần để cuộn chạm đáy...")
        
        # Bắt đầu lăn chuột liên tục (200 nấc cuộn, mỗi nấc -120 là chuẩn 1 notch Windows)
        # 200 nấc đảm bảo sẽ tuột xuống đáy bất chấp danh sách phôi dài đến nhường nào.
        # Giữa mỗi lần lăn nghỉ 0.04s để game kịp xử lý frame mới (tổng tốn 8s)
        import pyautogui
        for i in range(200):
            pyautogui.scroll(-120)
            time.sleep(0.04)
            
        time.sleep(0.8)

        # Rời chuột ra xa danh sách để ẩn Tooltip (bảng thông số mở rộng khi hover vào cầu thủ)
        # Tọa độ an toàn: Góc dưới bên trái của khu vực danh sách (vùng trống "Tăng % nâng cấp")
        # Không dùng góc (10, 10) vì nó có thể vô tình mở ra thanh Menu trên cùng che mất Header OVR!
        safe_hover_x = rect[0] + int(rect[2] * 0.35) if rect else int(pyautogui.size()[0] * 0.35)
        safe_hover_y = rect[1] + int(rect[3] * 0.85) if rect else int(pyautogui.size()[1] * 0.85)
        self.log_callback(f"► Kéo chuột đi chỗ an toàn ({safe_hover_x}, {safe_hover_y}) để tắt tooltip...")
        pydirectinput.moveTo(safe_hover_x, safe_hover_y)
        time.sleep(0.5)

        # Khởi tạo OCR reader (lazy)
        init_reader()

        self.log_callback("► OCR đang quét OVR tất cả hàng phôi...")
        screen_img = capture_screen(scale_percent=100)
        ui = parse_upgrade_screen(screen_img, debug_draw=True)
        ovr_rows = extract_ovr_from_rows(ui, screen_img, debug_draw=True)

        if not ovr_rows:
            self.log_callback("[WARN] OCR không đọc được OVR nào. Thử lại sau 2s...")
            time.sleep(2)
            screen_img = capture_screen(scale_percent=100)
            ui = parse_upgrade_screen(screen_img, debug_draw=True)
            ovr_rows = extract_ovr_from_rows(ui, screen_img, debug_draw=True)

        self.log_callback(f"[OCR] Tìm thấy {len(ovr_rows)} hàng: {[(r['row'], r['ovr']) for r in ovr_rows]}")
        return ovr_rows
    def _pick_materials(self, ovr_rows: list[dict], silent: bool = False) -> bool:
        """
        Lặp qua ovr_rows chọn ra nhiều nhất 5 phôi có tổng số vạch = 5.
        Ưu tiên các phôi phụ có tổng OVR nhỏ nhất.

        Returns:
            True nếu chọn phôi thành công, False nếu không đủ phôi.
        """
        import itertools

        if not silent:
            self.log_callback(f"[Chọn phôi] Bắt đầu tìm tổ hợp từ OVR {self.ovr_min} đến {self.ovr_max}...")

        # Lọc phôi trong khoảng OVR mục tiêu
        valid_rows = [r for r in ovr_rows if self.ovr_min <= r["ovr"] <= self.ovr_max]
        valid_rows.sort(key=lambda r: r["ovr"])

        if not valid_rows:
            if not silent:
                self.log_callback(f"[Lỗi] Không có hàng nào có OVR trong khoảng {self.ovr_min}-{self.ovr_max}")
            return False

        # Loại bỏ phôi có vạch = 0
        pool = [r for r in valid_rows if r.get("vach", 0) > 0]

        if not pool:
            if not silent:
                self.log_callback("[Lỗi] Tất cả phôi đều có vạch = 0, không thể chọn!")
            return False

        # Tìm tổ hợp tối đa 5 phôi có tổng vạch = 5
        MAX_PHOI = 5
        TARGET_VACH = 5
        valid_combos = []

        for k in range(1, min(MAX_PHOI + 1, len(pool) + 1)):
            for combo in itertools.combinations(pool, k):
                if sum(item["vach"] for item in combo) == TARGET_VACH:
                    valid_combos.append(combo)

        if not valid_combos:
            if not silent:
                self.log_callback("[Lỗi] Không tìm được tổ hợp phôi nào có tổng đúng = 5 vạch.")
            return False

        # Ưu tiên tổ hợp có tổng OVR thấp nhất
        valid_combos.sort(key=lambda combo: sum(item["ovr"] for item in combo))
        best_combo = valid_combos[0]

        self.log_callback(f"► Tổ hợp tối ưu ({len(best_combo)} phôi): "
                          f"{[f'Row {r['row']}: OVR {r['ovr']} ({r['vach']} vạch)' for r in best_combo]}")

        # Tiến hành click chọn từng phôi
        for row_data in best_combo:
            if not self._is_running:
                return False
            self._wait_if_paused()

            cx, cy = row_data["center"]
            safe_click(cx, cy, log_callback=None)
            self.log_callback(f"  → Đã chọn phôi OVR {row_data['ovr']} - {row_data['vach']} vạch (row {row_data['row']})")
            time.sleep(0.5)

            if is_upgrade_bar_full():
                self.log_callback("► Vạch upgrade xanh đã ĐẦY (100%). Dừng nhặt phôi!")
                break

        self.log_callback("[Hoàn tất] Đã chọn xong tổ hợp phôi đạt tổng 5 vạch.")
        return True

    def _search_up_for_materials(self, initial_rows: list[dict]) -> bool:
        """Cuộn list lên trên từ từ để tìm phôi nếu ở đáy không thỏa mãn."""
        self.log_callback("► Đang thử cuộn ngược lên trên để tìm thêm phôi...")
        import pyautogui
        import pydirectinput
        from .vision_core import parse_upgrade_screen, capture_screen, get_fc_window_rect
        from .ocr import extract_ovr_from_rows, init_reader
        
        current_rows = initial_rows
        
        rect = get_fc_window_rect()
        list_x = rect[0] + int(rect[2] * 0.60) if rect else int(pyautogui.size()[0] * 0.60)
        list_y = rect[1] + int(rect[3] * 0.55) if rect else int(pyautogui.size()[1] * 0.55)
        
        safe_hover_x = rect[0] + int(rect[2] * 0.35) if rect else int(pyautogui.size()[0] * 0.35)
        safe_hover_y = rect[1] + int(rect[3] * 0.85) if rect else int(pyautogui.size()[1] * 0.85)
        
        init_reader()
        
        # Thử tối đa 10 lần cuộn lên
        for attempt in range(10):
            if not self._is_running:
                return False
                
            # Đếm số lượng phôi có vạch >= 1 từ lần quét trước để tính quãng đường cuộn hợp lý
            valid_count = len([r for r in current_rows if r.get("vach", 0) >= 1])
            
            # Mỗi phôi chiếm khoảng 1 nấc cuộn. Cuộn lên = 10 - số phôi hợp lệ.
            # Giới hạn trong khoảng [1, 15] để đảm bảo luôn có cuộn và không bị lố.
            scroll_count = max(1, min(15, 10 - valid_count))
                
            self.log_callback(f"  [Tìm ngược] Lượt {attempt+1}/10. Phôi giữ lại ở đáy: {valid_count} -> Sẽ cuộn lên {scroll_count} nấc.")
            pydirectinput.moveTo(list_x, list_y)
            time.sleep(0.3)
            
            # Cuộn LÊN: scroll dương (+120)
            for _ in range(scroll_count):
                pyautogui.scroll(120)
                time.sleep(0.04)
                
            time.sleep(0.8)
            
            # Kéo chuột ra vùng an toàn để tránh tooltip
            pydirectinput.moveTo(safe_hover_x, safe_hover_y)
            time.sleep(0.5)
            
            screen_img = capture_screen(scale_percent=100)
            ui = parse_upgrade_screen(screen_img, debug_draw=False)
            ovr_rows = extract_ovr_from_rows(ui, screen_img, debug_draw=False)
            
            # Kiểm tra xem có chạm đỉnh chưa (row không đổi hoặc rỗng)
            if not ovr_rows or ovr_rows == current_rows:
                self.log_callback("  [Tìm ngược] Đã chạm ĐỈNH danh sách hoặc OCR không đọc được thêm.")
                break
                
            current_rows = ovr_rows
            
            # Thử pick phôi ngay trong trang vừa quét (silent=True để đỡ spam lỗi)
            self.log_callback(f"  [Tìm ngược] Quét được {len(ovr_rows)} phôi mới. Đang thử ghép...")
            success = self._pick_materials(ovr_rows, silent=True)
            if success:
                return True
                
        return False

    def run(self):
        """Vòng lặp chính điều phối toàn bộ quá trình auto đập thẻ."""
        self._is_running = True

        focus_game_window(self.log_callback)
        time.sleep(1.0)

        self.log_callback(f"[Khởi động] Bắt đầu Nâng Cấp Thẻ. Mục tiêu: Cấp +{self.target_level}")

        try:
            while self._is_running:
                self._wait_if_paused()

                # Bước 0: Kiểm tra nếu nút upgradeButton đã có sẵn (user tự bấm dở)
                if find_image("assets/upgradeButton.png", confidence=0.8):
                    self.log_callback("► Phát hiện nút Nâng cấp có sẵn, bấm ngay!")
                    click_image("assets/upgradeButton.png", confidence=0.8, delay=3.0)
                else:
                    # Bước 1: Kiểm tra context màn hình
                    if not self._check_upgrade_context():
                        time.sleep(2.0)
                        continue

                    # Bước 2: Chuẩn bị phôi (cuộn xuống + quét OCR)
                    self.log_callback("1. Chuẩn bị phôi — cuộn danh sách và quét thông tin...")
                    ovr_rows = self._prepare_materials()

                    if not self._is_running:
                        break

                    # Bước 3: Chọn phôi
                    self.log_callback("2. Bắt đầu chọn phôi tự động ở đáy danh sách...")
                    pick_success = self._pick_materials(ovr_rows, silent=True)

                    # Bước 3.5: Cuộn ngược lên nếu đáy không đủ phôi
                    if not pick_success:
                        self.log_callback("[Cảnh Báo] Màn hình đáy không thoả mãn tổ hợp 5 vạch!")
                        pick_success = self._search_up_for_materials(ovr_rows)

                    if not pick_success:
                        self.log_callback("[System] ❌ Thử tìm mọi trang đều không đủ phôi hợp lệ! Dừng auto.")
                        break

                    if not self._is_running:
                        break

                    # Bước 4: Click "Tiếp theo"
                    time.sleep(1.0)
                    self.log_callback("► Bấm [Tiếp theo]")
                    try:
                        click_dynamic_continue_button()
                        time.sleep(1.0)
                    except Exception as e:
                        self.log_callback(f"[Lỗi] Xử lý giao diện Tiếp theo: {e}")
                        time.sleep(2)
                        continue

                    if not self._is_running:
                        break

                    # Bước 5: Click "Tiến hành"
                    self.log_callback("► Bấm [Tiến hành]")
                    try:
                        click_image("assets/processButton.png", confidence=0.8, delay=1.0)
                    except Exception:
                        pass

                    if not self._is_running:
                        break

                    # Bước 6: Click "Nâng cấp"
                    self.log_callback("► Bấm Xác nhận (upgradeButton)")
                    try:
                        click_image("assets/upgradeButton.png", confidence=0.8, delay=3.0)
                    except Exception:
                        pass

                if not self._is_running:
                    break

                # Bước 7: Kiểm tra kết quả nâng cấp bằng OCR
                self.log_callback("3. Đợi kết quả nâng cấp (OCR)...")
                from .vision_core import wait_for_upgrade_result_ocr, detect_card_level_result_screen
                success = wait_for_upgrade_result_ocr(timeout=12, log_callback=self.log_callback)
                if success:
                    self.log_callback("[Thành Công] ✅ Quét OCR thấy dòng chữ 'Nâng cấp thành công'!")
                    
                    # Bước 7.5: Quét Template Matching từ +1 đến +13 để dò Level mới lên
                    self.log_callback("► Đang check Level hiện tại thẻ...")
                    current_level = detect_card_level_result_screen(log_callback=self.log_callback)
                    
                    if current_level:
                        if current_level >= self.target_level:
                            self.log_callback(f"[Hoàn Thành] 🎉 Đã cộng thẻ lên được mốc cài đặt: +{self.target_level}! Dừng Auto.")
                            break
                    else:
                        self.log_callback("► Xịt nhận diện: Không dò ra cấp thẻ từ chùm template mốc (+1 đến +13).")
                else:
                    self.log_callback("[Thất Bại] Phôi xịt hoặc Không nhận diện được chữ báo thành công.")

                if not self._is_running:
                    break

                # Bước 8: Bấm Kế tiếp / Xong sau khi đập thẻ
                self.log_callback("► Bấm [Kế tiếp / Xong] ở màn kết quả đập thẻ")
                try:
                    click_image("assets/afterUpgrade.png", confidence=0.8, delay=2.0)
                except Exception:
                    pass

                if not self._is_running:
                    break

                # Bước 9: Bấm Tiếp tục Nâng Cấp (nếu chưa đạt mốc)
                if find_image("assets/btnNext.png", confidence=0.8):
                    self.log_callback("► Phát hiện nút [Tiếp tục đập thẻ]. Quay về Chọn phôi...")
                    try:
                        click_image("assets/btnNext.png", confidence=0.8, delay=2.0)
                    except Exception:
                        pass
                    time.sleep(1.0)
                    continue
                else:
                    self.log_callback("Chưa lấy được kết quả Nút tiếp tục đập. Quanh quẩn thử lại 2s...")
                    time.sleep(2)
                    continue

        except Exception as e:
            self.log_callback(f"[Lỗi vòng lặp Auto]: Ngắt kịch bản do → {e}")
        finally:
            self._is_running = False
            self.log_callback("[System] Trạng thái: ĐÃ DỪNG AUTO ĐẬP THẺ.")


class GLXHWorkflow(threading.Thread):
    """
    Quản lý luồng kịch bản Giả Lập Xếp Hạng (GLXH) cho FC Online.
    """
    def __init__(self, log_callback=None):
        super().__init__()
        self.daemon = True
        self._is_running = False
        self.log_callback = log_callback if log_callback else print

    def stop(self):
        self._is_running = False
        self.log_callback("[GLXH] Đang báo dừng tệp lệnh. Vui lòng đợi hết chu kỳ...")

    def run(self):
        self._is_running = True
        focus_game_window(self.log_callback)
        time.sleep(1.0)
        
        self.log_callback("[GLXH] Bắt đầu Auto GLXH...")
        
        try:
            while self._is_running:
                current_screen = capture_screen()
                
                # 1. Tìm nút Giả Lập XH
                coords = find_image_box("assets/glxh.png", confidence=0.8, screen_img=current_screen)
                if not coords:
                    coords = find_image_box("assets/glxh2.png", confidence=0.8, screen_img=current_screen)
                if coords:
                    x, y, w, h = coords
                    cx, cy = x + w // 2, y + h // 2
                    self.log_callback(f"[Debug-GLXH] Đã tìm thấy 'Giả Lập XH'. Tọa độ hộp: x={x}, y={y}, w={w}, h={h}")

                    safe_click(cx, cy, log_callback=self.log_callback)
                    self.log_callback("► Đã bấm Giả Lập Xếp Hạng")
                    time.sleep(1.0)
                    continue
                    
                if not self._is_running: break
                
                # 2. Xếp hạng (btnRank.png)
                coords = find_image_box("assets/btnRank.png", confidence=0.8, screen_img=current_screen)
                if coords:
                    x, y, w, h = coords
                    cx, cy = x + w // 2, y + h // 2
                    self.log_callback(f"[Debug-GLXH] Đã tìm thấy 'Xếp hạng'. Tọa độ hộp: x={x}, y={y}, w={w}, h={h}")

                    safe_click(cx, cy, log_callback=self.log_callback)
                    self.log_callback("► Đã bấm Xếp Hạng")
                    time.sleep(1.0)
                    continue
                    
                if not self._is_running: break
                
                # 3. Tiếp tục (continueButton.png)
                coords = find_image_box("assets/continueButton.png", confidence=0.8, screen_img=current_screen)
                if coords:
                    x, y, w, h = coords
                    cx, cy = x + w // 2, y + h // 2
                    self.log_callback(f"[Debug-GLXH] Đã tìm thấy 'Tiếp tục'. Tọa độ hộp: x={x}, y={y}, w={w}, h={h}")

                    safe_click(cx, cy, log_callback=self.log_callback)
                    self.log_callback("► Đã bấm Tiếp tục")
                    time.sleep(1.0)
                    continue
                    
                if not self._is_running: break
                
                # 4. Chọn (btnSelect.png)
                coords = find_image_box("assets/btnSelect.png", confidence=0.8, screen_img=current_screen)
                if coords:
                    x, y, w, h = coords
                    cx, cy = x + w // 2, y + h // 2
                    self.log_callback(f"[Debug-GLXH] Đã tìm thấy 'Chọn'. Tọa độ hộp: x={x}, y={y}, w={w}, h={h}")
                    self.log_callback(f"[Debug-GLXH] Vẽ hộp đỏ tại {x},{y},{w},{h}")

                    safe_click(cx, cy, log_callback=self.log_callback)
                    self.log_callback("► Đã bấm Chọn")
                    time.sleep(1.0)
                    continue
                    
                if not self._is_running: break
                
                # 5. Trong trận, tìm nút Bỏ qua (skipTemp / skipTemp2 / skipTemp3)
                if find_image("assets/skipTemp.png", confidence=0.8, screen_img=current_screen) or find_image("assets/skipTemp2.png", confidence=0.8, screen_img=current_screen):
                    self.log_callback("► Phát hiện nút Bỏ qua, đang nhấn SPACE...")
                    pyautogui.press('space')
                    time.sleep(1.0)
                    continue
                elif find_image("assets/skipTemp3.png", confidence=0.8, screen_img=current_screen):
                    self.log_callback("► Phát hiện nút Bỏ qua (ảnh 3), đang nhấn ESC...")
                    pyautogui.press('esc')
                    time.sleep(1.0)
                    continue
                    
                time.sleep(0.5)
        except Exception as e:
            self.log_callback(f"[Lỗi vòng lặp GLXH]: Do -> {e}")
        finally:
            self._is_running = False
            self.log_callback("[GLXH] ĐÃ DỪNG AUTO GLXH.")
