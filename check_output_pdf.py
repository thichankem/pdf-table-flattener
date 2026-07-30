import fitz
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_path = "output/Sản phẩm cho vay CBNV trường đại học Quốc gia TP.Hồ Chí Minh - kênh quầy.docx_convert.pdf"
doc = fitz.open(pdf_path)

print(f"=== PAGES IN {pdf_path}: {len(doc)} ===")
for i, p in enumerate(doc):
    txt = p.get_text("text")
    print(f"\n--- PAGE {i+1} ({len(txt)} chars) ---")
    lines = txt.splitlines()
    for l in lines:
        if any(k in l for k in ["3.1", "3.2", "1.000", "700", "200", "STT", "Đối tượng", "Điều kiện"]):
            print(f"  --> {l}")

print("\n=== IS '3.2' IN CONVERTED PDF? ===")
all_txt = "\n".join(p.get_text("text") for p in doc)
print("3.2 in all_txt:", "3.2" in all_txt)
print("1.000 in all_txt:", "1.000" in all_txt)
