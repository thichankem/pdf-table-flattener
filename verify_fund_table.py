import os
import sys
import docx
from doc_table_converter import convert_doc_or_pdf_to_docx, process_document

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_path = "Bảo hiểm nhân thọ - Lộc Phát Hưng Thịnh - Quy định sản phẩm.pdf"
full_text, doc = process_document(pdf_path)

print("=== INSPECTING FUND TABLE LINES IN CONVERTED DOC ===")

for p in doc.paragraphs:
    t = p.text.strip()
    if "Tên Quỹ" in t or "Quỹ Dẫn đầu" in t or "Quỹ Tài chính" in t:
        print(f"  • {t[:160]}...")
