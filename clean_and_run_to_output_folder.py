import os
import sys
import shutil
import docx
from doc_table_converter import convert_file

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

root_dir = os.path.abspath(os.path.dirname(__file__))

original_pdf_names = {
    "Bảo hiểm nhân thọ - Lộc Phát Hưng Thịnh - Quy định sản phẩm.pdf",
    "Bảo hiểm nhân thọ - Lộc Phát Tràng An - Quy định sản phẩm.pdf",
    "Sản phẩm cho vay CBNV trường đại học Quốc gia TP.Hồ Chí Minh - kênh quầy.docx.pdf",
    "Sản phẩm cho vay kinh doanh xi măng Xuân Thành - Kênh quầy.docx.pdf",
    "Sản phẩm cho vay tái tài trợ - kênh quầy.docx.pdf"
}

output_dir = os.path.join(root_dir, "output")
os.makedirs(output_dir, exist_ok=True)

print("==================================================")
print("=== DỌN DẸP THƯ MỤC GỐC & CHUYỂN TOÀN BỘ SANG OUTPUT ===")
print("==================================================\n")

# 1. Clean up generated files in root_dir except original PDFs and code
deleted_count = 0
for fname in os.listdir(root_dir):
    fpath = os.path.join(root_dir, fname)
    if os.path.isfile(fpath):
        ext = os.path.splitext(fname)[1].lower()
        is_temp_file = False
        if ext in [".pdf", ".docx", ".doc", ".txt"] and fname not in original_pdf_names:
            is_temp_file = True
        elif ext == ".py" and any(fname.startswith(prefix) for prefix in ["test_", "inspect_", "check_", "verify_", "compare_", "diagnose_", "debug_"]):
            is_temp_file = True
            
        if is_temp_file:
            try:
                os.remove(fpath)
                print(f"  🗑️ Đã xóa file rác rưởi: {fname}")
                deleted_count += 1
            except Exception as e:
                print(f"  ⚠️ Không thể xóa {fname}: {e}")

# 2. Clean up temporary test output folders
for folder_name in ["test_outputs", "test_outputs_pdf"]:
    folder_path = os.path.join(root_dir, folder_name)
    if os.path.exists(folder_path):
        try:
            shutil.rmtree(folder_path)
            print(f"  🗑️ Đã xóa thư mục tạm: {folder_name}")
        except Exception as e:
            print(f"  ⚠️ Không thể xóa {folder_name}: {e}")

print(f"\nĐã dọn dẹp xong {deleted_count} file rác trong thư mục gốc.\n")

# 3. Convert all 5 original PDF files into the output/ folder
print("==================================================")
print("=== CHẠY CONVERT 5 FILE PDF VÀO THƯ MỤC OUTPUT ===")
print("==================================================\n")

pdf_files = list(original_pdf_names)
pdf_files.sort()

for idx, pdf_name in enumerate(pdf_files, 1):
    pdf_path = os.path.join(root_dir, pdf_name)
    base_name, _ = os.path.splitext(pdf_name)
    out_pdf_name = f"{base_name}_convert.pdf"
    out_pdf_path = os.path.join(output_dir, out_pdf_name)
    
    print(f"[{idx}/5] Đang xử lý: {pdf_name}")
    try:
        convert_file(
            file_path=pdf_path,
            output_path=out_pdf_path,
            export_pdf=True,
            separator=" | ",
            bullet_prefix=True
        )
        pdf_size_kb = os.path.getsize(out_pdf_path) / 1024
        print(f"  ✅ Đã xuất kết quả PDF gọn gàng tại: output/{out_pdf_name} ({pdf_size_kb:.1f} KB)\n")
    except Exception as err:
        print(f"  ❌ Lỗi khi convert {pdf_name}: {err}\n")

print("==================================================")
print("🎉 DỌN DẸP SẠCH SẼ & ĐÃ XUẤT GỌN GÀNG TẤT CẢ 5 FILE VÀO THƯ MỤC /output !")
print("==================================================")
