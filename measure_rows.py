import cv2
import easyocr
import os

def find_ovr_x():
    files = [f for f in os.listdir("assets") if f.endswith(".png")]
    if not files: return
    latest = max([os.path.join("assets", f) for f in files], key=os.path.getmtime)
    print(f"Analyzing {latest}")
    img = cv2.imread(latest)
    if img is None: return

    reader = easyocr.Reader(['en'], gpu=False)
    # OCR the header area to find exact X of string 'OVR'
    # header is roughly top 30% of the image
    h, w = img.shape[:2]
    header = img[int(h*0.2):int(h*0.35), :]
    
    res = reader.readtext(header)
    for bbox, text, conf in res:
        if 'OVR' in text.upper():
            cx = (bbox[0][0] + bbox[1][0]) / 2
            print(f"Found {text} at X={cx}, Ratio={cx/w:.4f}")
            print(f"Bbox: X1={bbox[0][0]}, X2={bbox[1][0]}, Width={bbox[1][0]-bbox[0][0]}")

find_ovr_x()
