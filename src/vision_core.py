import time
import pyautogui
import cv2
import numpy as np
import ctypes
from ctypes import wintypes

_TEMPLATE_CACHE = {}

# Cache layout UI để không tái tính Canny Edge mỗi lần gọi
# Key: (w, h, ox, oy) kích thước + vị trí client area. Value: dict chứa các biến layout
_LAYOUT_CACHE = {}

def invalidate_layout_cache():
    """Xóa cache layout — gọi khi game resize hoặc bắt đầu vòng lặp mới."""
    global _LAYOUT_CACHE
    _LAYOUT_CACHE.clear()

def get_fc_window_rect():
    """Tìm và trả về toạ độ Screen Coordinate (left, top, width, height) của vùng Client (Bỏ viền) Game FC Online."""
    user32 = ctypes.windll.user32
    target_hwnd = 0
    
    def foreach_window(hwnd, lParam):
        nonlocal target_hwnd
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.upper()
                if "FC ONLINE" in title or "FIFA ONLINE" in title or "EA SPORTS" in title:
                    client_rect = wintypes.RECT()
                    user32.GetClientRect(hwnd, ctypes.byref(client_rect))
                    w, h = client_rect.right - client_rect.left, client_rect.bottom - client_rect.top
                    if w > 100 and h > 100:  # Đảm bảo cửa sổ không phải launcher ẩn (size 0)
                        target_hwnd = hwnd
                        return False
        return True
        
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    user32.EnumWindows(EnumWindowsProc(foreach_window), 0)
    
    if target_hwnd:
        # Lấy kích thước Client thực sự (Lọc bỏ viền Border, Tiêu đề cửa sổ Windows)
        client_rect = wintypes.RECT()
        user32.GetClientRect(target_hwnd, ctypes.byref(client_rect))
        
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            
        pt_lt = POINT(client_rect.left, client_rect.top)
        pt_rb = POINT(client_rect.right, client_rect.bottom)
        
        # Chuyển toạ độ Client về toạ độ Màn hình thực (Desktop)
        user32.ClientToScreen(target_hwnd, ctypes.byref(pt_lt))
        user32.ClientToScreen(target_hwnd, ctypes.byref(pt_rb))
        
        # Trả về: Lề Trái, Lề Trên, Chiều Rộng, Chiều Cao
        return (pt_lt.x, pt_lt.y, pt_rb.x - pt_lt.x, pt_rb.y - pt_lt.y)
    return None

def capture_screen(scale_percent: int = 100) -> np.ndarray:
    """
    Chụp ảnh màn hình đúng khu vực của FC Online (Kể cả khi chạy Chế độ Cửa Sổ nhỏ).
    """
    rect = get_fc_window_rect()
    if rect and rect[2] > 0 and rect[3] > 0:
        screenshot = pyautogui.screenshot(region=rect)
    else:
        # Fallback nếu không tìm thấy cửa sổ game
        screenshot = pyautogui.screenshot()
        
    screen_img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    
    if scale_percent < 100:
        width = int(screen_img.shape[1] * scale_percent / 100)
        height = int(screen_img.shape[0] * scale_percent / 100)
        screen_img = cv2.resize(screen_img, (width, height), interpolation=cv2.INTER_AREA)
        
    return screen_img

def find_image(image_path: str, confidence: float = 0.8, scale_percent: int = 100, screen_img: np.ndarray = None) -> tuple[int, int] | None:
    try:
        if screen_img is None:
            screen_img = capture_screen(scale_percent)
            
        cache_key = f"{image_path}_{scale_percent}"
        if cache_key not in _TEMPLATE_CACHE:
            raw_img = cv2.imread(image_path, cv2.IMREAD_COLOR)
            if raw_img is None:
                raise FileNotFoundError(f"Không tìm thấy file ảnh mẫu tại: {image_path}")
            orig_h, orig_w = raw_img.shape[:2]
            if scale_percent < 100:
                t_width = max(1, int(orig_w * scale_percent / 100))
                t_height = max(1, int(orig_h * scale_percent / 100))
                template_img = cv2.resize(raw_img, (t_width, t_height), interpolation=cv2.INTER_AREA)
            else:
                template_img = raw_img
            _TEMPLATE_CACHE[cache_key] = (template_img, orig_w, orig_h)
            
        template_img, orig_w, orig_h = _TEMPLATE_CACHE[cache_key]
        
        if template_img.shape[0] > screen_img.shape[0] or template_img.shape[1] > screen_img.shape[1]:
            t_height = min(template_img.shape[0], screen_img.shape[0])
            t_width = min(template_img.shape[1], screen_img.shape[1])
            template_img = cv2.resize(template_img, (t_width, t_height), interpolation=cv2.INTER_AREA)
        
        result = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        
        if max_val >= confidence:
            center_x_scaled = max_loc[0] + template_img.shape[1] // 2
            center_y_scaled = max_loc[1] + template_img.shape[0] // 2
            
            real_x = int(center_x_scaled * (100 / scale_percent))
            real_y = int(center_y_scaled * (100 / scale_percent))
            
            # Cộng bù toạ độ toạ độ cửa sổ để trả về GLOBAL Screen Coordinates cho chuột ấn
            rect = get_fc_window_rect()
            if rect:
                real_x += rect[0]
                real_y += rect[1]
                
            return (real_x, real_y)
            
        return None
    except Exception as e:
        print(f"[Vision Core Error - find_image]: {e}")
        return None

def find_image_box(image_path: str, confidence: float = 0.8, scale_percent: int = 100, screen_img: np.ndarray = None) -> tuple[int, int, int, int] | None:
    try:
        if screen_img is None:
            screen_img = capture_screen(scale_percent)
            
        cache_key = f"{image_path}_{scale_percent}"
        if cache_key not in _TEMPLATE_CACHE:
            raw_img = cv2.imread(image_path, cv2.IMREAD_COLOR)
            if raw_img is None:
                return None
            orig_h, orig_w = raw_img.shape[:2]
            if scale_percent < 100:
                t_width = max(1, int(orig_w * scale_percent / 100))
                t_height = max(1, int(orig_h * scale_percent / 100))
                template_img = cv2.resize(raw_img, (t_width, t_height), interpolation=cv2.INTER_AREA)
            else:
                template_img = raw_img
            _TEMPLATE_CACHE[cache_key] = (template_img, orig_w, orig_h)
            
        template_img, orig_w, orig_h = _TEMPLATE_CACHE[cache_key]
        
        if template_img.shape[0] > screen_img.shape[0] or template_img.shape[1] > screen_img.shape[1]:
            t_height = min(template_img.shape[0], screen_img.shape[0])
            t_width = min(template_img.shape[1], screen_img.shape[1])
            template_img = cv2.resize(template_img, (t_width, t_height), interpolation=cv2.INTER_AREA)
        
        result = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        
        if max_val >= confidence:
            top_left_x_scaled = max_loc[0]
            top_left_y_scaled = max_loc[1]
            
            real_x = int(top_left_x_scaled * (100 / scale_percent))
            real_y = int(top_left_y_scaled * (100 / scale_percent))
            
            rect = get_fc_window_rect()
            if rect:
                real_x += rect[0]
                real_y += rect[1]
                
            return (real_x, real_y, orig_w, orig_h)
            
        return None
    except Exception as e:
        print(f"[Vision Core Error - find_image_box]: {e}")
        return None

def find_numbers_in_range(min_val: int, max_val: int, confidence: float = 0.85, scale_percent: int = 100, region: tuple = None) -> list:
    try:
        screen_img = capture_screen(scale_percent)
        screen_gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
        _, screen_bin = cv2.threshold(screen_gray, 150, 255, cv2.THRESH_BINARY)
        
        # Bù trừ toạ độ nếu region truyền vào thuộc về Global Screen Coordinates
        rect_offset = get_fc_window_rect()
        ox, oy = 0, 0
        if rect_offset:
            ox, oy = rect_offset[0], rect_offset[1]
            if region is not None:
                # Chuyển Screen Region về Window Region để cắt ảnh con xử lý
                rx1, ry1, rx2, ry2 = region
                region = (rx1 - ox, ry1 - oy, rx2 - ox, ry2 - oy)

        digits = []
        for i in range(10):
            img_path = f"assets/num{i}.png"
            template_img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
            if template_img is None:
                continue
                
            if scale_percent < 100:
                t_width = max(1, int(template_img.shape[1] * scale_percent / 100))
                t_height = max(1, int(template_img.shape[0] * scale_percent / 100))
                template_img = cv2.resize(template_img, (t_width, t_height), interpolation=cv2.INTER_AREA)
                
            _, template_bin = cv2.threshold(template_img, 150, 255, cv2.THRESH_BINARY)
            
            if template_bin.shape[0] > screen_bin.shape[0] or template_bin.shape[1] > screen_bin.shape[1]:
                t_height = min(template_bin.shape[0], screen_bin.shape[0])
                t_width = min(template_bin.shape[1], screen_bin.shape[1])
                template_bin = cv2.resize(template_bin, (t_width, t_height), interpolation=cv2.INTER_AREA)
                
            result = cv2.matchTemplate(screen_bin, template_bin, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= confidence)
            
            orig_h, orig_w = cv2.imread(img_path, cv2.IMREAD_COLOR).shape[:2]
            
            for pt in zip(*locations[::-1]):
                score = float(result[pt[1], pt[0]])
                x_scaled, y_scaled = int(pt[0]), int(pt[1])
                local_x = int(x_scaled * (100 / scale_percent))
                local_y = int(y_scaled * (100 / scale_percent))
                
                if region is not None:
                    rx1, ry1, rx2, ry2 = region
                    if not (rx1 <= local_x <= rx2 and ry1 <= local_y <= ry2):
                        continue
                
                digits.append({
                    'val': i, 'local_x': local_x, 'local_y': local_y, 'w': orig_w, 'h': orig_h, 'score': score
                })

        if not digits:
            return []
            
        digits.sort(key=lambda d: d['score'], reverse=True)
        nms_digits = []
        for d in digits:
            overlap = False
            for nd in nms_digits:
                x_left = max(d['local_x'], nd['local_x'])
                y_top = max(d['local_y'], nd['local_y'])
                x_right = min(d['local_x'] + d['w'], nd['local_x'] + nd['w'])
                y_bottom = min(d['local_y'] + d['h'], nd['local_y'] + nd['h'])
                if x_right > x_left and y_bottom > y_top:
                    inter_area = (x_right - x_left) * (y_bottom - y_top)
                    if inter_area > 0.6 * min(d['w'] * d['h'], nd['w'] * nd['h']):
                        overlap = True
                        break
            if not overlap:
                nms_digits.append(d)
                
        nms_digits.sort(key=lambda d: d['local_x'])
        numbers = []
        for d in nms_digits:
            added = False
            for grp in numbers:
                last_d = grp[-1]
                if abs(d['local_y'] - last_d['local_y']) <= max(d['h'], last_d['h']) * 1.5:
                    x_diff = d['local_x'] - last_d['local_x']
                    if 2 <= x_diff <= max(last_d['w'] * 2.5, 60):
                        grp.append(d)
                        added = True
                        break
            if not added:
                numbers.append([d])
            
        valid_boxes = []
        for grp in numbers:
            if len(grp) > 3:
                grp = grp[:3]
                
            num_str = "".join(str(d['val']) for d in grp)
            num_val_found = int(num_str)
            
            if min_val <= num_val_found <= max_val:
                min_x = min(d['local_x'] for d in grp)
                min_y = min(d['local_y'] for d in grp)
                max_x = max(d['local_x'] + d['w'] for d in grp)
                max_y = max(d['local_y'] + d['h'] for d in grp)
                
                # Biến toạ độ nội bộ Object Game thành Global Screen Coordinate cho pydirectinput click
                real_x = min_x + ox
                real_y = min_y + oy
                valid_boxes.append({'box': (real_x, real_y, max_x - min_x, max_y - min_y), 'val': num_val_found})
                
        return valid_boxes
    except Exception as e:
        print(f"[Vision Core Error - find_numbers_in_range]: {e}")
        return []

def draw_red_box_on_screen(x: int, y: int, w: int, h: int, duration: float = 0.3):
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    hdc = user32.GetWindowDC(0)
    hPen = gdi32.CreatePen(0, 3, 0x0000FF)
    hOldPen = gdi32.SelectObject(hdc, hPen)
    hNullBrush = gdi32.GetStockObject(5)
    hOldBrush = gdi32.SelectObject(hdc, hNullBrush)
    
    end_time = time.time() + duration
    while time.time() < end_time:
        gdi32.Rectangle(hdc, x, y, x + w, y + h)
        time.sleep(0.01)
        
    gdi32.SelectObject(hdc, hOldBrush)
    gdi32.SelectObject(hdc, hOldPen)
    gdi32.DeleteObject(hPen)
    user32.ReleaseDC(0, hdc)


def draw_boxes_batch(boxes: list, duration: float = 3.0, color: int = 0x00FFFF):
    """
    Vẽ nhiều box cùng lúc trên màn hình trong 1 thread (non-blocking).

    Args:
        boxes: list of dict {"x", "y", "w", "h"} hoặc list of tuple (x, y, w, h)
        duration: thời gian hiển thị (giây)
        color: màu GDI (BGR hex). Mặc định vàng 0x00FFFF
    """
    import threading

    def _draw():
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        hdc = user32.GetWindowDC(0)
        hPen = gdi32.CreatePen(0, 3, color)
        hOldPen = gdi32.SelectObject(hdc, hPen)
        hNullBrush = gdi32.GetStockObject(5)
        hOldBrush = gdi32.SelectObject(hdc, hNullBrush)

        end_time = time.time() + duration
        while time.time() < end_time:
            for b in boxes:
                if isinstance(b, dict):
                    bx, by, bw, bh = b["x"], b["y"], b["w"], b["h"]
                else:
                    bx, by, bw, bh = b
                gdi32.Rectangle(hdc, bx, by, bx + bw, by + bh)
            time.sleep(0.02)

        gdi32.SelectObject(hdc, hOldBrush)
        gdi32.SelectObject(hdc, hOldPen)
        gdi32.DeleteObject(hPen)
        user32.ReleaseDC(0, hdc)

    t = threading.Thread(target=_draw, daemon=True)
    t.start()

def safe_click(x: int, y: int, log_callback=None):
    if log_callback: log_callback(f"[Vision Core] Click chuột vật lý vào {x}, {y}")
    else: print(f"[Vision Core] Click chuột vật lý vào {x}, {y}")
    
    import pydirectinput
    import ctypes
    import time
    
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    orig_pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(orig_pt))
    
    pydirectinput.click(x, y)
    time.sleep(0.01)
    ctypes.windll.user32.SetCursorPos(orig_pt.x, orig_pt.y)

def safe_scroll(amount: int, x: int, y: int, log_callback=None):
    """Cuộn chuột tại vị trí (x, y). Dùng pydirectinput để di chuột (tương thích game DirectX)."""
    import pydirectinput

    # Di chuột bằng pydirectinput (giống safe_click đã hoạt động)
    pydirectinput.moveTo(x, y)
    time.sleep(0.3)

    # Dùng pyautogui.scroll tại vị trí hiện tại của chuột
    # amount là số notch (âm = xuống, dương = lên)
    pyautogui.scroll(amount)

    if log_callback:
        log_callback(f"[Scroll] pyautogui.scroll({amount}) tại ({x}, {y})")
    time.sleep(0.05)

def click_image(image_path: str, confidence: float = 0.8, delay: float = 0.5, scale_percent: int = 100) -> bool:
    coords = find_image_box(image_path, confidence, scale_percent)
    if coords is not None:
        try:
            x, y, w, h = coords
            cx, cy = x + w // 2, y + h // 2
            safe_click(cx, cy, log_callback=print)
            time.sleep(delay)
            return True
        except Exception as e:
            return False
    else:
        return False

def wait_for_image(image_path: str, timeout: int = 10, confidence: float = 0.8, scale_percent: int = 100) -> tuple[int, int] | None:
    start_time = time.time()
    while (time.time() - start_time) < timeout:
        coords = find_image(image_path, confidence, scale_percent)
        if coords is not None:
            return coords
        time.sleep(0.5) 
    return None

def parse_upgrade_screen(screen_img=None, debug_draw=False):
    if screen_img is None:
        screen_img = capture_screen(scale_percent=100)

    rect_offset = get_fc_window_rect()
    ox, oy = 0, 0
    lw, lh = screen_img.shape[1], screen_img.shape[0]
    if rect_offset:
        ox, oy = rect_offset[0], rect_offset[1]
        lw, lh = rect_offset[2], rect_offset[3]

    # ---- Các box dùng LOGICAL coordinates ----
    main_player_box = {
        "x": ox + int(lw * 0.161),
        "y": oy + int(lh * 0.134),
        "w": int(lw * 0.286),
        "h": int(lh * 0.278)
    }
    
    percent_bar_box = {
        "x": ox + int(lw * 0.161),
        "y": oy + int(lh * 0.647),
        "w": int(lw * 0.286),
        "h": int(lh * 0.036)
    }

    buttons_area = {
        "x": ox + int(lw * 0.480),
        "y": oy + int(lh * 0.866),
        "w": int(lw * 0.356),
        "h": int(lh * 0.040)
    }

    # 3 nút riêng biệt trong buttons_area
    btn_y = oy + int(lh * 0.866)
    btn_h = int(lh * 0.040)

    btn_protect = {
        "name": "Bảo vệ nâng cấp",
        "x": ox + int(lw * 0.481),
        "y": btn_y,
        "w": int(lw * 0.101),
        "h": btn_h
    }
    btn_reset = {
        "name": "N.Cấp lại",
        "x": ox + int(lw * 0.596),
        "y": btn_y,
        "w": int(lw * 0.081),
        "h": btn_h
    }
    btn_next = {
        "name": "Tiếp theo",
        "x": ox + int(lw * 0.732),
        "y": btn_y,
        "w": int(lw * 0.096),
        "h": btn_h
    }

    # Tỷ lệ CỐ ĐỊNH chuẩn xác (kéo từ bản gốc đã test kĩ với client area)
    start_x = ox + int(lw * 0.466)
    start_w = int(lw * 0.374)
    header_top = int(lh * 0.2638)
    # Calibrated via image projection: exact list_top and pitch 
    list_top = int(lh * 0.2885)
    header_h = list_top - header_top
    cell_h = lh * 0.0554
    top_y = oy + list_top
    print(f"[parse_upgrade_screen] Fit Ratio: header_y={header_top} list_top={list_top} cell_h={cell_h:.1f}")

    # Khung tiêu đề header riêng (dòng "Tăng | Vị Trí | Tên cầu thủ | OVR | Thẻ | Khóa | Giá")
    materials_header_box = {
        "x": start_x,
        "y": oy + header_top,
        "w": start_w,
        "h": int(header_h)
    }

    materials_list = []
    for row_index in range(10):
        y_pos = top_y + int(row_index * cell_h)
        # Các cột: OVR nằm ở khoảng ~64.5% - 70.5% màn hình
        ovr_x = ox + int(lw * 0.645)
        # Thu nhỏ chiều rộng chỉ để chứa mỗi số OVR (loại bỏ vùng ghi cấp thẻ)
        ovr_w = int(lw * 0.035)
        
        # Giảm chiều cao box đi 5% để tạo khe hở giữa các dòng phôi
        box_h = int(cell_h * 0.95)
        
        # Tập trung vào vùng chứa text (nằm ở giữa theo trục Y)
        ovr_y = y_pos + int(box_h * 0.25)
        ovr_h = int(box_h * 0.5)
        
        item_box = {
            "id": row_index + 1,
            "x": start_x,
            "y": y_pos,
            "w": start_w,
            "h": box_h,
            "ovr_box": {
                "x": ovr_x,
                "y": ovr_y,
                "w": ovr_w,
                "h": ovr_h
            }
        }
        materials_list.append(item_box)

    ui_scan_result = {
        "main_player": main_player_box,
        "percent_bar": percent_bar_box,
        "action_buttons": buttons_area,
        "btn_protect": btn_protect,
        "btn_reset": btn_reset,
        "btn_next": btn_next,
        "materials_header": materials_header_box,
        "materials_items": materials_list,
        "ovr_column_box": {
            # Shifted left from 0.645 to 0.615 to accurately hit OVR numbers, bypassing the Level Badges completely.
            "x": ox + int(lw * 0.615),
            "y": oy + list_top - int(lh * 0.01),
            "w": int(lw * 0.035),
            "h": int(lh * 0.60)
        },
        "window_rect": (ox, oy, lw, lh)
    }
    
    return ui_scan_result

def is_upgrade_bar_full(screen_img=None, ui_data=None):
    if screen_img is None:
        screen_img = capture_screen(scale_percent=100)
    if ui_data is None:
        ui_data = parse_upgrade_screen(screen_img)
        
    bar = ui_data["percent_bar"]
    
    # ui_data chứa màn hình thực (Global Screen), nhưng để cắt ảnh từ screen_img (Window/Client size) 
    # Ta phải trừ ngược lại kích thước offset
    rect_offset = get_fc_window_rect()
    ox, oy = 0, 0
    if rect_offset: 
        ox, oy = rect_offset[0], rect_offset[1]
    
    bar_client_x = bar["x"] - ox
    bar_client_y = bar["y"] - oy
    
    slot5_x = int(bar_client_x + bar["w"] * 0.82)
    slot5_w = int(bar["w"] * 0.18)
    
    region = screen_img[bar_client_y:bar_client_y+bar["h"], slot5_x:slot5_x+slot5_w]
    if region.size == 0: return False
    
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([40, 100, 100]), np.array([80, 255, 255]))
    green_pixels = cv2.countNonZero(mask)
    total_pixels = region.shape[0] * region.shape[1]
    
    return (green_pixels / total_pixels) > 0.15

def click_dynamic_continue_button():
    ui_data = parse_upgrade_screen()
    btns = ui_data["action_buttons"]
    cx = int(btns["x"] + btns["w"] * 0.85)
    cy = int(btns["y"] + btns["h"] * 0.5)
    safe_click(cx, cy, log_callback=None)

def check_upgrade_success_ocr(screen_img=None, debug_draw=False) -> bool:
    """Cropping the bottom area of the result screen to find 'nâng cấp thành công'"""
    if screen_img is None:
        screen_img = capture_screen(scale_percent=100)
    
    rect_offset = get_fc_window_rect()
    lh = rect_offset[3] if rect_offset else screen_img.shape[0]
    lw = rect_offset[2] if rect_offset else screen_img.shape[1]
    oy = rect_offset[1] if rect_offset else 0
    ox = rect_offset[0] if rect_offset else 0

    # Crop vùng bottom text (Y từ 70% -> 95%) để tăng tốc OCR cực độ
    y_start = oy + int(lh * 0.70)
    y_end = oy + int(lh * 0.95)
    x_start = ox + int(lw * 0.2)
    x_end = ox + int(lw * 0.8)

    crop_img = screen_img[y_start:y_end, x_start:x_end]
    from .ocr import read_text
    
    # Preprocess=False vì chữ "Nâng cấp thành công" màu trắng, rất to và rõ ràng
    results = read_text(crop_img, preprocess=False)
    for res in results:
        text_lower = str(res["text"]).lower()
        if "thành công" in text_lower or "thanh cong" in text_lower or "nâng cấp" in text_lower or "nang cap" in text_lower:
            return True
            
    return False

def wait_for_upgrade_result_ocr(timeout: int = 15, log_callback=None) -> bool:
    """Vòng lặp OCR chờ màn hình kết quả nâng cấp xuất hiện"""
    import time
    start_time = time.time()
    while time.time() - start_time < timeout:
        screen_img = capture_screen(scale_percent=100)
        if check_upgrade_success_ocr(screen_img):
            return True
        time.sleep(0.5)
    return False

def detect_card_level_result_screen(screen_img=None, log_callback=None) -> int | None:
    """Sử dụng OCR quét trực tiếp vào ô chứa Cấp thẻ góc dưới cùng bên trái màn hình."""
    if screen_img is None:
        screen_img = capture_screen(scale_percent=100)
        
    rect_offset = get_fc_window_rect()
    lh = rect_offset[3] if rect_offset else screen_img.shape[0]
    lw = rect_offset[2] if rect_offset else screen_img.shape[1]
    oy = rect_offset[1] if rect_offset else 0
    ox = rect_offset[0] if rect_offset else 0

    # Tọa độ vùng Cấp thẻ (theo hình khoanh mũi tên góc Bottom Left)
    y_start = oy + int(lh * 0.90)
    y_end = oy + int(lh * 0.99)
    x_start = ox + int(lw * 0.12)
    x_end = ox + int(lw * 0.19)
    
    crop_img = screen_img[y_start:y_end, x_start:x_end]
    from .ocr import read_text
    
    # Preprocess=True vì số level nằm trong ô nhỏ, cần upscale
    results = read_text(crop_img, preprocess=True)
    
    if log_callback:
        texts = [res["text"] for res in results]
        log_callback(f"[Debug] Lỗ hổng OCR góc trái đọc được: {texts}")

    import re
    best_level = None
    
    # Ưu tiên duyệt mảng OCR từ trái -> phải, trên -> dưới
    for res in results:
        text = str(res["text"]).strip()
        
        # Bỏ qua những từ khóa mồi hiển nhiên hoặc các số liệu hiển phụ trợ bắt đầu bằng dấu +
        if text.startswith("+") or "thẻ" in text.lower() or "cấp" in text.lower():
            continue
            
        # Tìm chính xác con số cô lập nguyên vẹn đứng một mình 
        # (Ví dụ: "2" -> match 2. "Z2" -> bỏ qua)
        nums = re.findall(r'\b(?:1[0-5]|[1-9])\b', text)
        for n in nums:
            val = int(n)
            if 1 <= val <= 13: # Cấp độ game hiện tại Max 10, dự phòng 13
                best_level = val
                break
        
        # Nếu đã tìm ra 1 gốc Level khả dĩ nhất ở vị trí đầu tiên, khoá kết quả luôn để tránh đọc nhầm sang dòng khác (như +1, +2..)
        if best_level is not None:
            break
            
    if best_level is not None and log_callback:
        log_callback(f"[Nhận Diện OCR] Đã nạy được mốc thẻ: +{best_level}")
        
    return best_level
