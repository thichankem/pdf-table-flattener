"""Create a Windows desktop shortcut that opens the GUI.

Run once:  python create_desktop_shortcut.py

Only Windows needs this.  macOS users double-click ``START_macOS.command``, and
``START_Linux.sh`` installs its own application-menu entry on first run.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover - odd stream
        pass

PROJECT_ROOT = Path(__file__).parent.resolve()
GUI_SCRIPT = PROJECT_ROOT / "launch_gui.py"
SHORTCUT_NAME = "PDF Table Flattener.lnk"


def _find_pythonw() -> Path:
    """Prefer the project's own .venv.

    That is the only interpreter guaranteed to have the dependencies installed;
    a shortcut pointing at a system or Anaconda interpreter starts and dies
    silently under pythonw.exe, with no window to show the traceback.
    """
    candidates = [
        PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe",
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        Path(sys.executable).parent / "pythonw.exe",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def _desktop_dirs() -> list[Path]:
    """Every folder Windows might currently be using as the desktop.

    The desktop is not always ``~/Desktop``: OneDrive redirects it, and it is
    then named in the user's own language.  The registry holds the real path,
    so it is asked first and the usual locations are only a fallback.
    """
    found: list[Path] = []
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        )
        with key:
            raw, _ = winreg.QueryValueEx(key, "Desktop")
        found.append(Path(os.path.expandvars(raw)))
    except (ImportError, OSError):
        pass

    home = Path.home()
    found += [home / "Desktop", home / "OneDrive" / "Desktop"]
    return list({p.resolve() for p in found if p.is_dir()})


def _create_lnk(lnk_path: Path, pythonw: Path) -> None:
    """Create one .lnk via WScript.Shell.

    Two Windows encoding traps are worked around here:

    1. The script is handed to PowerShell as a UTF-8-with-BOM *file* rather than
       a -Command string; a command line goes through the console code page.
    2. WScript.Shell.Save() is ANSI-based, so it cannot write to a path holding
       characters outside the system code page.  It therefore saves under an
       ASCII name, and Python -- which is fully Unicode -- does the rename.
    """
    tmp_lnk = lnk_path.with_name("_new_shortcut.lnk")
    script = (
        f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{tmp_lnk}')\n"
        f"$s.TargetPath='{pythonw}'\n"
        f"$s.Arguments='\"{GUI_SCRIPT}\"'\n"
        f"$s.WorkingDirectory='{PROJECT_ROOT}'\n"
        f"$s.Description='PDF Table Flattener'\n"
        f"$s.Save()\n"
    )
    with tempfile.NamedTemporaryFile(
        "w", suffix=".ps1", encoding="utf-8-sig", delete=False
    ) as fh:
        fh.write(script)
        ps1 = fh.name
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1],
            check=True,
        )
    finally:
        os.unlink(ps1)

    if not tmp_lnk.exists():
        raise RuntimeError(f"PowerShell did not produce {tmp_lnk}")
    os.replace(tmp_lnk, lnk_path)


def main() -> int:
    if not sys.platform.startswith("win"):
        print("This script only does anything on Windows.")
        return 1

    pythonw = _find_pythonw()
    desktops = _desktop_dirs()
    if not desktops:
        print("Could not locate the desktop folder.")
        return 1

    failures = 0
    for desktop in desktops:
        lnk_path = desktop / SHORTCUT_NAME
        try:
            _create_lnk(lnk_path, pythonw)
            print(f"Created shortcut: {lnk_path}")
        except Exception as exc:
            failures += 1
            print(f"Could not create {lnk_path}: {exc}")
    return 1 if failures == len(desktops) else 0


if __name__ == "__main__":
    sys.exit(main())
