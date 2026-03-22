import os
import sys
import tkinter as tk

# Thêm path dự án vào sys để tránh lỗi import tương đối/tuyệt đối khi đóng gói EXE
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.ui import AppUI

def main():
    """Entry point của Ứng dụng"""
    # Khởi tạo giao diện Tkinter cơ bản
    root = tk.Tk()
    
    # Init App (đưa instance Tkinter root vào app của chúng ta)
    app = AppUI(root)
    
    # Ví dụ set Icon (nếu tồn tại)
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico")
    if os.path.exists(icon_path):
        root.iconbitmap(icon_path)
        
    # Vòng lặp chính duy trì app không bị đóng
    root.mainloop()

if __name__ == "__main__":
    main()
