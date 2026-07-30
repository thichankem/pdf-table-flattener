import docx
import sys
import os
from doc_table_converter import convert_doc_or_pdf_to_docx, process_document

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_path = "Sản phẩm cho vay CBNV trường đại học Quốc gia TP.Hồ Chí Minh - kênh quầy.docx.pdf"
text, doc = process_document(pdf_path)

print(f"Total paragraphs in doc: {len(doc.paragraphs)}")

found_31 = False
found_32 = False
found_1000 = False

for i, p in enumerate(doc.paragraphs):
    t = p.text.strip()
    if "3.1" in t:
        print(f"Paragraph {i}: {t[:120]}")
        found_31 = True
    if "3.2" in t:
        print(f"Paragraph {i}: {t[:120]}")
        found_32 = True
    if "1.000" in t:
        print(f"Paragraph {i}: {t[:120]}")
        found_1000 = True

print(f"\n3.1 found in python-docx: {found_31}")
print(f"3.2 found in python-docx: {found_32}")
print(f"1.000 found in python-docx: {found_1000}")
