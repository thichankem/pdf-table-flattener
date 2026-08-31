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

for _stream in (sys.stdout, sys.stderr):
    try:  # a Windows console still defaults to cp1252, which cannot print this
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - odd stream
        pass

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

# The app ships no documents of its own, so any that are lying around a
# developer's checkout are their own sample files -- private by default, and
# the one thing that must never end up in an archive handed to someone else.
DOCUMENT_SUFFIXES = {".pdf", ".docx", ".doc", ".xlsx", ".xlsm", ".xls"}

# Named files that are development notes or one-off outputs, not part of the app.
EXCLUDED_NAMES = {
    ".DS_Store",
    "Thumbs.db",
}

# Developer-only files: useful in the repository, only confusing in a package
# handed to someone who just wants to flatten a PDF.
EXCLUDED_GLOBS = [".github/*", ".github/**/*"]

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
    suffix = path.suffix.lower()
    if path.name in EXCLUDED_NAMES or suffix in EXCLUDED_SUFFIXES:
        return True
    if suffix in DOCUMENT_SUFFIXES:
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
            "README.md",
            "requirements.txt",
            "tools/bootstrap.py",
            "tools/posix_launch.sh",
        )
        if not (APP_ROOT / name).exists()
    ]
    if missing:
        print("Required files are missing: " + ", ".join(missing), file=sys.stderr)
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
    print(f"Packaged {len(shipped)} files -> {archive_path} ({size_mb:.2f} MB)")
    print("\nSend this .zip to anyone. All they have to do is:")
    print("  1. Unzip it")
    print("  2. Double-click START_Windows.bat / START_macOS.command / START_Linux.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
