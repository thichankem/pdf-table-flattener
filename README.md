# Công Cụ Chuyển Đổi Bảng PDF / Word (.pdf, .doc, .docx) Thành Text Gạch Đầu Dòng (- )

Công cụ tự động đọc file **PDF** và **Word** (`.pdf`, `.doc`, `.docx`), trích xuất toàn bộ bảng (table), xóa bảng đi và thay thế bằng dạng văn bản gạch đầu dòng (`- Key: Value`) theo từng dòng bảng. **Chỉ tác động duy nhất vào bảng, 100% văn bản/hình ảnh/tiêu đề ngoài bảng giữ nguyên xi không đụng chạm.**

---

## 🌟 Ví Dụ Minh Họa

### Bảng trong file PDF / Word:
| Tên | Tuổi | Chức vụ |
|---|---|---|
| Nam | 25 | Dev |
| Hoa | 30 | Tester |

### Kết quả sau khi chuyển đổi:
```text
- Tên: Nam | Tuổi: 25 | Chức vụ: Dev
- Tên: Hoa | Tuổi: 30 | Chức vụ: Tester
```

Nếu chọn ký tự phân cách là dấu phẩy ` , `:
```text
- Tên: Nam , Tuổi: 25 , Chức vụ: Dev
- Tên: Hoa , Tuổi: 30 , Chức vụ: Tester
```

---

## 🚀 Cách Sử Dụng

### Cách 1: Sử dụng Giao diện Đồ họa Kéo & Thả (GUI)
1. Nhấp kép vào file **`run.bat`** (hoặc chạy phím tắt trên Desktop **`ChuyenDoiBangWord.vbs`**).
2. Kéo & Thả file **PDF** (`.pdf`) hoặc **Word** (`.doc`, `.docx`) vào giao diện.
3. Tùy chọn ký tự phân cách (Thanh đứng `|`, dấu phẩy `,`, gạch ngang `-`, hai chấm `:`, hoặc tự nhập).
4. Tùy chọn định dạng file xuất: **`.pdf`**, **`.docx`** hoặc **`.txt`**.
5. Nhấn **🔍 Xem Trước File Đã Chọn** để xem nhanh nội dung.
6. Nhấn **⚡ CHUYỂN ĐỔI TẤT CẢ FILE ⚡** để xuất file kết quả.

---

## 💻 Cách 2: Sử dụng Dòng Lệnh (CLI)

Chuyển đổi file PDF xuất ra PDF mới:
```bash
python doc_table_converter.py document.pdf -o document_converted.pdf --pdf -s " | "
```

Chuyển đổi file PDF xuất ra DOCX:
```bash
python doc_table_converter.py document.pdf -o document_converted.docx -s " | "
```

Xuất ra file Text (`.txt`):
```bash
python doc_table_converter.py document.pdf -o document_converted.txt --txt -s " | "
```

---

## 📁 Danh Sách File Trong Bộ Công Cụ

- **`gui_app.py`**: Giao diện ứng dụng đồ họa (Tkinter Desktop App - Kéo & Thả Hàng Loạt).
- **`doc_table_converter.py`**: Core engine xử lý chuyển đổi bảng PDF/Word In-place.
- **`test_converter.py`**: Script kiểm thử tự động file PDF & Word.
- **`run.bat`**: Script nhấp đúp chạy nhanh ứng dụng trên Windows.
- **`README.md`**: Hướng dẫn sử dụng chi tiết.

