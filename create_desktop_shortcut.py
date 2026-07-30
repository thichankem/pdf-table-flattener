import os
import sys
import win32com.client

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def create_desktop_shortcuts():
    shell = win32com.client.Dispatch("WScript.Shell")
    
    # Dynamically find Desktop directory
    desktop_folder = shell.SpecialFolders("Desktop")
    if not os.path.exists(desktop_folder):
        desktop_folder = os.path.join(os.path.expanduser("~"), "Desktop")
        
    print(f"Thư mục Desktop phát hiện: {desktop_folder}")
    
    work_dir = os.path.abspath(os.path.dirname(__file__))
    python_exe = sys.executable
    pythonw_exe = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
    gui_script = os.path.join(work_dir, "gui_app.py")
    bat_file = os.path.join(work_dir, "run.bat")
    
    # Update run.bat to use current python executable and working dir
    bat_content = f"""@echo off
chcp 65001 > nul
title Chuyen Doi Bang PDF/Word sang Text
cd /d "{work_dir}"
"{python_exe}" -X utf8 "{gui_script}"
"""
    with open(bat_file, "w", encoding="utf-8") as f:
        f.write(bat_content)
        
    print(f"Đã cập nhật run.bat chuẩn: {bat_file}")
    
    # Clean up any old broken shortcuts
    for old_name in ["ChuyenDoiBangWord.lnk", "ChuyenDoiBangPDF_Word.lnk", "ChuyenDoiBangPDF.lnk"]:
        old_lnk = os.path.join(desktop_folder, old_name)
        if os.path.exists(old_lnk):
            try:
                os.remove(old_lnk)
                print(f"Đã xóa icon shortcut cũ: {old_name}")
            except Exception:
                pass

    # Create clean Desktop shortcut
    lnk_name = "ChuyenDoiBangPDF_Word.lnk"
    lnk_path = os.path.join(desktop_folder, lnk_name)
    
    shortcut = shell.CreateShortCut(lnk_path)
    if os.path.exists(pythonw_exe):
        shortcut.TargetPath = pythonw_exe
        shortcut.Arguments = f'-X utf8 "{gui_script}"'
    else:
        shortcut.TargetPath = python_exe
        shortcut.Arguments = f'-X utf8 "{gui_script}"'
        
    shortcut.WorkingDirectory = work_dir
    shortcut.WindowStyle = 1
    shortcut.Description = "Cong cu chuyen doi Bang PDF/Word sang Text"
    
    icon_path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "shell32.dll")
    shortcut.IconLocation = f"{icon_path}, 70"
    shortcut.save()
    
    print(f"✅ Đã tạo thành công Icon Shortcut Desktop tại: {lnk_path}")

if __name__ == "__main__":
    create_desktop_shortcuts()
