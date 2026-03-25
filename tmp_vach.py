import os
import cv2
import glob

# Dùng đường dẫn tương đối để file test hoạt động ở mọi máy tính
base_dir = os.path.dirname(os.path.abspath(__file__))
asset_path = os.path.join(base_dir, 'assets', 'detectUpgradeScreen.png')
img = cv2.imread(asset_path)
import sys
if img is None: sys.exit(1)

templates = []
for i in range(6):
    t = cv2.imread(os.path.join(base_dir, 'assets', f'{i}vach.png'))
    templates.append(t)

# Try matching the first template over the whole image to find its location and confidence
for i, t in enumerate(templates):
    if t is None:
        print(f"Failed to load {i}vach.png")
        continue

    result = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    print(f"Template {i}vach: max_score = {max_val:.3f}, loc = {max_loc}")
