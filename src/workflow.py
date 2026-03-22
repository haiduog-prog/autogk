import threading
import time
import ctypes
import pyautogui
from .vision_core import wait_for_image, click_image, find_image, find_image_box, draw_red_box_on_screen, safe_click, capture_screen

def focus_game_window(log_callback=print):
    """Tìm và đưa cửa sổ game FC Online lên trên cùng (focus)."""
    EnumWindows = ctypes.windll.user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    GetWindowText = ctypes.windll.user32.GetWindowTextW
    GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible
    SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow
    ShowWindow = ctypes.windll.user32.ShowWindow

    found = [False]

    def foreach_window(hwnd, lParam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                GetWindowText(hwnd, buff, length + 1)
                title = buff.value.upper()
                if "FC ONLINE" in title or "FIFA ONLINE" in title or "EA SPORTS" in title:
                    ShowWindow(hwnd, 9)  # SW_RESTORE
                    SetForegroundWindow(hwnd)
                    found[0] = True
                    return False  # Stop enumerating
        return True

    EnumWindows(EnumWindowsProc(foreach_window), 0)
    
    if found[0]:
        log_callback("[System] Đã focus vào cửa sổ game FC Online.")
    else:
        log_callback("[System] Không tìm thấy cửa sổ game FC Online! Vui lòng bật game.")

class AutomationWorkflow(threading.Thread):
    """
    Quản lý luồng kịch bản Ép thẻ (Upgrade) cho FC Online.
    Chạy đa luồng (Thread) để không làm block Main UI Loop của Tkinter.
    """
    def __init__(self, target_level: int = 5, log_callback=None):
        super().__init__()
        self.daemon = True # Thread tự kill khi App thoát
        self._is_running = False
        self.target_level = target_level
        self.log_callback = log_callback if log_callback else print

    def stop(self):
        """Hạ cờ is_running để dừng vòng lặp an toàn."""
        self._is_running = False
        self.log_callback("[System] Đang gửi lệnh Dừng. Vui lòng đợi hoàn tất chu kỳ lệnh...")

    def run(self):
        """Kịch bản Nâng Cấp Thẻ FC Online"""
        self._is_running = True
        
        # Focus game window
        focus_game_window(self.log_callback)
        time.sleep(1.0) # Đợi 1 chút để màn hình game hiện ra
        
        self.log_callback(f"[Khởi động] Bắt đầu Nâng Cấp Thẻ. Mục tiêu: Cấp +{self.target_level}")
        
        try:
            while self._is_running:
                # 1. Chờ vạch nguyên liệu đầy (fullPersentUpgrade.png)
                self.log_callback("1. Đang đợi thanh nguyên liệu đầy tỉ lệ (fullPersentUpgrade.png)...")
                # timeout ngắn để check Stop Event mỗi vòng
                coords = wait_for_image("assets/fullPersentUpgrade.png", timeout=3, confidence=0.8)
                if not coords:
                    continue # Bỏ qua, tiếp tục đợi
                    
                if not self._is_running: break
                
                # Nút 'Tiếp theo'
                self.log_callback("► Đã lấp đầy tỷ lệ. Bấm [Tiếp theo]")
                click_image("assets/continueButton.png", confidence=0.8, delay=1.0)
                if not self._is_running: break
                
                # Nút 'Tiến hành'
                self.log_callback("► Bấm [Tiến hành]")
                click_image("assets/processButton.png", confidence=0.8, delay=1.0)
                if not self._is_running: break
                
                # Nút 'Nâng cấp'
                self.log_callback("► Bấm Xác nhận (upgradeButton)")
                click_image("assets/upgradeButton.png", confidence=0.8, delay=3.0) 
                if not self._is_running: break
                
                # Kiểm tra kết quả
                self.log_callback("2. Đợi kết quả nâng cấp (sucessUpgrade.png)...")
                success = wait_for_image("assets/sucessUpgrade.png", timeout=12, confidence=0.8)
                if success:
                    self.log_callback("[Thành Công] Quá trình nâng cấp thành công!")
                    # Bổ sung thao tác check mốc thẻ hiện tại sau thành công
                    if find_image("assets/cardLevel.png", confidence=0.8):
                        self.log_callback("Đã xác nhận thẻ nâng thành công tại khung chi tiết (cardLevel.png).")
                else:
                    self.log_callback("[Thất Bại / Quá hạn] Không thấy thẻ nâng thành công. (Chờ update code chọn nguyên liệu)")
                    
                if not self._is_running: break

                # Bấm 'afterUpgrade.png'
                self.log_callback("► Bấm [Kế tiếp / Xong] sau khi đập thẻ")
                click_image("assets/afterUpgrade.png", confidence=0.8, delay=2.0)
                if not self._is_running: break
                
                # Khảo sát mức thẻ ở màn hình chính
                self.log_callback(f"3. Kiểm tra mục tiêu: +{self.target_level} tại màn hình chính...")
                # Gợi ý user để tên file theo định dạnh level 
                target_img = f"assets/homeCardLevel_{self.target_level}.png"
                fallback_img = "assets/homeCardLevel.png"
                
                if find_image(target_img, confidence=0.8):
                    self.log_callback(f"[Hoàn Thành Mục Tiêu] Đã đạt thẻ +{self.target_level}! Dừng Auto.")
                    break
                elif find_image(fallback_img, confidence=0.8):
                    # Nếu user chỉ dùng 1 file chung chung "homeCardLevel.png" thì đành ngắt để user kiểm tra
                    self.log_callback(f"► Đã tìm thấy {fallback_img}. Vui lòng tự kiểm tra Level thực tế.")
                    self.log_callback("Tạm dừng Auto để đảm bảo an toàn.")
                    break
                else:
                    self.log_callback(f"Chưa đạt đích. Tiếp tục vòng lặp mới sau 2 giây...")
                    time.sleep(2)
                
        except Exception as e:
            self.log_callback(f"[Lỗi vòng lặp Auto]: Ngắt kịch bản do -> {e}")
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
                    draw_red_box_on_screen(x, y, w, h, duration=0.3)
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
                    draw_red_box_on_screen(x, y, w, h, duration=0.3)
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
                    draw_red_box_on_screen(x, y, w, h, duration=0.3)
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
                    draw_red_box_on_screen(x, y, w, h, duration=0.3)
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
