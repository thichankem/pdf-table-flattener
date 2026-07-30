import os
import sys
import docx
from doc_table_converter import process_document

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_path = "Bảo hiểm nhân thọ - Lộc Phát Hưng Thịnh - Quy định sản phẩm.pdf"
full_text, doc = process_document(pdf_path)

print("=== CHECKING TABLE 7.1.3 OUTPUT IN CONVERTED DOC ===")

found = False
for p in doc.paragraphs:
    t = p.text.strip()
    if "7.1.3" in t or "Tuổi của Người được bảo hiểm chính" in t or ("25%" in t and "50%" in t) or ("25%" in t and "Tuổi" in t):
        print(f"  • {t}")
        found = True

if not found:
    print("Searching for lines containing 25%...")
    for p in doc.paragraphs:
        t = p.text.strip()
        if "25%" in t:
            print(f"  • {t}")
