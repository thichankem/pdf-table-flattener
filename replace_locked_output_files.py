import os
import shutil
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

output_dir = "output"
for fname in os.listdir(output_dir):
    if fname.endswith("_new.pdf"):
        orig_name = fname.replace("_new.pdf", ".pdf")
        orig_path = os.path.join(output_dir, orig_name)
        new_path = os.path.join(output_dir, fname)
        
        try:
            if os.path.exists(orig_path):
                os.remove(orig_path)
            os.rename(new_path, orig_path)
            print(f"  ✅ Đã cập nhật file PDF mới nhất: {orig_name}")
        except Exception as e:
            print(f"  ⚠️ Không thể đè file {orig_name} do đang bị mở bởi phần mềm xem PDF: {e}")
