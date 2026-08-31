"""PDF Table Flattener - GUI launcher.

Double-click this file to open the GUI.  It exists so the app starts with the
right working directory and import path no matter how it was launched, and so a
missing dependency surfaces as a dialog rather than a console traceback nobody
sees.
"""
import os
import sys
from pathlib import Path

# Always run from the directory this file lives in.
THIS_DIR = Path(__file__).resolve().parent
os.chdir(THIS_DIR)

if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

try:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    import tkinter as tk
    from tkinter import messagebox

    try:
        from src.pdf_table_tool.pipeline import PDFTableFlattenerPipeline  # noqa: F401
    except Exception as import_err:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Startup error",
            f"Could not import the application:\n{import_err}\n\n"
            f"Working directory: {THIS_DIR}\n\n"
            "Install the dependencies first:\n"
            "  pip install -r requirements.txt",
        )
        sys.exit(1)

    from gui import main

    main()

except Exception as exc:  # pragma: no cover - last-resort dialog
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Fatal error", f"The application crashed:\n\n{exc}")
    except Exception:
        pass
    sys.exit(1)
