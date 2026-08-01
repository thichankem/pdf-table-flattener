import os
import sys
import subprocess
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.resolve()
GUI_SCRIPT = PROJECT_ROOT / "gui.py"
PYTHONW_EXE = Path(sys.executable).parent / "pythonw.exe"
if not PYTHONW_EXE.exists():
    PYTHONW_EXE = Path(sys.executable)

def setup_desktop_shortcut():
    desktop_paths = [
        Path("C:/Users/ADMIN/OneDrive/Máy tính"),
        Path("C:/Users/ADMIN/Desktop"),
        Path(os.path.expanduser("~/Desktop")),
        Path(os.path.expanduser("~/OneDrive/Máy tính")),
    ]

    valid_desktops = list({p.resolve() for p in desktop_paths if p.exists()})

    for desktop in valid_desktops:
        # 1. Remove old .bat files
        for bat_name in ["Làm Phẳng Bảng PDF.bat", "Lam_Phang_Bang_PDF.bat"]:
            bat_file = desktop / bat_name
            if bat_file.exists():
                try:
                    bat_file.unlink()
                    print(f"Removed bat file: {bat_file}")
                except Exception as e:
                    print(f"Could not remove bat file {bat_file}: {e}")

        # 2. Create clean Windows .lnk Shortcut
        for lnk_name in ["Làm Phẳng Bảng PDF.lnk", "PDF Table Flattener.lnk"]:
            lnk_path = desktop / lnk_name
            cmd = [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-Command",
                f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk_path}'); "
                f"$s.TargetPath='{PYTHONW_EXE}'; "
                f"$s.Arguments='\"{GUI_SCRIPT}\"'; "
                f"$s.WorkingDirectory='\"{PROJECT_ROOT}\"'; "
                f"$s.Description='Làm phẳng Bảng PDF'; "
                f"$s.Save()"
            ]
            try:
                subprocess.run(cmd, check=True)
                print(f"Successfully created Windows shortcut (.lnk): {lnk_path}")
            except Exception as e:
                print(f"Shortcut creation info ({lnk_path}): {e}")

if __name__ == "__main__":
    setup_desktop_shortcut()
