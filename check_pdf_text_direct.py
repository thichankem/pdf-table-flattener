import fitz
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_path = "output/Sản phẩm cho vay CBNV trường đại học Quốc gia TP.Hồ Chí Minh - kênh quầy.docx_convert.pdf"
doc = fitz.open(pdf_path)

print(f"=== FULL TEXT OF CONVERTED PDF ({len(doc)} pages) ===")
full_text = ""
for i, page in enumerate(doc):
    t = page.get_text("text")
    print(f"\n--- PAGE {i+1} ---")
    print(t)
    full_text += t

print("\n=== SEARCH CHECKS ===")
for query in ["3.1", "3.2", "3.3", "1.000", "700", "200", "15", "12", "10", "không bao gồm lái xe", "đối tượng khách hàng"]:
    found = query.lower() in full_text.lower()
    print(f"  {'✅' if found else '❌ MISSING'}: '{query}'")
