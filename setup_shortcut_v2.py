"""
Creates the Desktop shortcut using Windows 8.3 short paths to avoid Unicode issues.
Run once: python setup_shortcut_v2.py
"""
import ctypes
import subprocess
import sys
from pathlib import Path

def get_short_path(long_path: str) -> str:
    buf = ctypes.create_unicode_buffer(32767)
    ret = ctypes.windll.kernel32.GetShortPathNameW(str(long_path), buf, 32767)
    return buf.value if ret else long_path

PROJ_LONG   = r"C:\Users\ADMIN\OneDrive\Máy tính\pdf-table-flattener"
DESK_LONG   = r"C:\Users\ADMIN\OneDrive\Máy tính"
PYTHONW     = str(Path(sys.executable).parent / "pythonw.exe")

PROJ_SHORT  = get_short_path(PROJ_LONG)
DESK_SHORT  = get_short_path(DESK_LONG)
PYTW_SHORT  = get_short_path(PYTHONW)

LAUNCHER    = PROJ_SHORT + r"\launch_gui.py"
LNK_FILE    = DESK_SHORT + r"\PDF Table Flattener.lnk"

print(f"proj short : {PROJ_SHORT}")
print(f"desk short : {DESK_SHORT}")
print(f"pythonw    : {PYTW_SHORT}")
print(f"launcher   : {LAUNCHER}")
print(f"lnk        : {LNK_FILE}")

# Build PS1 with only ASCII paths
ps_script = f"""$WshShell = New-Object -ComObject WScript.Shell
$s = $WshShell.CreateShortcut("{LNK_FILE}")
$s.TargetPath = "{PYTW_SHORT}"
$s.Arguments = "`"{LAUNCHER}`""
$s.WorkingDirectory = "{PROJ_SHORT}"
$s.Description = "PDF Table Flattener"
$s.Save()
Write-Host "Shortcut saved: {LNK_FILE}"
"""

tmp_ps1 = Path(r"C:\Users\ADMIN\tmp_mk_lnk.ps1")
tmp_ps1.write_text(ps_script, encoding="utf-8")

result = subprocess.run(
    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(tmp_ps1)],
    capture_output=True, text=True
)
tmp_ps1.unlink(missing_ok=True)

print("stdout:", result.stdout.strip())
if result.returncode != 0:
    print("FAILED stderr:", result.stderr.strip())
    sys.exit(1)
else:
    print("\nShortcut created! Double-click 'PDF Table Flattener.lnk' on Desktop.")
