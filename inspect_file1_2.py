import os
import sys
import docx

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

output_dir = "test_outputs"
pdf_files = [
    "Bảo hiểm nhân thọ - Lộc Phát Hưng Thịnh - Quy định sản phẩm.pdf",
    "Bảo hiểm nhân thọ - Lộc Phát Tràng An - Quy định sản phẩm.pdf"
]

for idx, pdf_name in enumerate(pdf_files, 1):
    out_docx = os.path.join(output_dir, f"out_{idx}.docx")
    print(f"\n==================================================")
    print(f"FILE {idx}: {pdf_name}")
    print(f"==================================================")
    doc = docx.Document(out_docx)
    
    for i, p in enumerate(doc.paragraphs):
        t = p.text.strip()
        if t.startswith("- "):
            print(f"[{i:03d}]: {t}")
