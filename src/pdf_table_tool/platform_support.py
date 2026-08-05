"""The handful of things that genuinely differ between Windows, macOS and Linux.

Everything else in this package is plain Python and needs no per-OS branching.
Keeping the branches here means the GUI can stay readable, and a new platform
only has to be taught about in one file.
"""

import os
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
