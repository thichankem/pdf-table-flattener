"""The handful of things that genuinely differ between Windows, macOS and Linux.

Everything else in this package is plain Python and needs no per-OS branching.
Keeping the branches here means the GUI can stay readable, and a new platform
only has to be taught about in one file.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional

IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"
IS_LINUX = not IS_WINDOWS and not IS_MACOS


def open_folder(path: Path) -> None:
    """Show a folder in the desktop's file manager.

    ``os.startfile`` only exists on Windows, so the other two get their own
    command.  A missing file manager must not take the app down with it: the
    results are already on disk either way.
    """
    path.mkdir(parents=True, exist_ok=True)
    target = str(path)
    try:
        if IS_WINDOWS:
            os.startfile(target)  # type: ignore[attr-defined]
        elif IS_MACOS:
            subprocess.run(["open", target], check=False)
        else:
            subprocess.run(["xdg-open", target], check=False)
    except OSError:
        pass


def open_url(url: str) -> None:
    import webbrowser

    try:
        webbrowser.open(url)
    except Exception:  # pragma: no cover - headless machine
        pass


# The GUI asked for "Segoe UI", which exists on Windows only; elsewhere Tk
# silently substitutes a default that looks nothing like the design.  Naming a
# per-platform first choice keeps the three builds looking like one app.
_UI_FONT_PREFERENCES: List[str] = (
    ["Segoe UI", "Tahoma", "Arial"]
    if IS_WINDOWS
    else ["SF Pro Text", "Helvetica Neue", "Lucida Grande", "Arial"]
    if IS_MACOS
    else ["Ubuntu", "Cantarell", "Noto Sans", "DejaVu Sans", "Liberation Sans"]
)


def ui_font_family(available: Optional[Iterable[str]] = None) -> str:
    """The best available UI font family, or Tk's own default as a last resort."""
    names = set(available or ())
    if not names:
        try:
            import tkinter.font as tkfont

            names = set(tkfont.families())
        except Exception:  # pragma: no cover - no display
            return "TkDefaultFont"
    for candidate in _UI_FONT_PREFERENCES:
        if candidate in names:
            return candidate
    return "TkDefaultFont"


def user_documents_dir() -> Path:
    """Where a user would expect generated files to appear."""
    documents = Path.home() / "Documents"
    return documents if documents.is_dir() else Path.home()


def writable_output_dir(preferred: Path) -> Path:
    """``preferred`` if we may write there, otherwise a folder in Documents.

    A copy unpacked into Program Files, /Applications or a read-only mount would
    otherwise fail at the last step, after all the work is done.
    """
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        probe = preferred / ".write_test"
        probe.touch()
        probe.unlink()
        return preferred
    except OSError:
        fallback = user_documents_dir() / "PDF Table Flattener" / preferred.name
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def ollama_executable() -> Optional[str]:
    """Path to the ``ollama`` binary, including the spots installers use.

    The macOS app bundle and the Windows per-user installer both land outside
    the default PATH of a double-clicked launcher, so PATH alone reports "not
    installed" on machines that plainly have it.
    """
    found = shutil.which("ollama")
    if found:
        return found
    candidates = [
        Path.home() / ".local/bin/ollama",
        Path("/usr/local/bin/ollama"),
        Path("/opt/homebrew/bin/ollama"),
        Path("/Applications/Ollama.app/Contents/Resources/ollama"),
        Path.home() / "AppData/Local/Programs/Ollama/ollama.exe",
        Path("C:/Program Files/Ollama/ollama.exe"),
    ]
    for path in candidates:
        try:
            if path.is_file():
                return str(path)
        except OSError:
            continue
    return None


def ollama_running(url: str, timeout: float = 2.0) -> bool:
    """True when an Ollama server answers on ``url``."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def ollama_has_model(url: str, model: str, timeout: float = 3.0) -> bool:
    """True when ``model`` is already pulled on this machine.

    A running server is not enough: asking it for a model it does not have
    returns 404 per table, the pipeline quietly falls back, and the user is left
    believing the LLM ran.  Checking up front is what makes the GUI's toggle
    honest.
    """
    import json
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return False
    # Ollama reports "name:tag"; a bare name means the :latest tag.
    wanted = model if ":" in model else f"{model}:latest"
    return any(entry.get("name") == wanted for entry in payload.get("models", []))


def start_ollama_server(executable: Optional[str] = None) -> bool:
    """Launch ``ollama serve`` in the background; True if the spawn succeeded.

    Installed but not running is the common case on Linux and on a fresh macOS
    install, and it is a worse experience to tell the user "no LLM found" than
    to just start the server they already have.
    """
    binary = executable or ollama_executable()
    if not binary:
        return False
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if IS_WINDOWS:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen([binary, "serve"], **kwargs)
        return True
    except OSError:
        return False
