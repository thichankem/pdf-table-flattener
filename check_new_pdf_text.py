import fitz
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_path = "output/Sản phẩm cho vay CBNV trường đại học Quốc gia TP.Hồ Chí Minh - kênh quầy.docx_convert_new.pdf"
doc = fitz.open(pdf_path)

all_txt = "\n".join(p.get_text("text") for p in doc)

print(f"=== CHECKING NEW PDF ({len(doc)} pages) ===")
for phrase in ["3.1", "3.2", "3.3", "3.4", "3.5", "1.000", "700", "200", "15", "12", "10", "không bao gồm lái xe", "đối tượng khách hàng"]:
    found = phrase.lower() in all_txt.lower()
    print(f"  {'✅' if found else '❌ MISSING'}: '{phrase}'")
