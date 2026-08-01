"""
PDF Table Flattener - Launcher
Double-click this file to open the GUI.
This launcher ensures correct working directory regardless of how it is launched.
"""
import sys
import os
import subprocess
from pathlib import Path

# Always cd to the directory this file lives in
THIS_DIR = Path(__file__).resolve().parent
os.chdir(THIS_DIR)

# Ensure project root on sys.path
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

# Now launch the GUI in the same process (no subprocess) so errors surface via messagebox
try:
    # Reconfigure encoding
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    if hasattr(sys.stderr, 'reconfigure'):
        try:
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

    # Import and run GUI
    import tkinter as tk
    from tkinter import messagebox

    try:
        from src.pdf_table_tool.pipeline import PDFTableFlattenerPipeline
    except Exception as import_err:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Lỗi khởi động",
            f"Không thể import module:\n{import_err}\n\n"
            f"Thư mục hiện tại: {THIS_DIR}\n\n"
            "Hãy đảm bảo bạn đã cài đủ dependencies:\n"
            "  pip install pdfplumber PyMuPDF requests"
        )
        sys.exit(1)

    # All good - run GUI
    from gui import PDFFlattenerGUI, main
    main()

except Exception as e:
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Lỗi nghiêm trọng", f"Ứng dụng gặp lỗi:\n\n{e}")
    except Exception:
        pass
    sys.exit(1)
