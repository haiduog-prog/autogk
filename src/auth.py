import platform
import subprocess

class KeyAuthenticator:
    """
    Xử lý logic kết nối xác thực KeyAuth để bảo vệ ứng dụng (License System).
    Bao gồm lấy HWID để Bind Key.
    """
    def __init__(self):
        # Đây là nơi map với tham số KeyAuth app
        self.name = "autogk"
        self.ownerid = "YOUR_OWNERID"
        self.secret = "YOUR_SECRET"
        self.version = "1.0"
        
    def _get_hwid(self) -> str:
        """
        Lấy UUID cơ bản của phần cứng theo hệ điều hành Windows.
        """
        if platform.system() == "Windows":
            try:
                hwid = subprocess.check_output('wmic csproduct get uuid').decode().split('\n')[1].strip()
                return hwid
            except Exception:
                return "UNKNOWN-HWID"
        return "NON-WINDOWS-HWID"

    def init_auth(self) -> bool:
        """
        Thiết lập kết nối với Server API của KeyAuth.
        """
        # Mock SDK initialization logic
        try:
            # (Giả lập Request)
            return True
        except Exception:
            return False

    def verify_key(self, license_key: str) -> tuple[bool, str]:
        """
        Gửi Key lên hệ thống với HWID để xác nhận quyền truy cập.
        
        Args:
            license_key (str): Mã key do người dùng nhập.
            
        Returns:
            tuple[bool, str]: (Thành công/Thất bại, Thông báo)
        """
        hwid = self._get_hwid()
        
        if not license_key:
            return False, "Vui lòng nhập License Key để tiếp tục."
            
        # [MOCK] Logic giả lập check Key
        if license_key in ["TRIALKEY", "VIPKEY"]:
            return True, "Kích hoạt thành công!"
            
        return False, "License Key đã hết hạn hoặc bị sai máy (HWID)!"
