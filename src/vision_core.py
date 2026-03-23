import time
import pyautogui
import cv2
import numpy as np

_TEMPLATE_CACHE = {}

def capture_screen(scale_percent: int = 100) -> np.ndarray:
    """
    Chụp ảnh màn hình và chuyển sang chuẩn BGR của OpenCV.
    Có thể nén (giảm kích thước và độ phân giải) thông qua scale_percent 
    giúp hàm matchTemplate chạy với ít lượng pixel hơn, giảm thiểu áp lực CPU.
    """
    screenshot = pyautogui.screenshot()
    screen_img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    
    if scale_percent < 100:
        width = int(screen_img.shape[1] * scale_percent / 100)
        height = int(screen_img.shape[0] * scale_percent / 100)
        # INTER_AREA là giải thuật tối ưu nhất khi muốn thu nhỏ ảnh mà không gãy viền
        screen_img = cv2.resize(screen_img, (width, height), interpolation=cv2.INTER_AREA)
        
    return screen_img

def find_image(image_path: str, confidence: float = 0.8, scale_percent: int = 100, screen_img: np.ndarray = None) -> tuple[int, int] | None:
    """Tìm kiếm hình mẫu trên màn hình, hỗ trợ screen_img sẵn có và lưu cache."""
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
        
        result = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        
        if max_val >= confidence:
            center_x_scaled = max_loc[0] + template_img.shape[1] // 2
            center_y_scaled = max_loc[1] + template_img.shape[0] // 2
            
            real_x = int(center_x_scaled * (100 / scale_percent))
            real_y = int(center_y_scaled * (100 / scale_percent))
            
            return (real_x, real_y)
            
        return None
    except Exception as e:
        print(f"[Vision Core Error - find_image]: {e}")
        return None

def find_image_box(image_path: str, confidence: float = 0.8, scale_percent: int = 100, screen_img: np.ndarray = None) -> tuple[int, int, int, int] | None:
    """Trả về (x, y, w, h) của ảnh tìm thấy trên màn hình. Hỗ trợ truyền sẵn ảnh màn hình và lưu cache RAM."""
    try:
        if screen_img is None:
            screen_img = capture_screen(scale_percent)
            
        # Nạp Cache cho template để tránh đọc ổ cứng 5 lần/giây
        cache_key = f"{image_path}_{scale_percent}"
        if cache_key not in _TEMPLATE_CACHE:
            raw_img = cv2.imread(image_path, cv2.IMREAD_COLOR)
            if raw_img is None:
                print(f"[Vision Core Error]: Không tìm thấy file ảnh mẫu tại {image_path}")
                return None
            
            orig_h, orig_w = raw_img.shape[:2]
            
            if scale_percent < 100:
                t_width = max(1, int(orig_w * scale_percent / 100))
                t_height = max(1, int(orig_h * scale_percent / 100))
                template_img = cv2.resize(raw_img, (t_width, t_height), interpolation=cv2.INTER_AREA)
            else:
                template_img = raw_img
                
            _TEMPLATE_CACHE[cache_key] = (template_img, orig_w, orig_h)
            
        # Khôi phục từ Cache (0ms)
        template_img, orig_w, orig_h = _TEMPLATE_CACHE[cache_key]
        
        result = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        
        if max_val >= confidence:
            top_left_x_scaled = max_loc[0]
            top_left_y_scaled = max_loc[1]
            
            real_x = int(top_left_x_scaled * (100 / scale_percent))
            real_y = int(top_left_y_scaled * (100 / scale_percent))
            
            return (real_x, real_y, orig_w, orig_h)
            
        return None
    except Exception as e:
        print(f"[Vision Core Error - find_image_box]: {e}")
        return None

def find_numbers_in_range(min_val: int, max_val: int, confidence: float = 0.85, scale_percent: int = 100, region: tuple = None) -> list:
    """
    Quét qua các file ảnh num0.png -> num9.png trên màn hình.
    Gom các chữ số gần nhau thành một số hoàn chỉnh.
    Nếu số nằm trong khoảng [min_val, max_val], trả về bounding boxes của các số đó: danh sách (x, y, w, h).
    Khung 'region' (x1, y1, x2, y2) để giới hạn tìm kiếm.
    """
    try:
        screen_img = capture_screen(scale_percent)
        # Tối ưu hóa: Chuyển ảnh màn hình sang Grayscale và Nhị phân hoá (Đen/Trắng)
        # Giúp loại bỏ hoàn toàn nhiễu từ các sọc nền xen kẽ (màu xám đậm/nhạt) của FC Online
        screen_gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
        _, screen_bin = cv2.threshold(screen_gray, 150, 255, cv2.THRESH_BINARY)
        
        digits = []
        for i in range(10):
            img_path = f"assets/num{i}.png"
            # Đọc ảnh số mẫu dưới dạng Grayscale
            template_img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
            if template_img is None:
                continue
                
            if scale_percent < 100:
                t_width = max(1, int(template_img.shape[1] * scale_percent / 100))
                t_height = max(1, int(template_img.shape[0] * scale_percent / 100))
                template_img = cv2.resize(template_img, (t_width, t_height), interpolation=cv2.INTER_AREA)
                
            # Nhị phân hoá ảnh mẫu để đồng bộ pixel hoàn toàn với hệ thống screen_bin
            _, template_bin = cv2.threshold(template_img, 150, 255, cv2.THRESH_BINARY)
                
            result = cv2.matchTemplate(screen_bin, template_bin, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= confidence)
            
            orig_h, orig_w = cv2.imread(img_path, cv2.IMREAD_COLOR).shape[:2]
            
            # Lọc bằng NMS và loại trừ số ngoài region focus
            for pt in zip(*locations[::-1]):
                score = float(result[pt[1], pt[0]])
                x_scaled, y_scaled = int(pt[0]), int(pt[1])
                real_x = int(x_scaled * (100 / scale_percent))
                real_y = int(y_scaled * (100 / scale_percent))
                
                # Bỏ qua nếu nằm ngoài vùng focus (nếu được cấp region)
                if region is not None:
                    rx1, ry1, rx2, ry2 = region
                    if not (rx1 <= real_x <= rx2 and ry1 <= real_y <= ry2):
                        continue
                
                digits.append({
                    'val': i, 'x': real_x, 'y': real_y, 'w': orig_w, 'h': orig_h, 'score': score
                })

        if not digits:
            return []
            
        # NMS (Non-Maximum Suppression) để chọn lọc ứng viên sáng giá nhất, loại bỏ trùng lặp khu vực
        digits.sort(key=lambda d: d['score'], reverse=True)
        nms_digits = []
        for d in digits:
            overlap = False
            for nd in nms_digits:
                x_left = max(d['x'], nd['x'])
                y_top = max(d['y'], nd['y'])
                x_right = min(d['x'] + d['w'], nd['x'] + nd['w'])
                y_bottom = min(d['y'] + d['h'], nd['y'] + nd['h'])
                if x_right > x_left and y_bottom > y_top:
                    inter_area = (x_right - x_left) * (y_bottom - y_top)
                    # Thay vì 0.1 (quá gắt), để 0.6 vòng tránh xoá nhầm 2 số đứng sát nhau chặn bounding box
                    if inter_area > 0.6 * min(d['w'] * d['h'], nd['w'] * nd['h']):
                        overlap = True
                        break
            if not overlap:
                nms_digits.append(d)
                
        # Gom ngang thành số OVR
        nms_digits.sort(key=lambda d: d['x'])
        
        numbers = []
        for d in nms_digits:
            added = False
            for grp in numbers:
                last_d = grp[-1]
                # Nới lỏng y và tính x_diff trực tiếp để không phụ thuộc vào w (tránh lỗi width của số 1 quá nhỏ/to)
                if abs(d['y'] - last_d['y']) <= max(d['h'], last_d['h']) * 1.5:
                    x_diff = d['x'] - last_d['x']
                    # Ở FC Online chữ số thường cách nhau dứt khoát 5 -> 50px
                    if 2 <= x_diff <= max(last_d['w'] * 2.5, 60):
                        grp.append(d)
                        added = True
                        break
            if not added:
                numbers.append([d])
            
        valid_boxes = []
        for grp in numbers:
            # Giới hạn tối đa 3 chữ số để không bị lẹm sang số Level củng hàng ngang nếu lỡ quét dính
            if len(grp) > 3:
                grp = grp[:3]
                
            num_str = "".join(str(d['val']) for d in grp)
            num_val_found = int(num_str)
            print(f"[Vision Core] Nhận diện OVR Group: {num_str} (tại y={grp[0]['y']}, x={grp[0]['x']})")
            
            if min_val <= num_val_found <= max_val:
                min_x = min(d['x'] for d in grp)
                min_y = min(d['y'] for d in grp)
                max_x = max(d['x'] + d['w'] for d in grp)
                max_y = max(d['y'] + d['h'] for d in grp)
                valid_boxes.append({'box': (min_x, min_y, max_x - min_x, max_y - min_y), 'val': num_val_found})
                
        return valid_boxes
        
    except Exception as e:
        print(f"[Vision Core Error - find_numbers_in_range]: {e}")
        return []

def draw_red_box_on_screen(x: int, y: int, w: int, h: int, duration: float = 0.3):
    """Vẽ một khung màu đỏ bao quanh vùng tìm thấy trực tiếp lên màn hình."""
    import ctypes
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

def safe_click(x: int, y: int, log_callback=None):
    """
    Gửi thông điệp Click ngầm (Background Click) bằng PostMessage.
    Không chiếm chuột phần cứng, cho phép người dùng lướt web làm việc khác.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
            
    import ctypes
    user32 = ctypes.windll.user32
    
    # 1. Tìm cửa sổ FC Online
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
                    target_hwnd = hwnd
                    return False
        return True
    
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    user32.EnumWindows(EnumWindowsProc(foreach_window), 0)
    
    if not target_hwnd:
        log("[Debug-Click] Không tìm thấy cửa sổ FC Online để gửi lệnh ngầm!")
        return
        
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT(x, y)
    user32.ScreenToClient(target_hwnd, ctypes.byref(pt))
    client_x, client_y = pt.x, pt.y
    
    log(f"[Debug-Click] Bắn tọa độ ngầm: Screen({x}, {y}) -> Client({client_x}, {client_y})")
    
    lparam = (client_y << 16) | (client_x & 0xFFFF)
    WM_MOUSEMOVE = 0x0200
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    MK_LBUTTON = 0x0001
    
    user32.PostMessageW(target_hwnd, WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.05)
    user32.PostMessageW(target_hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
    time.sleep(0.05)
    user32.PostMessageW(target_hwnd, WM_LBUTTONUP, 0, lparam)
    
    log("[Debug-Click] --- Đã gửi Click Ngầm thành công ---")

def safe_scroll(amount: int, x: int, y: int, log_callback=None):
    """
    Cuộn chuột ngầm (Background Scroll) không chiếm dụng trỏ chuột vật lý.
    amount: > 0 cuộn lên, < 0 cuộn xuống
    x, y: tọa độ điểm nhấn trên mục cần cuộn (Screen coords).
    """
    import ctypes
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
                    target_hwnd = hwnd
                    return False
        return True
    
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    user32.EnumWindows(EnumWindowsProc(foreach_window), 0)
    
    if not target_hwnd:
        return
        
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT(x, y)
    user32.ScreenToClient(target_hwnd, ctypes.byref(pt))
    client_x, client_y = pt.x, pt.y
    
    # Định vị tọa độ ngầm (lParam movement requires Client Coordinates)
    lparam_move = ((client_y & 0xFFFF) << 16) | (client_x & 0xFFFF)
    user32.PostMessageW(target_hwnd, 0x0200, 0, lparam_move)
    time.sleep(0.05)
    
    # Cuộn ngầm (lParam WM_MOUSEWHEEL requires Screen Coordinates)
    lparam_scroll = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
    wparam_scroll = ((amount & 0xFFFF) << 16) | 0
    
    # Có thể cần phái lặp nhiều lần WM_MOUSEWHEEL cho mượt nếu amount lớn
    # vì hệ điều hành giới hạn 1 lần scroll ngắn
    step_delta = 120 if amount > 0 else -120
    times_to_scroll = max(1, abs(amount) // 120)
    
    wparam_step = ((step_delta & 0xFFFF) << 16) | 0
    for _ in range(times_to_scroll):
        user32.PostMessageW(target_hwnd, 0x020A, wparam_step, lparam_scroll)
        time.sleep(0.01)

def click_image(image_path: str, confidence: float = 0.8, delay: float = 0.5, scale_percent: int = 100) -> bool:
    """Tìm vị trí ảnh mẫu và tiến hành click chuột"""
    coords = find_image_box(image_path, confidence, scale_percent)
    if coords is not None:
        try:
            x, y, w, h = coords
            draw_red_box_on_screen(x, y, w, h, duration=0.3)
            cx, cy = x + w // 2, y + h // 2
            safe_click(cx, cy, log_callback=print)
            time.sleep(delay)
            return True
        except Exception as e:
            print(f"[Vision Core Error - click_image]: Thao tác chuột thất bại - {e}")
            return False
    else:
        raise Exception(f"Không tìm thấy hình mẫu '{image_path}' trên màn hình để click.")

def wait_for_image(image_path: str, timeout: int = 10, confidence: float = 0.8, scale_percent: int = 100) -> tuple[int, int] | None:
    """Vòng lặp chờ tối đa `timeout` giây cho đến khi ảnh xuất hiện."""
    start_time = time.time()
    while (time.time() - start_time) < timeout:
        coords = find_image(image_path, confidence, scale_percent)
        if coords is not None:
            return coords
        time.sleep(0.5) 
        
    return None
