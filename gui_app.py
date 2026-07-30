import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from tkinterdnd2 import DND_FILES, TkinterDnD

# Import core conversion engine
from doc_table_converter import convert_file, process_document

class DesktopWordConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Công Cụ Chuyển Đổi Bảng (PDF / Word) sang Text Gạch Đầu Dòng (- )")
        self.root.geometry("980x750")
        self.root.minsize(800, 600)

        # Style configuration
        self.style = ttk.Style()
        self.style.theme_use('clam')

        # Color Palette
        self.bg_header = "#1e272e"
        self.drop_bg = "#f1f2f6"
        self.drop_hover = "#dcdde1"
        self.accent_color = "#00a8ff"

        self.root.configure(bg="#f5f6fa")
        self.file_list = []  # List of file absolute paths
        self.error_details = {} # Dict storing detailed error messages for items

        self._build_ui()

    def _build_ui(self):
        # 1. Header Banner
        header_frame = tk.Frame(self.root, bg=self.bg_header, pady=12)
        header_frame.pack(fill=tk.X)

        title_lbl = tk.Label(
            header_frame,
            text="📄 CÔNG CỤ CHUYỂN ĐỔI BẢNG (PDF / WORD) SANG TEXT GẠCH ĐẦU DÒNG",
            font=("Segoe UI", 13, "bold"),
            fg="#ffffff",
            bg=self.bg_header
        )
        title_lbl.pack()

        subtitle_lbl = tk.Label(
            header_frame,
            text="Xóa bảng & chuyển thành dạng: - Tên: Nam | Tuổi: 25 | Chức vụ: Dev (Giữ nguyên xi mọi văn bản khác)",
            font=("Segoe UI", 9),
            fg="#d2dae2",
            bg=self.bg_header
        )
        subtitle_lbl.pack(pady=(2, 0))

        # Main Layout container
        main_box = ttk.Frame(self.root, padding=10)
        main_box.pack(fill=tk.BOTH, expand=True)

        # 2. Drag & Drop Target Area
        self.drop_frame = tk.Frame(
            main_box,
            bg=self.drop_bg,
            bd=2,
            relief=tk.GROOVE,
            cursor="hand2"
        )
        self.drop_frame.pack(fill=tk.X, pady=(0, 10), ipady=15)

        # Register Drag and Drop on drop_frame
        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind('<<Drop>>', self._on_drop_files)
        self.drop_frame.dnd_bind('<<DropEnter>>', lambda e: self.drop_frame.config(bg=self.drop_hover))
        self.drop_frame.dnd_bind('<<DropLeave>>', lambda e: self.drop_frame.config(bg=self.drop_bg))

        drop_label = tk.Label(
            self.drop_frame,
            text="📂 KÉO & THẢ CÁC FILE PDF (.PDF) HOẶC WORD (.DOC, .DOCX) VÀO ĐÂY\n(Hoặc nhấp vào đây để chọn file)",
            font=("Segoe UI", 11, "bold"),
            fg="#2f3640",
            bg=self.drop_bg
        )
        drop_label.pack(expand=True)
        
        # Click on drop zone to select files
        self.drop_frame.bind("<Button-1>", lambda e: self._browse_files())
        drop_label.bind("<Button-1>", lambda e: self._browse_files())

        # 3. Queue Listview (Treeview)
        queue_group = ttk.LabelFrame(main_box, text=" Danh Sách File Chờ Xử Lý ", padding=5)
        queue_group.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Toolbar above Treeview
        tb_frame = ttk.Frame(queue_group)
        tb_frame.pack(fill=tk.X, pady=(0, 5))

        btn_add_files = ttk.Button(tb_frame, text="➕ Thêm File...", command=self._browse_files)
        btn_add_files.pack(side=tk.LEFT, padx=3)

        btn_add_folder = ttk.Button(tb_frame, text="📁 Thêm Thư Mục...", command=self._browse_folder)
        btn_add_folder.pack(side=tk.LEFT, padx=3)

        btn_remove = ttk.Button(tb_frame, text="❌ Xóa File Chọn", command=self._remove_selected)
        btn_remove.pack(side=tk.LEFT, padx=3)

        btn_clear = ttk.Button(tb_frame, text="🧹 Xóa Tất Cả", command=self._clear_all)
        btn_clear.pack(side=tk.LEFT, padx=3)

        self.lbl_count = ttk.Label(tb_frame, text="Tổng số file: 0", font=("Segoe UI", 9, "bold"))
        self.lbl_count.pack(side=tk.RIGHT, padx=5)

        # Treeview Widget
        columns = ("no", "filename", "path", "status")
        self.tree = ttk.Treeview(queue_group, columns=columns, show="headings", height=6)
        
        self.tree.heading("no", text="#", anchor=tk.CENTER)
        self.tree.heading("filename", text="Tên File", anchor=tk.W)
        self.tree.heading("path", text="Đường Dẫn Chi Tiết", anchor=tk.W)
        self.tree.heading("status", text="Trạng Thái", anchor=tk.CENTER)

        self.tree.column("no", width=40, anchor=tk.CENTER)
        self.tree.column("filename", width=250, anchor=tk.W)
        self.tree.column("path", width=420, anchor=tk.W)
        self.tree.column("status", width=200, anchor=tk.CENTER)

        # Scrollbar for tree
        scrollbar = ttk.Scrollbar(queue_group, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", lambda e: self._on_tree_double_click())

        # Also register Drag & Drop on Treeview
        self.tree.drop_target_register(DND_FILES)
        self.tree.dnd_bind('<<Drop>>', self._on_drop_files)

        # 4. Settings Configuration Group
        cfg_group = ttk.LabelFrame(main_box, text=" Cấu Hình Chuyển Đổi Bảng ", padding=8)
        cfg_group.pack(fill=tk.X, pady=(0, 10))

        # Row 1: Separators
        r1_frame = ttk.Frame(cfg_group)
        r1_frame.pack(fill=tk.X, pady=3)

        ttk.Label(r1_frame, text="Ký tự phân cách: ", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 10))

        self.sep_choice = tk.StringVar(value="pipe")
        
        ttk.Radiobutton(r1_frame, text="Thanh đứng (Tên: Nam | Tuổi: 25)", variable=self.sep_choice, value="pipe", command=self._on_sep_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(r1_frame, text="Dấu phẩy (Tên: Nam , Tuổi: 25)", variable=self.sep_choice, value="comma", command=self._on_sep_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(r1_frame, text="Gạch ngang (a - 1)", variable=self.sep_choice, value="dash", command=self._on_sep_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(r1_frame, text="Hai chấm (a: 1)", variable=self.sep_choice, value="colon", command=self._on_sep_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(r1_frame, text="Tùy chỉnh:", variable=self.sep_choice, value="custom", command=self._on_sep_change).pack(side=tk.LEFT, padx=(15, 5))

        self.custom_sep_var = tk.StringVar(value=" | ")
        self.custom_sep_entry = ttk.Entry(r1_frame, textvariable=self.custom_sep_var, width=8, state=tk.DISABLED)
        self.custom_sep_entry.pack(side=tk.LEFT)

        # Row 2: Header & Format Options
        r2_frame = ttk.Frame(cfg_group)
        r2_frame.pack(fill=tk.X, pady=3)

        self.bullet_prefix_var = tk.BooleanVar(value=True)
        cb_bullet = ttk.Checkbutton(r2_frame, text="Gạch đầu dòng (- )", variable=self.bullet_prefix_var)
        cb_bullet.pack(side=tk.LEFT, padx=(0, 15))

        self.use_header_var = tk.BooleanVar(value=True)
        cb_header = ttk.Checkbutton(r2_frame, text="Dùng Dòng 0 làm Tiêu đề cột", variable=self.use_header_var)
        cb_header.pack(side=tk.LEFT, padx=(0, 15))

        self.show_indices_var = tk.BooleanVar(value=False)
        cb_indices = ttk.Checkbutton(r2_frame, text="Chỉ số dòng (--- Dòng X ---)", variable=self.show_indices_var)
        cb_indices.pack(side=tk.LEFT, padx=(0, 15))

        self.process_pseudo_var = tk.BooleanVar(value=False)
        cb_pseudo = ttk.Checkbutton(r2_frame, text="Bảng giả lập dạng tab (mặc định tắt)", variable=self.process_pseudo_var)
        cb_pseudo.pack(side=tk.LEFT, padx=(0, 15))

        # Row 3: Output format
        r3_frame = ttk.Frame(cfg_group)
        r3_frame.pack(fill=tk.X, pady=3)

        ttk.Label(r3_frame, text="Định dạng xuất:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 10))

        self.output_fmt_var = tk.StringVar(value="auto")
        ttk.Radiobutton(r3_frame, text="Cùng định dạng file gốc (.pdf / .docx)", variable=self.output_fmt_var, value="auto").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(r3_frame, text="File .pdf mới", variable=self.output_fmt_var, value="pdf").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(r3_frame, text="File .docx mới", variable=self.output_fmt_var, value="docx").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(r3_frame, text="File .txt", variable=self.output_fmt_var, value="txt").pack(side=tk.LEFT, padx=5)

        # 5. Action Buttons & Progress Bar
        act_box = ttk.Frame(main_box)
        act_box.pack(fill=tk.X, pady=(0, 10))

        self.btn_convert = tk.Button(
            act_box,
            text="⚡ CHUYỂN ĐỔI TẤT CẢ FILE ⚡",
            font=("Segoe UI", 11, "bold"),
            bg="#44bd32",
            fg="white",
            activebackground="#4cd137",
            activeforeground="white",
            bd=0,
            padx=15,
            pady=8,
            cursor="hand2",
            command=self._start_batch_conversion
        )
        self.btn_convert.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_preview = ttk.Button(act_box, text="🔍 Xem Trước File Đã Chọn", command=self._preview_selected)
        self.btn_preview.pack(side=tk.LEFT, padx=5)

        self.progress_bar = ttk.Progressbar(act_box, orient=tk.HORIZONTAL, mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        # 6. Preview Text Box
        preview_group = ttk.LabelFrame(main_box, text=" Khung Xem Trước Nhanh Nội Dung ", padding=5)
        preview_group.pack(fill=tk.BOTH, expand=False)

        self.txt_preview = scrolledtext.ScrolledText(preview_group, font=("Consolas", 9), height=6, wrap=tk.WORD)
        self.txt_preview.pack(fill=tk.BOTH, expand=True)

        # Status Bar
        self.status_var = tk.StringVar(value="Sẵn sàng. Sẵn sàng kéo thả file Word/PDF vào giao diện.")
        status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W, bg="#2f3640", fg="white", font=("Segoe UI", 9))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _on_sep_change(self):
        if self.sep_choice.get() == "custom":
            self.custom_sep_entry.config(state=tk.NORMAL)
        else:
            self.custom_sep_entry.config(state=tk.DISABLED)

    def _get_separator(self):
        choice = self.sep_choice.get()
        if choice == "pipe":
            return " | "
        elif choice == "comma":
            return " , "
        elif choice == "space":
            return " "
        elif choice == "dash":
            return " - "
        elif choice == "colon":
            return ": "
        elif choice == "custom":
            return self.custom_sep_var.get()
        return " | "

    def _on_drop_files(self, event):
        raw_data = event.data
        if not raw_data:
            return
        
        paths = self.root.tk.splitlist(raw_data)
        added_count = 0

        for path in paths:
            clean_p = os.path.abspath(path.strip('{}'))
            if os.path.isfile(clean_p) and clean_p.lower().endswith(('.doc', '.docx', '.pdf')):
                self._add_file_to_list(clean_p)
                added_count += 1
            elif os.path.isdir(clean_p):
                for root_dir, _, files in os.walk(clean_p):
                    for f in files:
                        if f.lower().endswith(('.doc', '.docx', '.pdf')) and not f.startswith('~$'):
                            self._add_file_to_list(os.path.join(root_dir, f))
                            added_count += 1

        self.drop_frame.config(bg=self.drop_bg)
        self.status_var.set(f"Đã thêm {added_count} file từ kéo thả.")

    def _add_file_to_list(self, file_path):
        file_path = os.path.abspath(file_path)
        if file_path not in self.file_list:
            self.file_list.append(file_path)
            no = len(self.file_list)
            fname = os.path.basename(file_path)
            self.tree.insert("", tk.END, values=(no, fname, file_path, "Chờ xử lý"))
            self._update_file_count()

    def _update_file_count(self):
        self.lbl_count.config(text=f"Tổng số file: {len(self.file_list)}")

    def _browse_files(self):
        files = filedialog.askopenfilenames(
            title="Chọn các file PDF / Word",
            filetypes=[("PDF & Word Files", "*.pdf;*.docx;*.doc"), ("PDF Files", "*.pdf"), ("Word Documents", "*.docx;*.doc"), ("All Files", "*.*")]
        )
        if files:
            for f in files:
                self._add_file_to_list(f)

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Chọn thư mục chứa file PDF/Word")
        if folder:
            added = 0
            for root_dir, _, files in os.walk(folder):
                for f in files:
                    if f.lower().endswith(('.doc', '.docx', '.pdf')) and not f.startswith('~$'):
                        self._add_file_to_list(os.path.join(root_dir, f))
                        added += 1
            self.status_var.set(f"Đã thêm {added} file từ thư mục.")

    def _remove_selected(self):
        selected_items = self.tree.selection()
        if not selected_items:
            return
        for item in selected_items:
            vals = self.tree.item(item, "values")
            fpath = vals[2]
            if fpath in self.file_list:
                self.file_list.remove(fpath)
            if item in self.error_details:
                del self.error_details[item]
            self.tree.delete(item)

        for idx, item in enumerate(self.tree.get_children(), 1):
            old_vals = self.tree.item(item, "values")
            self.tree.item(item, values=(idx, old_vals[1], old_vals[2], old_vals[3]))

        self._update_file_count()

    def _clear_all(self):
        self.file_list.clear()
        self.error_details.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._update_file_count()
        self.status_var.set("Đã xóa danh sách file.")

    def _on_tree_double_click(self):
        selected_items = self.tree.selection()
        if not selected_items:
            return
        item_id = selected_items[0]
        vals = self.tree.item(item_id, "values")

        if item_id in self.error_details:
            messagebox.showerror("Chi Tiết Lỗi", f"File: {vals[1]}\n\nLỗi xảy ra:\n{self.error_details[item_id]}")
        else:
            self._preview_selected()

    def _preview_selected(self):
        selected_items = self.tree.selection()
        if not selected_items:
            if self.file_list:
                fpath = self.file_list[0]
            else:
                messagebox.showwarning("Cảnh báo", "Vui lòng chọn hoặc kéo thả ít nhất 1 file để xem trước.")
                return
        else:
            fpath = self.tree.item(selected_items[0], "values")[2]

        self.status_var.set(f"Đang tạo bản xem trước cho: {os.path.basename(fpath)}...")
        
        def worker():
            try:
                sep = self._get_separator()
                header = self.use_header_var.get()
                indices = self.show_indices_var.get()
                bullet = self.bullet_prefix_var.get()
                pseudo = self.process_pseudo_var.get()
                full_text, _ = process_document(fpath, separator=sep, use_header=header, show_row_indices=indices, bullet_prefix=bullet, process_pseudo=pseudo)

                def update_ui():
                    self.txt_preview.delete("1.0", tk.END)
                    self.txt_preview.insert(tk.END, f"=== KẾT QUẢ XEM TRƯỚC BẢNG: {os.path.basename(fpath)} ===\n\n")
                    if full_text:
                        self.txt_preview.insert(tk.END, full_text)
                    else:
                        self.txt_preview.insert(tk.END, "(Không tìm thấy bảng nào trong tài liệu)")
                    self.status_var.set(f"Đã tải bản xem trước cho {os.path.basename(fpath)}")

                self.root.after(0, update_ui)
            except Exception as ex:
                self.root.after(0, lambda: messagebox.showerror("Lỗi Xem Trước", str(ex)))

        threading.Thread(target=worker, daemon=True).start()

    def _start_batch_conversion(self):
        if not self.file_list:
            messagebox.showwarning("Cảnh báo", "Danh sách trống! Vui lòng kéo thả hoặc chọn file PDF/Word trước khi chuyển đổi.")
            return

        sep = self._get_separator()
        header = self.use_header_var.get()
        indices = self.show_indices_var.get()
        bullet = self.bullet_prefix_var.get()
        pseudo = self.process_pseudo_var.get()
        export_mode = self.output_fmt_var.get()

        self.btn_convert.config(state=tk.DISABLED)
        self.progress_bar["value"] = 0
        total = len(self.file_list)

        def worker():
            success_count = 0
            for idx, item_id in enumerate(self.tree.get_children()):
                fpath = self.tree.item(item_id, "values")[2]
                fname = os.path.basename(fpath)

                self.root.after(0, lambda i=item_id, fn=fname: self.tree.item(i, values=(self.tree.item(i, "values")[0], fn, fpath, "⏳ Đang xử lý...")))
                self.root.after(0, lambda fn=fname: self.status_var.set(f"Đang xử lý: {fn}"))

                try:
                    base, orig_ext = os.path.splitext(fpath)
                    
                    if export_mode == "txt":
                        out_ext = ".txt"
                    elif export_mode == "pdf":
                        out_ext = ".pdf"
                    elif export_mode == "docx":
                        out_ext = ".docx"
                    else: # "auto"
                        out_ext = orig_ext if orig_ext.lower() in ['.pdf', '.docx'] else '.docx'

                    out_path = f"{base}_converted{out_ext}"

                    try:
                        convert_file(
                            file_path=fpath,
                            output_path=out_path,
                            export_txt=(out_ext == ".txt"),
                            export_pdf=(out_ext == ".pdf"),
                            separator=sep,
                            use_header=header,
                            show_row_indices=indices,
                            bullet_prefix=bullet,
                            process_pseudo=pseudo
                        )
                    except PermissionError:
                        out_path = f"{base}_converted_new{out_ext}"
                        convert_file(
                            file_path=fpath,
                            output_path=out_path,
                            export_txt=(out_ext == ".txt"),
                            export_pdf=(out_ext == ".pdf"),
                            separator=sep,
                            use_header=header,
                            show_row_indices=indices,
                            bullet_prefix=bullet,
                            process_pseudo=pseudo
                        )

                    success_count += 1
                    self.root.after(0, lambda i=item_id, fn=fname: self.tree.item(i, values=(self.tree.item(i, "values")[0], fn, fpath, "✅ Hoàn thành")))

                except PermissionError:
                    err_msg = "File đang mở trong ứng dụng khác! Hãy đóng lại và thử lại."
                    self.error_details[item_id] = err_msg
                    self.root.after(0, lambda i=item_id, fn=fname: self.tree.item(i, values=(self.tree.item(i, "values")[0], fn, fpath, "❌ Đóng file!")))

                except FileNotFoundError:
                    err_msg = f"Không tìm thấy file: {fpath}"
                    self.error_details[item_id] = err_msg
                    self.root.after(0, lambda i=item_id, fn=fname: self.tree.item(i, values=(self.tree.item(i, "values")[0], fn, fpath, "❌ Không tìm thấy file")))

                except Exception as ex:
                    err_msg = str(ex)
                    self.error_details[item_id] = err_msg
                    short_err = err_msg[:30] if len(err_msg) > 30 else err_msg
                    self.root.after(0, lambda i=item_id, fn=fname, se=short_err: self.tree.item(i, values=(self.tree.item(i, "values")[0], fn, fpath, f"❌ Lỗi: {se}")))

                progress = int(((idx + 1) / total) * 100)
                self.root.after(0, lambda p=progress: self.progress_bar.config(value=p))

            self.root.after(0, lambda: self._on_batch_complete(success_count, total))

        threading.Thread(target=worker, daemon=True).start()

    def _on_batch_complete(self, success, total):
        self.btn_convert.config(state=tk.NORMAL)
        self.status_var.set(f"Hoàn thành chuyển đổi {success}/{total} file.")
        messagebox.showinfo("Hoàn Thành", f"Đã chuyển đổi thành công {success}/{total} file.\nFile đầu ra được lưu ngay bên cạnh file gốc!")

def main():
    root = TkinterDnD.Tk()
    app = DesktopWordConverterApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
