import sys
import threading
import tkinter as tk
import tkinter.font as tkFont
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# Force UTF-8 encoding on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Import pipeline
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from src.pdf_table_tool.pipeline import (
    SUPPORTED_SUFFIXES,
    PDFTableFlattenerPipeline,
    output_stem_for,
    output_suffix_for,
)
from src.pdf_table_tool.platform_support import (
    open_folder,
    ui_font_family,
    writable_output_dir,
)

# Try to import tkinterdnd2 for drag-and-drop support
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False


def _parse_drop_data(data: str) -> list[Path]:
    """Parse tkinterdnd2 drop event data into list of Paths."""
    # Data may be: {path with spaces} path2 {path with spaces}
    paths = []
    raw = data.strip()
    while raw:
        if raw.startswith("{"):
            end = raw.find("}")
            if end == -1:
                break
            paths.append(raw[1:end])
            raw = raw[end + 1:].strip()
        else:
            parts = raw.split(None, 1)
            paths.append(parts[0])
            raw = parts[1].strip() if len(parts) > 1 else ""
    return [Path(p) for p in paths]


def _is_supported(path: Path) -> bool:
    """A PDF, Word or Excel file -- ``~$`` lock files are not real documents."""
    return (
        path.suffix.lower() in SUPPORTED_SUFFIXES
        and not path.name.startswith("~$")
    )


def _documents_in(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.is_file() and _is_supported(p))


class PDFFlattenerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Table Flattener")
        self.root.geometry("820x660")
        self.root.minsize(720, 520)

        # Style configuration
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # "Segoe UI" exists on Windows only; on macOS and Linux Tk would fall
        # back to a face that ignores the sizes chosen here.
        self.ui_font = ui_font_family(tkFont.families(root))
        ui = self.ui_font

        font_normal  = tkFont.Font(family=ui, size=10)
        font_header  = tkFont.Font(family=ui, size=14, weight="bold")
        font_sub     = tkFont.Font(family=ui, size=9)
        font_btn     = tkFont.Font(family=ui, size=11, weight="bold")
        font_heading = tkFont.Font(family=ui, size=10, weight="bold")

        self.style.configure(".",                font=font_normal)
        self.style.configure("Header.TLabel",    font=font_header,  foreground="#1e293b")
        self.style.configure("SubHeader.TLabel", font=font_sub,     foreground="#64748b")
        self.style.configure("Accent.TButton",   font=font_btn,     background="#2563eb", foreground="#ffffff")
        self.style.map("Accent.TButton", background=[("active", "#1d4ed8"), ("disabled", "#94a3b8")])
        self.style.configure("Treeview.Heading", font=font_heading,  background="#f1f5f9")
        self.style.configure("Treeview", rowheight=28)

        self.files_to_process = []  # List of Path objects
        self.is_processing = False
        # A copy unpacked under Program Files or /Applications is not writable,
        # so results land in Documents instead of failing at the last step.
        self.output_dir = writable_output_dir(PROJECT_ROOT / "output_flattened")
        self.dnd_active = DND_AVAILABLE

        self._build_ui()
        self._setup_dnd()
        self.pipeline = None

    # ─────────────────────────────────────── UI BUILD ─────────────────────────

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ── Header ──────────────────────────────────────────────────────────
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(header_frame, text="📄 PDF Table Flattener", style="Header.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header_frame,
            text="Turn every table in a PDF, Word or Excel document into flat bullet points.",
            style="SubHeader.TLabel"
        ).pack(anchor=tk.W, pady=(1, 0))

        # ── Toolbar ─────────────────────────────────────────────────────────
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=(0, 6))

        ttk.Button(toolbar, text="➕ Add Files...", command=self.add_files).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="📂 Add Folder...", command=self.add_directory).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="🗑️ Clear List", command=self.clear_files).pack(side=tk.LEFT)

        self.lbl_count = ttk.Label(toolbar, text="0 files selected", font=tkFont.Font(family=self.ui_font, size=9, slant="italic"))
        self.lbl_count.pack(side=tk.RIGHT, padx=4)

        # ── Drop Zone (shown only when DND available) ────────────────────────
        if DND_AVAILABLE:
            self.drop_frame = tk.Frame(
                main_frame,
                bg="#eff6ff",
                bd=1,
                relief="solid",
                cursor="hand2",
            )
            self.drop_frame.pack(fill=tk.X, pady=(0, 6), ipady=4)

            drop_inner = tk.Frame(self.drop_frame, bg="#eff6ff")
            drop_inner.pack(expand=True)

            tk.Label(
                drop_inner,
                text="🗂️  Drop PDF / Word / Excel files or a folder here (or onto the list below)",
                bg="#eff6ff",
                fg="#2563eb",
                font=tkFont.Font(family=self.ui_font, size=9, weight="bold"),
            ).pack()

        # ── File List Treeview ───────────────────────────────────────────────
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        columns = ("name", "size", "status")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("name",   text="File",     anchor=tk.W)
        self.tree.heading("size",   text="Size",     anchor=tk.CENTER)
        self.tree.heading("status", text="Status",   anchor=tk.CENTER)

        self.tree.column("name",   width=400, minwidth=200, anchor=tk.W,      stretch=True)
        self.tree.column("size",   width=100, minwidth=80,  anchor=tk.CENTER, stretch=False)
        self.tree.column("status", width=160, minwidth=100, anchor=tk.CENTER, stretch=False)

        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Options ──────────────────────────────────────────────────────────
        options_frame = ttk.Frame(main_frame)
        options_frame.pack(fill=tk.X, pady=(0, 8))

        self.numbering_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame,
            text="Number bullets after the document outline (1.1, 1.1.1) - better RAG chunking",
            variable=self.numbering_var,
        ).pack(anchor=tk.W)

        # ── Progress ─────────────────────────────────────────────────────────
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 12))

        self.progress_bar = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(0, 4))

        self.status_lbl = ttk.Label(progress_frame, text="Ready.")
        self.status_lbl.pack(anchor=tk.W)

        # ── Action Buttons ───────────────────────────────────────────────────
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X)

        self.btn_run = ttk.Button(
            action_frame,
            text="🚀 FLATTEN TABLES",
            style="Accent.TButton",
            command=self.start_processing,
        )
        self.btn_run.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=6)

        ttk.Button(action_frame, text="📂 Open Output Folder", command=self.open_output_dir).pack(side=tk.RIGHT, ipady=6)

    # ─────────────────────────────────────── DND SETUP ────────────────────────

    def _setup_dnd(self):
        """Register drag-and-drop handlers if tkinterdnd2 is available.

        Importing tkinterdnd2 is not proof that it works: the package ships a
        Tcl extension that fails to load on plenty of macOS and Linux setups,
        and registering then raises TclError.  Drag-and-drop is a convenience,
        so a failure here just leaves the file picker as the way in.
        """
        if not DND_AVAILABLE:
            return

        # Register both the drop zone frame and the treeview
        try:
            for widget in (self.drop_frame, self.tree):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop)
                widget.dnd_bind("<<DragEnter>>", self._on_drag_enter)
                widget.dnd_bind("<<DragLeave>>", self._on_drag_leave)
        except (tk.TclError, AttributeError):
            self.dnd_active = False
            if hasattr(self, "drop_frame"):
                for child in self.drop_frame.winfo_children():
                    child.destroy()
                tk.Label(
                    self.drop_frame,
                    text="Use the \"Add Files...\" or \"Add Folder...\" buttons above",
                    bg="#eff6ff",
                    fg="#64748b",
                    font=tkFont.Font(family=self.ui_font, size=9),
                ).pack()

    def _on_drag_enter(self, event):
        if self.dnd_active:
            self.drop_frame.config(bg="#dbeafe")
            for child in self.drop_frame.winfo_children():
                self._set_bg_recursive(child, "#dbeafe")

    def _on_drag_leave(self, event):
        if self.dnd_active:
            self.drop_frame.config(bg="#eff6ff")
            for child in self.drop_frame.winfo_children():
                self._set_bg_recursive(child, "#eff6ff")

    def _set_bg_recursive(self, widget, color):
        try:
            widget.config(bg=color)
        except Exception:
            pass
        for child in widget.winfo_children():
            self._set_bg_recursive(child, color)

    def _on_drop(self, event):
        """Handle files/folders dropped onto the window."""
        self._on_drag_leave(event)  # reset highlight

        paths = _parse_drop_data(event.data)
        added = 0
        for p in paths:
            if p.is_dir():
                for doc in _documents_in(p):
                    if doc not in self.files_to_process:
                        self.files_to_process.append(doc)
                        added += 1
            elif _is_supported(p) and p not in self.files_to_process:
                self.files_to_process.append(p)
                added += 1

        if added:
            self._update_treeview()
            self.status_lbl.config(text=f"Added {added} file(s) by drag and drop.")

    # ─────────────────────────────────────── FILE MANAGEMENT ──────────────────

    def add_files(self):
        files = filedialog.askopenfilenames(
            title="Select PDF, Word or Excel files",
            filetypes=[
                ("PDF / Word / Excel", "*.pdf *.docx *.xlsx *.xlsm"),
                ("PDF", "*.pdf"),
                ("Word", "*.docx"),
                ("Excel", "*.xlsx *.xlsm"),
                ("All files", "*.*"),
            ]
        )
        for f in files:
            path = Path(f)
            if _is_supported(path) and path not in self.files_to_process:
                self.files_to_process.append(path)
        if files:
            self._update_treeview()

    def add_directory(self):
        dir_path = filedialog.askdirectory(
            title="Select a folder of PDF / Word / Excel files"
        )
        if not dir_path:
            return
        doc_files = _documents_in(Path(dir_path))
        if not doc_files:
            messagebox.showinfo(
                "Nothing to do",
                "No PDF, Word or Excel file was found in that folder.",
            )
            return
        for path in doc_files:
            if path not in self.files_to_process:
                self.files_to_process.append(path)
        self._update_treeview()

    def clear_files(self):
        if self.is_processing:
            return
        self.files_to_process.clear()
        self._update_treeview()
        self.status_lbl.config(text="Ready.")
        self.progress_bar["value"] = 0

    def _update_treeview(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for path in self.files_to_process:
            try:
                size_bytes = path.stat().st_size
                size_str = f"{size_bytes/(1024*1024):.2f} MB" if size_bytes >= 1024*1024 else f"{size_bytes/1024:.0f} KB"
            except OSError:
                size_str = "?"
            self.tree.insert("", tk.END, iid=str(path), values=(path.name, size_str, "Queued"))

        self.lbl_count.config(text=f"{len(self.files_to_process)} file(s) selected")

    def open_output_dir(self):
        open_folder(self.output_dir)

    # ─────────────────────────────────────── PROCESSING ───────────────────────

    def start_processing(self):
        if not self.files_to_process:
            messagebox.showwarning("No files", "Select at least one PDF, Word or Excel file first.")
            return
        if self.is_processing:
            return

        self.is_processing = True
        self.btn_run.config(state=tk.DISABLED)
        self.progress_bar["maximum"] = len(self.files_to_process)
        self.progress_bar["value"] = 0

        threading.Thread(target=self._worker_process, daemon=True).start()

    def _worker_process(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Building the pipeline imports pdfplumber and friends, so it is kept
        # between runs and only paid for once.
        numbering = self.numbering_var.get()
        if self.pipeline is None:
            self.root.after(0, lambda: self.status_lbl.config(text="Starting up..."))
            self.pipeline = PDFTableFlattenerPipeline(numbering=numbering)
        elif self.pipeline.numbering != numbering:
            # The checkbox was changed between two runs; a cached pipeline would
            # otherwise keep using the setting of the first one.
            self.pipeline = PDFTableFlattenerPipeline(numbering=numbering)

        total = len(self.files_to_process)
        success_count = 0
        fail_count = 0

        used_names: set[str] = set()

        for idx, pdf_path in enumerate(self.files_to_process, 1):
            # Same name, same format as the input -- only the folder differs.
            out_file = self._output_path_for(pdf_path, used_names)
            if out_file is None:
                fail_count += 1
                self.root.after(0, lambda p=pdf_path: self._update_file_status(
                    p, "❌ Already in the output folder"
                ))
                self.root.after(0, lambda val=idx: self.progress_bar.config(value=val))
                continue

            self.root.after(0, lambda p=pdf_path: self._update_file_status(p, "Working..."))
            self.root.after(0, lambda i=idx, t=total, p=pdf_path: self.status_lbl.config(
                text=f"[{i}/{t}] Processing: {p.name}"
            ))

            try:
                summary = self.pipeline.process(str(pdf_path), str(out_file))
                tables_cnt = summary.get("total_tables_flattened", 0)
                if summary.get("verification_passed", True):
                    status_text = f"✅ Done ({tables_cnt} tables)"
                else:
                    status_text = f"⚠️ Done ({tables_cnt} tables) - self-check failed"
                success_count += 1
                self.root.after(0, lambda p=pdf_path, st=status_text: self._update_file_status(p, st))
            except Exception as e:
                fail_count += 1
                err_msg = f"❌ Error: {str(e)[:30]}"
                self.root.after(0, lambda p=pdf_path, st=err_msg: self._update_file_status(p, st))

            self.root.after(0, lambda val=idx: self.progress_bar.config(value=val))

        summary_msg = f"Finished: {success_count}/{total} file(s) succeeded."
        if fail_count > 0:
            summary_msg += f" ({fail_count} failed)"

        self.root.after(0, lambda: self._finish_processing(summary_msg))

    def _output_path_for(self, source: Path, used_names: set) -> Path | None:
        """Where this file's result goes, or None when that would clobber it.

        The output keeps the input's own name with `_flattened` appended, so two
        guards are still needed: a file already sitting in the results folder
        must not be overwritten, and two inputs of the same name from different
        folders must not land on top of each other.  Only the extension may
        differ: an Excel workbook is flattened into Word, because a bullet list
        is not a grid of cells.
        """
        suffix = output_suffix_for(str(source))
        stem = output_stem_for(str(source))
        candidate = self.output_dir / f"{stem}{suffix}"
        try:
            if candidate.resolve() == source.resolve():
                return None
        except OSError:
            pass

        if candidate.name.lower() in used_names:
            n = 2
            while f"{stem} ({n}){suffix}".lower() in used_names:
                n += 1
            candidate = self.output_dir / f"{stem} ({n}){suffix}"

        used_names.add(candidate.name.lower())
        return candidate

    def _update_file_status(self, path: Path, status: str):
        iid = str(path)
        if self.tree.exists(iid):
            vals = list(self.tree.item(iid, "values"))
            vals[2] = status
            self.tree.item(iid, values=vals)

    def _finish_processing(self, msg: str):
        self.is_processing = False
        self.btn_run.config(state=tk.NORMAL)
        self.status_lbl.config(text=msg)
        messagebox.showinfo("Finished", f"{msg}\n\nResults were written to:\n{self.output_dir}")


def main():
    root = None
    if DND_AVAILABLE:
        # The Tcl side of tkinterdnd2 is a separate binary that is missing or
        # mismatched often enough on macOS and Linux to be worth surviving.
        try:
            root = TkinterDnD.Tk()
        except Exception:
            root = None
    if root is None:
        root = tk.Tk()

    app = PDFFlattenerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
