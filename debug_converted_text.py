import fitz
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_path = "output/Sản phẩm cho vay CBNV trường đại học Quốc gia TP.Hồ Chí Minh - kênh quầy.docx_convert.pdf"
doc = fitz.open(pdf_path)

print(f"Total pages in converted PDF: {len(doc)}")
for i, p in enumerate(doc):
    t = p.get_text("text")
    print(f"\n--- PAGE {i+1} ({len(t)} chars) ---")
    for line in t.splitlines():
        if any(k in line for k in ["3.1", "3.2", "1.000", "700", "200", "STT", "Chức danh", "đối tượng", "Điều kiện"]):
            print(f"  MATCH: {line[:120]}")
