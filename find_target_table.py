import os
import sys
import docx
from doc_table_converter import convert_doc_or_pdf_to_docx, clean_table_grid

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_files = [
    "Bảo hiểm nhân thọ - Lộc Phát Hưng Thịnh - Quy định sản phẩm.pdf",
    "Bảo hiểm nhân thọ - Lộc Phát Tràng An - Quy định sản phẩm.pdf"
]

for idx, pdf_name in enumerate(pdf_files, 1):
    docx_path, is_tmp = convert_doc_or_pdf_to_docx(pdf_name)
    doc = docx.Document(docx_path)
    
    print(f"\n==================================================")
    print(f"SEARCHING FOR 'Thứ tự phân bổ phí' IN FILE {idx}: {pdf_name}")
    print(f"==================================================")
    
    for t_i, table in enumerate(doc.tables, 1):
        grid = clean_table_grid(table)
        grid_str = " ".join(" ".join(r) for r in grid)
        if "Thứ tự phân bổ phí" in grid_str or "Tình huống" in grid_str:
            print(f"Found target table at Table {t_i}! (Rows: {len(grid)}, Cols: {max(len(r) for r in grid) if grid else 0})")
            for r_i, r in enumerate(grid):
                print(f"  Row {r_i}: {r}")
                
    if is_tmp and os.path.exists(docx_path):
        os.remove(docx_path)
