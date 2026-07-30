import os
import sys
import win32com.client

def create_shortcut():
    desktop = r"C:\Users\ADMIN\OneDrive\Máy tính"
    shortcut_path = os.path.join(desktop, "ChuyenDoiBangWord.lnk")

    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    work_dir = os.path.abspath(os.path.dirname(__file__))
    gui_script = os.path.join(work_dir, "gui_app.py")

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.TargetPath = pythonw
    shortcut.Arguments = f'-X utf8 "{gui_script}"'
    shortcut.WorkingDirectory = work_dir
    shortcut.WindowStyle = 1
    shortcut.Description = "Công cụ chuyển đổi Bảng Word sang Text"
    shortcut.save()

    print(f"Đã tạo Shortcut Windows (.lnk) tại: {shortcut_path}")

if __name__ == "__main__":
    create_shortcut()
