import sys
import fitz
import re

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

original = "Sản phẩm cho vay CBNV trường đại học Quốc gia TP.Hồ Chí Minh - kênh quầy.docx.pdf"
converted = "output/Sản phẩm cho vay CBNV trường đại học Quốc gia TP.Hồ Chí Minh - kênh quầy.docx_convert.pdf"

print("=" * 80)
print("=== FILE GỐC - TOÀN BỘ NỘI DUNG ===")
print("=" * 80)
doc_orig = fitz.open(original)
for i, page in enumerate(doc_orig):
    text = page.get_text("text")
    print(f"\n--- TRANG {i+1} ---")
    print(text[:3000] if text else "(trống)")
doc_orig.close()

print("\n\n")
print("=" * 80)
print("=== FILE CONVERT - TOÀN BỘ NỘI DUNG ===")
print("=" * 80)
doc_conv = fitz.open(converted)
for i, page in enumerate(doc_conv):
    text = page.get_text("text")
    print(f"\n--- TRANG {i+1} ---")
    print(text[:3000] if text else "(trống)")
doc_conv.close()
