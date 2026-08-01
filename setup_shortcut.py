"""
One-time setup: creates the Desktop shortcut pointing to launch_gui.py.
Run this script once: python setup_shortcut.py
"""
import sys
import os
import subprocess
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent  # pdf-table-flattener folder
PYTHONW  = Path(sys.executable).parent / "pythonw.exe"
LAUNCHER = THIS_DIR / "launch_gui.py"
DESKTOP  = THIS_DIR.parent                 # Máy tính folder (the Desktop)
LNK_FILE = DESKTOP / "PDF Table Flattener.lnk"

# Build PowerShell script as Python strings (no unicode escaping issues)
ps_lines = [
    "$WshShell = New-Object -ComObject WScript.Shell",
    f'$s = $WshShell.CreateShortcut("{LNK_FILE}")',
    f'$s.TargetPath = "{PYTHONW}"',
    f'$s.Arguments = "`"{LAUNCHER}`""',
    f'$s.WorkingDirectory = "{THIS_DIR}"',
    '$s.Description = "PDF Table Flattener"',
    "$s.Save()",
    'Write-Host "Shortcut saved."',
]
ps_script = "\n".join(ps_lines)

# Write to a temp ps1 file (ASCII path, no Vietnamese)
tmp_ps1 = THIS_DIR / "tmp_mk_shortcut.ps1"
tmp_ps1.write_text(ps_script, encoding="utf-8")

print(f"Launcher   : {LAUNCHER}")
print(f"pythonw    : {PYTHONW}  (exists={PYTHONW.exists()})")
print(f"Shortcut   : {LNK_FILE}")
print(f"Working dir: {THIS_DIR}")

result = subprocess.run(
    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(tmp_ps1)],
    capture_output=True, text=True
)
tmp_ps1.unlink(missing_ok=True)

print(result.stdout)
if result.returncode != 0:
    print("PowerShell error:", result.stderr)
else:
    print("Done! Double-click 'PDF Table Flattener.lnk' on Desktop to launch the GUI.")
