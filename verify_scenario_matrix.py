import sys
from doc_table_converter import process_document

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_path = "Bảo hiểm nhân thọ - Lộc Phát Hưng Thịnh - Quy định sản phẩm.pdf"
full_text, doc = process_document(pdf_path)

print("=== CHECKING SCENARIO MATRIX TABLE OUTPUT ===")
for p in doc.paragraphs:
    t = p.text.strip()
    if "Tình huống" in t or "Thứ tự phân bổ phí" in t or "Điều kiện:" in t:
        print(f"  • {t[:200]}")
