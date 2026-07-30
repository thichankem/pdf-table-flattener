import os
import sys
import docx
from pdf2docx import Converter

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_name = "Bảo hiểm nhân thọ - Lộc Phát Hưng Thịnh - Quy định sản phẩm.pdf"
temp_docx = "temp_inspect_713.docx"

cv = Converter(pdf_name)
cv.convert(temp_docx)
cv.close()

doc = docx.Document(temp_docx)

print("=== INSPECTING ALL TABLES IN FILE 1 ===")

for t_idx, table in enumerate(doc.tables):
    grid = []
    for r in table.rows:
        row_vals = [cell.text.strip().replace('\n', ' ') for cell in r.cells]
        grid.append(row_vals)
        
    for r in grid:
        if any("Tỷ lệ phần trăm (%)" in cell for cell in r) or any("Giới hạn về quyền lợi" in cell for cell in r) or any("25%" in cell for cell in r):
            print(f"\n--- FOUND TARGET TABLE {t_idx} ---")
            for r_i, r_data in enumerate(grid):
                print(f"  Row {r_i}: {r_data}")

if os.path.exists(temp_docx):
    os.remove(temp_docx)
