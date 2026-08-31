"""First-run setup, shared by the Windows, macOS and Linux launchers.

The launcher scripts only have to find *a* Python 3.10+; everything after that
happens here, so the three of them stay short and identical in behaviour.

What this does, in order:
  1. builds ``.venv`` next to the app if it is not there yet,
  2. installs the pinned dependencies into it,
  3. downloads the bundled Vietnamese-capable fonts (best effort),
  4. re-executes the requested entry point using the venv's interpreter.

Step 4 is why this file is written against the standard library only: it runs
under the *system* Python, before any dependency exists.  It is also why the
work is guarded by a stamp file -- the second and every later launch skips
straight to the app and needs no network at all.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional

def _force_utf8_console() -> None:
    """Stop a non-ASCII progress message from killing the installer.

    This module runs under whatever Python the machine already had, and on a
    Windows console that still means cp1252 -- where a plain ``print`` of an
    accented path raises UnicodeEncodeError before any real work happens.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover - odd stream
            pass


_force_utf8_console()

APP_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = APP_ROOT / ".venv"
STAMP = VENV_DIR / ".bootstrapped"
REQUIREMENTS = APP_ROOT / "requirements.txt"
FONTS_DIR = APP_ROOT / "assets" / "fonts"

MIN_PYTHON = (3, 10)

# Bundling the fonts makes non-Latin text render identically on all three
# systems instead of depending on whatever the machine happens to have.
# They are optional: config.py falls back to system fonts when absent.
# Static instances rather than the variable-font builds: PyMuPDF embeds a
# fixed weight, and a static file is what it handles predictably.
_NOTO = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf"
FONT_DOWNLOADS = {
    "NotoSans-Regular.ttf": f"{_NOTO}/NotoSans/NotoSans-Regular.ttf",
    "NotoSerif-Regular.ttf": f"{_NOTO}/NotoSerif/NotoSerif-Regular.ttf",
}


def log(message: str) -> None:
    print(f"  {message}", flush=True)


def step(message: str) -> None:
    print(f"\n==> {message}", flush=True)


# ─────────────────────────────────────────── venv ──────────────────────────────


def venv_python(venv: Path = VENV_DIR) -> Path:
    if sys.platform.startswith("win"):
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def venv_pythonw(venv: Path = VENV_DIR) -> Path:
    """The console-less interpreter, so a double-click shows no black window."""
    if sys.platform.startswith("win"):
        pythonw = venv / "Scripts" / "pythonw.exe"
        if pythonw.is_file():
            return pythonw
    return venv_python(venv)


def create_venv() -> None:
    step("Creating a private Python environment for the app (.venv)")
    if VENV_DIR.exists() and not venv_python().is_file():
        log("the existing environment is broken, rebuilding it")
        shutil.rmtree(VENV_DIR, ignore_errors=True)
    if venv_python().is_file():
        log("already present, skipping")
        return
    # --copies avoids symlinks, which break when the folder is moved or synced
    # through Drive/OneDrive -- exactly how this package gets passed around.
    subprocess.run(
        [sys.executable, "-m", "venv", "--copies", str(VENV_DIR)], check=True
    )
    log(f"created {VENV_DIR}")


def pip_install() -> None:
    step("Installing dependencies (first run only, needs Internet)")
    python = str(venv_python())
    subprocess.run(
        [python, "-m", "pip", "install", "--upgrade", "pip", "--quiet"], check=False
    )
    result = subprocess.run(
        [python, "-m", "pip", "install", "--quiet", "-r", str(REQUIREMENTS)]
    )
    if result.returncode != 0:
        raise SystemExit(
            "\nThe dependencies could not be installed. Check your Internet "
            "connection and try again.\n"
            f"To do it by hand:\n  \"{python}\" -m pip install -r \"{REQUIREMENTS}\"\n"
        )
    log("done")


# ─────────────────────────────────────────── fonts ─────────────────────────────


def fetch_fonts() -> None:
    step("Downloading the bundled Noto fonts")
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in FONT_DOWNLOADS.items():
        target = FONTS_DIR / name
        if target.is_file() and target.stat().st_size > 10_000:
            log(f"{name}: already present")
            continue
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
            if len(data) < 10_000:
                raise ValueError("file too small, the download is probably broken")
            target.write_bytes(data)
            log(f"{name}: downloaded ({len(data)//1024} KB)")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            # Not fatal: config.py will use a system font instead.
            log(f"{name}: skipped ({exc}) - a system font will be used instead")


# ─────────────────────────────────────────── run ───────────────────────────────


def already_bootstrapped() -> bool:
    if not STAMP.is_file() or not venv_python().is_file():
        return False
    try:
        stamp = json.loads(STAMP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    # Re-running setup after the requirements change is cheaper than shipping a
    # copy that silently runs against stale dependencies.
    return stamp.get("requirements") == _requirements_fingerprint()


def _requirements_fingerprint() -> str:
    import hashlib

    try:
        return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    except OSError:
        return ""


def write_stamp() -> None:
    STAMP.write_text(
        json.dumps(
            {
                "requirements": _requirements_fingerprint(),
                "python": sys.version,
                "platform": sys.platform,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def bootstrap() -> None:
    if already_bootstrapped():
        return
    if sys.version_info < MIN_PYTHON:
        raise SystemExit(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is required; "
            f"this machine is running {sys.version.split()[0]}."
        )
    print("=" * 68)
    print("  PDF Table Flattener - first-run setup")
    print("  This runs ONCE; later launches go straight to the app.")
    print("=" * 68)
    create_venv()
    pip_install()
    fetch_fonts()
    write_stamp()
    step("Setup complete.")


def launch(mode: str, extra: List[str]) -> int:
    """Hand control to the app, running under the venv's interpreter."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(APP_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"

    if mode == "gui":
        # pythonw keeps the console window from lingering behind the GUI.
        command = [str(venv_pythonw()), str(APP_ROOT / "launch_gui.py")]
        if sys.platform.startswith("win"):
            # Detached, so the launcher's console can close immediately.
            subprocess.Popen(command, cwd=str(APP_ROOT), env=env)
            return 0
    elif mode == "cli":
        command = [str(venv_python()), str(APP_ROOT / "cli.py"), *extra]
    elif mode == "test":
        command = [str(venv_python()), "-m", "pytest", *extra]
    else:  # "setup" -- bootstrap only, no app
        return 0

    return subprocess.run(command, cwd=str(APP_ROOT), env=env).returncode


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Install and launch the app.")
    parser.add_argument(
        "--mode",
        default="gui",
        choices=["gui", "cli", "test", "setup"],
        help="gui: open the interface | cli: command line | setup: install only",
    )
    parser.add_argument(
        "--force", action="store_true", help="Reinstall from scratch"
    )
    args, extra = parser.parse_known_args(argv)
    # `--mode cli -- -i file.pdf` is the natural way to pass through flags that
    # argparse would otherwise claim; the separator itself is not one of them.
    if extra and extra[0] == "--":
        extra = extra[1:]

    if args.force:
        STAMP.unlink(missing_ok=True)

    try:
        bootstrap()
    except subprocess.CalledProcessError as exc:
        print(f"\nSetup failed: {exc}", file=sys.stderr)
        return 1
    return launch(args.mode, extra)


if __name__ == "__main__":
    sys.exit(main())
