import sys
import fitz

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_path = "Sản phẩm cho vay CBNV trường đại học Quốc gia TP.Hồ Chí Minh - kênh quầy.docx.pdf"
doc = fitz.open(pdf_path)

print("=== PHÂN TÍCH CẤU TRÚC BẢNG TRONG FILE GỐC ===\n")
for page_idx in range(len(doc)):
    page = doc[page_idx]
    tables = page.find_tables()
    if tables.tables:
        for t_idx, table in enumerate(tables.tables):
            print(f"--- Trang {page_idx+1}, Bảng {t_idx+1} ---")
            print(f"  Vị trí: {table.bbox}")
            print(f"  Số hàng: {table.row_count}, Số cột: {table.col_count}")
            grid = table.extract()
            for r_idx, row in enumerate(grid):
                row_display = []
                for c_idx, cell in enumerate(row):
                    if cell:
                        cell_clean = cell.replace('\n', ' ').strip()
                        if len(cell_clean) > 60:
                            cell_clean = cell_clean[:57] + "..."
                    else:
                        cell_clean = "(trống)"
                    row_display.append(cell_clean)
                print(f"  Hàng {r_idx}: {' | '.join(row_display)}")
            print()

doc.close()
