import cv2
import numpy as np

img = cv2.imread(r"C:\Users\vthun\Desktop\autogk\assets\upgradeHomeContext.png")
if img is not None:
    # Get arbitrary dimensions
    h, w = img.shape[:2]
    # Crop the tabs area: "Cầu thủ đang sở hữu" | "Mua cầu thủ" | "Mua hàng loạt"
    # Looking at the original game layout, it's roughly:
    # X ~ 46% to 75%, Y ~ 12% to 20%
    x1 = int(w * 0.46)
    y1 = int(h * 0.12)
    x2 = int(w * 0.75)
    y2 = int(h * 0.20)
    
    crop = img[y1:y2, x1:x2]
    cv2.imwrite(r"C:\Users\vthun\Desktop\autogk\assets\upgrade_tabs.png", crop)
    print(f"Cropped to assets/upgrade_tabs.png with shape {crop.shape}")
else:
    print("Could not load image")
