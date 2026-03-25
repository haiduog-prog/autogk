"""
src/ocr.py
──────────
Module OCR sử dụng EasyOCR để quét Text tiếng Việt và tiếng Anh trực tiếp từ
ảnh màn hình game FC Online mà không phụ thuộc template-matching ảnh tĩnh.

Các hàm chính:
    - init_reader()                      : Khởi tạo reader EasyOCR (lazy, chỉ 1 lần)
    - read_text(img_region)              : Trả về list các (text, confidence, bbox)
    - read_text_in_box(x, y, w, h)       : Chụp ảnh vùng rồi OCR
    - find_text(keyword, x, y, w, h)     : Tìm keyword, trả toạ độ trung tâm khi thấy
    - read_all_rows_text(ui_data)        : Đọc text của từng hàng phôi trong materials_items
"""

import cv2
import numpy as np
from typing import Optional

# Lazy-init: reader chỉ được tạo 1 lần duy nhất
_reader = None

# Cache kết quả OCR dạng hình ảnh để tăng tốc
_last_col_img = None
_last_ocr_rows = None

def init_reader():
    """
    Khởi tạo EasyOCR Reader với Vietnamese + English.
    Lần đầu chạy sẽ tải model (~100MB), các lần sau dùng ngay cache.
    """
    global _reader
    if _reader is None:
        try:
            import easyocr
            print("[OCR] Đang khởi tạo EasyOCR reader (vi + en)...")
            _reader = easyocr.Reader(["vi", "en"], gpu=False, verbose=False)
            print("[OCR] EasyOCR ready!")
        except ImportError:
            print("[OCR] Thiếu thư viện easyocr. Chạy: pip install easyocr")
            _reader = None
    return _reader


def _preprocess(img: np.ndarray) -> np.ndarray:
    """
    Tiền xử lý ảnh để tăng độ chính xác OCR:
    - Tăng kích thước 2x (giúp OCR đọc chữ nhỏ)
    - Sharpen + tăng tương phản
    """
    scale = 2
    h, w = img.shape[:2]
    img = cv2.resize(img, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
    # Sharpen kernel
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    img = cv2.filter2D(img, -1, kernel)
    return img


def read_text(img_region: np.ndarray, preprocess: bool = True) -> list[dict]:
    """
    OCR một ảnh numpy BGR.

    Args:
        img_region: Ảnh crop (numpy BGR array)
        preprocess: Có tiền xử lý ảnh không

    Returns:
        List[dict] dạng:
        [
            {"text": "Tiếp theo", "conf": 0.95, "bbox": (x1, y1, x2, y2)},
            ...
        ]
    """
    reader = init_reader()
    if reader is None:
        return []
    if img_region is None or img_region.size == 0:
        return []

    if preprocess:
        img_region = _preprocess(img_region)

    # EasyOCR nhận BGR hoặc grayscale
    try:
        results = reader.readtext(img_region, detail=1, paragraph=False)
    except Exception as e:
        print(f"[OCR Error] read_text: {e}")
        return []

    parsed = []
    for (bbox, text, conf) in results:
        # bbox là list 4 điểm [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        x1, y1, x2, y2 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
        parsed.append({"text": text.strip(), "conf": round(conf, 3), "bbox": (x1, y1, x2, y2)})

    return parsed


def read_text_in_box(x: int, y: int, w: int, h: int,
                     screen_img: Optional[np.ndarray] = None,
                     preprocess: bool = True) -> list[dict]:
    """
    Chụp ảnh vùng (x, y, w, h) trên màn hình rồi OCR.

    Args:
        x, y, w, h : Toạ độ TUYỆT ĐỐI trên màn hình (screen coordinate)
        screen_img  : Nếu đã có ảnh capture sẵn thì truyền vào để tránh chụp lại
        preprocess  : Có tiền xử lý không

    Returns:
        List[dict] giống read_text()
    """
    from .vision_core import capture_screen, get_fc_window_rect

    if screen_img is None:
        screen_img = capture_screen(scale_percent=100)

    rect = get_fc_window_rect()
    ox, oy = (rect[0], rect[1]) if rect else (0, 0)

    # Chuyển về toạ độ ảnh (không có window offset)
    lx1 = max(x - ox, 0)
    ly1 = max(y - oy, 0)
    lx2 = min(lx1 + w, screen_img.shape[1])
    ly2 = min(ly1 + h, screen_img.shape[0])

    crop = screen_img[ly1:ly2, lx1:lx2]
    if crop.size == 0:
        return []

    return read_text(crop, preprocess=preprocess)


def find_text(keyword: str,
              x: int, y: int, w: int, h: int,
              screen_img: Optional[np.ndarray] = None,
              conf_threshold: float = 0.5,
              case_sensitive: bool = False) -> Optional[tuple[int, int]]:
    """
    Tìm keyword trong vùng (x, y, w, h). Trả về toạ độ TUYỆT ĐỐI trung tâm
    của text khi tìm thấy, None nếu không thấy.

    Args:
        keyword        : Chuỗi cần tìm (ví dụ: "Tiếp theo", "Bảo vệ")
        x, y, w, h     : Vùng tìm kiếm — toạ độ màn hình tuyệt đối
        conf_threshold : Chỉ chấp nhận kết quả có confidence >= ngưỡng

    Returns:
        (cx, cy) toạ độ tuyệt đối trên màn hình, hoặc None
    """
    results = read_text_in_box(x, y, w, h, screen_img)
    kw = keyword if case_sensitive else keyword.lower()

    for item in results:
        text = item["text"] if case_sensitive else item["text"].lower()
        if kw in text and item["conf"] >= conf_threshold:
            # Toạ độ trong ảnh crop → chuyển về toạ độ màn hình
            bx1, by1, bx2, by2 = item["bbox"]
            # Scale ngược nếu đã resize 2x trong preprocess
            cx_crop = (bx1 + bx2) // (2 * 2)
            cy_crop = (by1 + by2) // (2 * 2)
            return (x + cx_crop, y + cy_crop)

    return None


def read_all_rows_text(ui_data: dict,
                       screen_img: Optional[np.ndarray] = None) -> list[dict]:
    """
    Đọc text của tất cả 10 hàng phôi trong materials_items.

    Args:
        ui_data    : Kết quả từ parse_upgrade_screen()
        screen_img : Ảnh capture (tránh chụp nhiều lần)

    Returns:
        List[dict] mỗi phần tử ứng với 1 hàng:
        {
            "row": 1,
            "x": ..., "y": ..., "w": ..., "h": ...,
            "texts": [{"text":..., "conf":..., "bbox":...}, ...]
        }
    """
    from .vision_core import capture_screen

    if screen_img is None:
        screen_img = capture_screen(scale_percent=100)

    rows = []
    for item in ui_data.get("materials_items", []):
        result = read_text_in_box(
            item["x"], item["y"], item["w"], item["h"],
            screen_img=screen_img
        )
        rows.append({
            "row": item["id"],
            "x": item["x"], "y": item["y"],
            "w": item["w"], "h": item["h"],
            "texts": result
        })

    return rows


def is_text_visible(keyword: str,
                    x: int, y: int, w: int, h: int,
                    screen_img: Optional[np.ndarray] = None,
                    conf_threshold: float = 0.5) -> bool:
    """
    Kiểm tra nhanh xem keyword có xuất hiện trong vùng không.

    Returns:
        True nếu thấy, False nếu không
    """
    return find_text(keyword, x, y, w, h, screen_img, conf_threshold) is not None


def count_upgrade_bars(screen_img: np.ndarray, dyn_item_box: dict, window_rect: tuple) -> int:
    """
    Đếm số vạch (Tăng) của một phôi bằng template matching.
    """
    # Load templates Vạch nếu chưa load
    global _vach_templates
    if '_vach_templates' not in globals():
        import os
        _vach_templates = []
        for i in range(6):
            p = os.path.join("assets", f"{i}vach.png")
            t = cv2.imread(p) if os.path.exists(p) else None
            _vach_templates.append(t)

    ox, oy, lw, lh = window_rect

    ix1 = max(dyn_item_box["x"] - ox, 0)
    iy1 = max(dyn_item_box["y"] - oy, 0)
    ix2 = min(ix1 + int(lw * 0.06), screen_img.shape[1])
    iy2 = min(iy1 + dyn_item_box["h"], screen_img.shape[0])
    
    vach_crop = screen_img[iy1:iy2, ix1:ix2]
    
    best_val = 0
    best_score = -1.0
    if vach_crop.size > 0:
        for i, t in enumerate(_vach_templates):
            if t is None: continue
            if t.shape[0] > vach_crop.shape[0] or t.shape[1] > vach_crop.shape[1]:
                try:
                    t = cv2.resize(t, (min(t.shape[1], vach_crop.shape[1]), min(t.shape[0], vach_crop.shape[0])))
                except: continue
                
            res = cv2.matchTemplate(vach_crop, t, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            if max_val > best_score:
                best_score = max_val
                best_val = i

    return best_val


def extract_ovr_from_rows(ui_data: dict,
                          screen_img: Optional[np.ndarray] = None,
                          debug_draw: bool = False) -> list[dict]:
    """
    OCR cột OVR của danh sách phôi — crop từng ô OVR riêng biệt theo row.

    Workflow:
        1. Xác định vùng cột OVR (tỷ lệ cố định theo chiều rộng cửa sổ)
        2. Với mỗi row trong materials_items, crop riêng ô OVR
        3. Tiền xử lý (upscale 3x, binary threshold) rồi OCR riêng từng ô
        4. Kết quả OCR tương ứng trực tiếp với row → không cần mapping Y

    Args:
        ui_data    : Kết quả từ parse_upgrade_screen()
        screen_img : Ảnh capture
        debug_draw : Vẽ khung vàng lên hàng OCR thành công

    Returns:
        List[dict]: [{"row": 1, "ovr": 111, "item_box": {...}, "center": (cx, cy)}, ...]
    """
    import re
    from .vision_core import capture_screen, get_fc_window_rect, draw_boxes_batch

    reader = init_reader()
    if reader is None:
        return []

    if screen_img is None:
        screen_img = capture_screen(scale_percent=100)

    rect = ui_data.get("window_rect")
    if rect:
        ox, oy, lw, lh = rect
    else:
        r = get_fc_window_rect()
        ox, oy = (r[0], r[1]) if r else (0, 0)
        lw = r[2] if r else screen_img.shape[1]
        lh = r[3] if r else screen_img.shape[0]

    items = ui_data.get("materials_items", [])
    ovr_col_box = ui_data.get("ovr_column_box")
    if not items or not ovr_col_box:
        return []

    # --- DYNAMIC OVR CALIBRATION ---
    # Tự động quét Header để lấy chính xác mốc X của chữ "OVR"
    materials_header = ui_data.get("materials_header")
    dynamic_ovr_x = None
    if materials_header:
        hx = max(materials_header["x"] - ox, 0)
        hy = max(materials_header["y"] - oy, 0)
        hw = materials_header["w"]
        hh = materials_header["h"]
        header_img = screen_img[hy:hy+hh, hx:hx+hw]
        
        if header_img.size > 0:
            h_c, w_c = header_img.shape[:2]
            header_big = cv2.resize(header_img, (w_c * 2, h_c * 2), interpolation=cv2.INTER_CUBIC)
            try:
                header_res = reader.readtext(header_big, detail=1, paragraph=False)
                print(f"[OCR-DEBUG] Header text blocks found: {len(header_res)}")
                for bbox, text, conf in header_res:
                    print(f"[OCR-DEBUG] text: '{text}', conf:{conf}")
                    if "OVR" in text.upper() and conf > 0.4:
                        cx_big = (bbox[0][0] + bbox[1][0]) / 2.0
                        cx_screen_img = hx + (cx_big / 2.0)
                        dynamic_ovr_x = int(cx_screen_img - (lw * 0.018))
                        print(f"[OCR] DYNAMIC OVR CALIBRATED: Header OVR cx={cx_screen_img:.1f}, adjusted box_x={dynamic_ovr_x}")
                        break
            except Exception as e:
                print(f"[OCR] Header scan error: {e}")

    if dynamic_ovr_x is not None:
        ovr_col_box["x"] = dynamic_ovr_x + ox
        ovr_col_box["w"] = int(lw * 0.026) # Thu hẹp lại để KHÔNG dính vào Thẻ (Level badge) bên phải OVR

    scale = 3
    print(f"[OCR] screen={screen_img.shape} rect=({ox},{oy},{lw},{lh}) column mode (x={ovr_col_box['x']}, w={ovr_col_box['w']})")

    cell_x1 = max(ovr_col_box["x"] - ox, 0)
    cell_y1 = max(ovr_col_box["y"] - oy, 0)
    cell_x2 = min(cell_x1 + ovr_col_box["w"], screen_img.shape[1])
    cell_y2 = min(cell_y1 + ovr_col_box["h"], screen_img.shape[0])
    
    col_img = screen_img[cell_y1:cell_y2, cell_x1:cell_x2]
    if col_img.size == 0:
        return []

    global _last_col_img, _last_ocr_rows
    if _last_col_img is not None and col_img.shape == _last_col_img.shape:
        # Check Mean Squared Error (MSE) siêu tốc
        mse = np.mean((col_img.astype(float) - _last_col_img.astype(float)) ** 2)
        if mse < 50.0:  # Ngưỡng chấp nhận noise nhỏ
            print(f"[OCR] CACHE HIT: Hình ảnh cột OVR không đổi (MSE={mse:.2f}), trả về kết quả quét trước đó!")
            return _last_ocr_rows
        else:
            print(f"[OCR] Danh sách đã thay đổi hoặc cuộn (MSE={mse:.2f}), tiến hành quét lại...")

    h_c, w_c = col_img.shape[:2]
    # Dùng ảnh BGR gốc upscaled thay vì mask nhị phân, EasyOCR giải mã text màu tự nhiên tốt hơn nhiều
    col_big = cv2.resize(col_img, (w_c * scale, h_c * scale), interpolation=cv2.INTER_CUBIC)

    # Thử OCR trực tiếp trên ảnh màu
    try:
        ocr_results = reader.readtext(col_big, detail=1, paragraph=False, allowlist='0123456789')
    except Exception as e:
        print(f"[OCR] Lỗi khi readtext: {e}")
        ocr_results = []

    # Filter kết quả OCR để gom những Bbox gần nhau (nếu OCR vô tình cắt đôi 1 dòng)
    found_numbers = []
    for (bbox, text, conf) in ocr_results:
        nums = re.findall(r'\d{2,3}', text)
        for n in nums:
            val = int(n)
            # Nới lỏng dải OVR vì phôi có thể từ 60 đến 130
            if 50 <= val <= 130 and conf > 0.4:
                cy_big = (bbox[0][1] + bbox[2][1]) / 2
                cy = (cy_big / scale) + cell_y1 + oy
                
                # Tránh lấy trùng lặp 2 số trên cùng 1 hàng (cách nhau < 20px)
                duplicate = False
                for fn in found_numbers:
                    if abs(fn["cy"] - cy) < 20: 
                        if conf > fn["conf"]: # Lấy số có độ tin cậy cao hơn
                            fn["ovr"] = val
                            fn["conf"] = conf
                        duplicate = True
                        break
                
                if not duplicate:
                    found_numbers.append({"ovr": val, "cy": cy, "conf": conf})
                break

    # Xếp hạng từ trên xuống dưới theo Y
    found_numbers.sort(key=lambda x: x["cy"])

    final_rows = []
    base_item = items[0]
    cell_h = lh * 0.0554
    box_h = int(cell_h * 0.95)
    
    # Lấy lùi list_top gốc lại
    list_top = ovr_col_box["y"] + int(lh * 0.01)
    row_1_center = list_top + cell_h / 2.0

    for fn in found_numbers:
        row_idx = round((fn["cy"] - row_1_center) / cell_h)
        if 0 <= row_idx < 10:
            # Tạo box động khớp tuyệt đối với Y thực tế
            true_y_pos = int(fn["cy"] - box_h * 0.5)
            
            dyn_item_box = {
                "id": row_idx + 1,
                "x": base_item["x"],
                "y": true_y_pos,
                "w": base_item["w"],
                "h": box_h
            }
            
            dyn_ovr_box = {
                "x": ovr_col_box["x"],
                "y": int(fn["cy"] - box_h * 0.25),
                "w": ovr_col_box["w"],
                "h": int(box_h * 0.5)
            }
            
            # --- TÍNH TOÁN SỐ VẠCH (TEMPLATE MATCHING) ---
            vach_val = count_upgrade_bars(screen_img, dyn_item_box, (ox, oy, lw, lh))

            print(f"[OCR] Tự động định vị: Row {row_idx + 1}, OVR={fn['ovr']}, Y center={fn['cy']:.1f}, Vạch={vach_val}")
            
            final_rows.append({
                "row": row_idx + 1,
                "ovr": fn["ovr"],
                "vach": vach_val,
                "item_box": dyn_item_box,
                "ovr_box": dyn_ovr_box,
                # Điểm click: tính từ tâm green box
                "center": (base_item["x"] + base_item["w"] // 2, int(fn["cy"]))
            })

    print(f"[OCR] Kết quả: {[(r['row'], r['ovr'], r['vach']) for r in final_rows]}")

    if debug_draw and screen_img is not None:
        debug_img = screen_img.copy()

        # Vẽ khung xanh quanh từng row động, vẽ khung vàng quanh OVR động
        for r in final_rows:
            ib = r["item_box"]
            iy1 = max(ib["y"] - oy, 0)
            iy2 = min(iy1 + ib["h"], debug_img.shape[0])
            ix1 = max(ib["x"] - ox, 0)
            ix2 = min(ix1 + ib["w"], debug_img.shape[1])
            cv2.rectangle(debug_img, (ix1, iy1), (ix2, iy2), (0, 255, 0), 2)
            
            ob = r["ovr_box"]
            oy1 = max(ob["y"] - oy, 0)
            oy2 = min(oy1 + ob["h"], debug_img.shape[0])
            ox1 = max(ob["x"] - ox, 0)
            ox2 = min(ox1 + ob["w"], debug_img.shape[1])
            
            cv2.rectangle(debug_img, (ox1, oy1), (ox2, oy2), (0, 255, 255), 2)

        cv2.imwrite('debug_positions.png', debug_img)
        print(f"[OCR] Đã lưu debug_positions.png với {len(final_rows)} bounding boxes")

    _last_col_img = col_img.copy()
    _last_ocr_rows = final_rows

    return final_rows
