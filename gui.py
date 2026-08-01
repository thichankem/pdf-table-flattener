import sys
import os
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

from src.pdf_table_tool.pipeline import PDFTableFlattenerPipeline

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


class PDFFlattenerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Table Flattener - Làm phẳng Bảng PDF")
        self.root.geometry("820x660")
        self.root.minsize(720, 520)

        # Style configuration
        self.style = ttk.Style()
        self.style.theme_use("clam")

        font_normal  = tkFont.Font(family="Segoe UI", size=10)
        font_header  = tkFont.Font(family="Segoe UI", size=14, weight="bold")
        font_sub     = tkFont.Font(family="Segoe UI", size=9)
        font_btn     = tkFont.Font(family="Segoe UI", size=11, weight="bold")
        font_heading = tkFont.Font(family="Segoe UI", size=10, weight="bold")

        self.style.configure(".",                font=font_normal)
        self.style.configure("Header.TLabel",    font=font_header,  foreground="#1e293b")
        self.style.configure("SubHeader.TLabel", font=font_sub,     foreground="#64748b")
        self.style.configure("Accent.TButton",   font=font_btn,     background="#2563eb", foreground="#ffffff")
        self.style.map("Accent.TButton", background=[("active", "#1d4ed8"), ("disabled", "#94a3b8")])
        self.style.configure("Treeview.Heading", font=font_heading,  background="#f1f5f9")
        self.style.configure("Treeview", rowheight=28)

        self.files_to_process = []  # List of Path objects
        self.is_processing = False
        self.output_dir = PROJECT_ROOT / "output_flattened"

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
            text="Tự động làm phẳng toàn bộ bảng trong file PDF thành dạng gạch đầu dòng (bullet points).",
            style="SubHeader.TLabel"
        ).pack(anchor=tk.W, pady=(1, 0))

        # ── Toolbar ─────────────────────────────────────────────────────────
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=(0, 6))

        ttk.Button(toolbar, text="➕ Chọn File PDF...", command=self.add_files).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="📂 Chọn Thư Mục...", command=self.add_directory).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="🗑️ Xóa Danh Sách", command=self.clear_files).pack(side=tk.LEFT)

        self.lbl_count = ttk.Label(toolbar, text="Đã chọn: 0 file", font=tkFont.Font(family="Segoe UI", size=9, slant="italic"))
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
                text="🗂️  Kéo & thả file PDF hoặc thư mục vào đây (hoặc vào danh sách bên dưới)",
                bg="#eff6ff",
                fg="#2563eb",
                font=tkFont.Font(family="Segoe UI", size=9, weight="bold"),
            ).pack()

        # ── File List Treeview ───────────────────────────────────────────────
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        columns = ("name", "size", "status")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("name",   text="Tên File PDF",  anchor=tk.W)
        self.tree.heading("size",   text="Dung lượng",   anchor=tk.CENTER)
        self.tree.heading("status", text="Trạng thái",   anchor=tk.CENTER)

        self.tree.column("name",   width=400, minwidth=200, anchor=tk.W,      stretch=True)
        self.tree.column("size",   width=100, minwidth=80,  anchor=tk.CENTER, stretch=False)
        self.tree.column("status", width=160, minwidth=100, anchor=tk.CENTER, stretch=False)

        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Progress ─────────────────────────────────────────────────────────
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 12))

        self.progress_bar = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(0, 4))

        self.status_lbl = ttk.Label(progress_frame, text="Sẵn sàng xử lý.")
        self.status_lbl.pack(anchor=tk.W)

        # ── Action Buttons ───────────────────────────────────────────────────
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X)

        self.btn_run = ttk.Button(
            action_frame,
            text="🚀 BẮT ĐẦU LÀM PHẲNG BẢNG",
            style="Accent.TButton",
            command=self.start_processing,
        )
        self.btn_run.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=6)

        ttk.Button(action_frame, text="📂 Mở Thư Mục Kết Quả", command=self.open_output_dir).pack(side=tk.RIGHT, ipady=6)

    # ─────────────────────────────────────── DND SETUP ────────────────────────

    def _setup_dnd(self):
        """Register drag-and-drop handlers if tkinterdnd2 is available."""
        if not DND_AVAILABLE:
            return

        # Register both the drop zone frame and the treeview
        for widget in (self.drop_frame, self.tree):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
            widget.dnd_bind("<<DragEnter>>", self._on_drag_enter)
            widget.dnd_bind("<<DragLeave>>", self._on_drag_leave)

    def _on_drag_enter(self, event):
        if DND_AVAILABLE:
            self.drop_frame.config(bg="#dbeafe")
            for child in self.drop_frame.winfo_children():
                self._set_bg_recursive(child, "#dbeafe")

    def _on_drag_leave(self, event):
        if DND_AVAILABLE:
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
                for pdf in p.glob("*.pdf"):
                    if pdf not in self.files_to_process:
                        self.files_to_process.append(pdf)
                        added += 1
            elif p.suffix.lower() == ".pdf" and p not in self.files_to_process:
                self.files_to_process.append(p)
                added += 1

        if added:
            self._update_treeview()
            self.status_lbl.config(text=f"Đã thêm {added} file qua kéo thả.")

    # ─────────────────────────────────────── FILE MANAGEMENT ──────────────────

    def add_files(self):
        files = filedialog.askopenfilenames(
            title="Chọn file PDF",
            filetypes=[("File PDF", "*.pdf"), ("Tất cả file", "*.*")]
        )
        for f in files:
            path = Path(f)
            if path.suffix.lower() == ".pdf" and path not in self.files_to_process:
                self.files_to_process.append(path)
        if files:
            self._update_treeview()

    def add_directory(self):
        dir_path = filedialog.askdirectory(title="Chọn thư mục chứa file PDF")
        if not dir_path:
            return
        pdf_files = list(Path(dir_path).glob("*.pdf"))
        if not pdf_files:
            messagebox.showinfo("Thông báo", "Không tìm thấy file PDF nào trong thư mục đã chọn.")
            return
        for path in pdf_files:
            if path not in self.files_to_process:
                self.files_to_process.append(path)
        self._update_treeview()

    def clear_files(self):
        if self.is_processing:
            return
        self.files_to_process.clear()
        self._update_treeview()
        self.status_lbl.config(text="Sẵn sàng xử lý.")
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
            self.tree.insert("", tk.END, iid=str(path), values=(path.name, size_str, "Chờ xử lý"))

        self.lbl_count.config(text=f"Đã chọn: {len(self.files_to_process)} file")

    def open_output_dir(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self.output_dir))

    # ─────────────────────────────────────── PROCESSING ───────────────────────

    def start_processing(self):
        if not self.files_to_process:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn ít nhất 1 file PDF để xử lý.")
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

        if self.pipeline is None:
            self.root.after(0, lambda: self.status_lbl.config(text="Đang khởi tạo..."))
            self.pipeline = PDFTableFlattenerPipeline(use_llm=False)

        total = len(self.files_to_process)
        success_count = 0
        fail_count = 0

        for idx, pdf_path in enumerate(self.files_to_process, 1):
            out_file = self.output_dir / f"{pdf_path.stem}_flattened.pdf"

            self.root.after(0, lambda p=pdf_path: self._update_file_status(p, "Đang xử lý..."))
            self.root.after(0, lambda i=idx, t=total, p=pdf_path: self.status_lbl.config(
                text=f"[{i}/{t}] Đang xử lý: {p.name}"
            ))

            try:
                summary = self.pipeline.process(str(pdf_path), str(out_file))
                tables_cnt = summary.get("total_tables_flattened", 0)
                if summary.get("verification_passed", True):
                    status_text = f"✅ Xong ({tables_cnt} bảng)"
                else:
                    status_text = f"⚠️ Xong ({tables_cnt} bảng) - kiểm tra chưa đạt"
                success_count += 1
                self.root.after(0, lambda p=pdf_path, st=status_text: self._update_file_status(p, st))
            except Exception as e:
                fail_count += 1
                err_msg = f"❌ Lỗi: {str(e)[:30]}"
                self.root.after(0, lambda p=pdf_path, st=err_msg: self._update_file_status(p, st))

            self.root.after(0, lambda val=idx: self.progress_bar.config(value=val))

        summary_msg = f"Hoàn thành! Thành công: {success_count}/{total} file."
        if fail_count > 0:
            summary_msg += f" (Lỗi: {fail_count})"

        self.root.after(0, lambda: self._finish_processing(summary_msg))

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
        messagebox.showinfo("Hoàn tất", f"{msg}\n\nFile kết quả được lưu tại:\n{self.output_dir}")


def main():
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    app = PDFFlattenerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
