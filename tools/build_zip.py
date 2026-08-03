"""Build the distributable archive: `python tools/build_zip.py`.

Produces `dist/PDF-Table-Flattener-<version>.zip`, which is the whole
deliverable -- unzip it anywhere on Windows, macOS or Linux and double-click the
matching START file.

Two details make or break the result:

* **Executable bits.** A zip built by most tools loses them, and macOS then
  refuses to run START_macOS.command at all. The Unix permission bits live in
  the high 16 bits of `external_attr`, so they are written explicitly here.
* **What stays out.** `.venv`, caches and the developer's own test documents are
  machine-specific or private; shipping them would at best bloat the archive and
  at worst leak someone's files.
"""

import os
import stat
import sys
import zipfile
from pathlib import Path
from typing import Iterator, List

APP_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = APP_ROOT / "dist"
APP_NAME = "PDF-Table-Flattener"

# Whole directories that never ship.
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".idea",
    ".vscode",
    "dist",
    "output_flattened",
    "input test",
    "node_modules",
}

EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip", ".log"}

# Named files that are development notes or one-off outputs, not part of the app.
EXCLUDED_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "output_loc_phat_trang_an.pdf",
    "create_desktop_shortcut.py",
    "setup_shortcut.py",
    "setup_shortcut_v2.py",
}

# The design write-ups are useful in the repo and only confusing in a package
# handed to someone who just wants to flatten a PDF.
EXCLUDED_GLOBS = ["solution*.md", "intergation.md", "test.md"]

# Anything a POSIX machine must be allowed to execute after unzipping.
EXECUTABLE_SUFFIXES = {".sh", ".command"}


def version() -> str:
    text = (APP_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip().startswith("version"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "0.0.0"


def excluded(path: Path) -> bool:
    relative = path.relative_to(APP_ROOT)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return True
    if path.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    return any(path.match(pattern) for pattern in EXCLUDED_GLOBS)


def files_to_ship() -> Iterator[Path]:
    for root, dirnames, filenames in os.walk(APP_ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in sorted(filenames):
            path = Path(root) / name
            if not excluded(path):
                yield path


def add(archive: zipfile.ZipFile, path: Path, arcname: str) -> None:
    info = zipfile.ZipInfo.from_file(path, arcname)
    info.compress_type = zipfile.ZIP_DEFLATED
    mode = 0o755 if path.suffix.lower() in EXECUTABLE_SUFFIXES else 0o644
    # High 16 bits of external_attr carry the Unix mode; without this a macOS
    # user gets "Permission denied" on the launcher they were told to click.
    info.external_attr = (stat.S_IFREG | mode) << 16
    archive.writestr(info, path.read_bytes())


def main() -> int:
    missing = [
        name
        for name in (
            "START_Windows.bat",
            "START_macOS.command",
            "START_Linux.sh",
            "HUONG_DAN.txt",
            "requirements.txt",
            "tools/bootstrap.py",
            "tools/posix_launch.sh",
            "tools/setup_llm.py",
        )
        if not (APP_ROOT / name).exists()
    ]
    if missing:
        print("Thiếu file bắt buộc: " + ", ".join(missing), file=sys.stderr)
        return 1

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = DIST_DIR / f"{APP_NAME}-{version()}.zip"
    top = f"{APP_NAME}"

    shipped: List[str] = []
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files_to_ship():
            arcname = f"{top}/{path.relative_to(APP_ROOT).as_posix()}"
            add(archive, path, arcname)
            shipped.append(arcname)

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"Đã đóng gói {len(shipped)} file -> {archive_path} ({size_mb:.2f} MB)")
    print("\nGửi file .zip này cho người khác. Họ chỉ cần:")
    print("  1. Giải nén")
    print("  2. Nháy đúp START_Windows.bat / START_macOS.command / START_Linux.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
