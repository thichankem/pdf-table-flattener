import os
import sys
import docx
from pdf2docx import Converter
from doc_table_converter import process_document

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_files = [
    "Bảo hiểm nhân thọ - Lộc Phát Hưng Thịnh - Quy định sản phẩm.pdf",
    "Bảo hiểm nhân thọ - Lộc Phát Tràng An - Quy định sản phẩm.pdf",
    "Sản phẩm cho vay CBNV trường đại học Quốc gia TP.Hồ Chí Minh - kênh quầy.docx.pdf",
    "Sản phẩm cho vay kinh doanh xi măng Xuân Thành - Kênh quầy.docx.pdf",
    "Sản phẩm cho vay tái tài trợ - kênh quầy.docx.pdf"
]

for idx, pdf_name in enumerate(pdf_files, 1):
    print(f"\n==================================================")
    print(f"COMPARING IMAGES BEFORE/AFTER FOR FILE {idx}: {pdf_name}")
    print(f"==================================================")
    
    # 1. Before
    temp_docx = f"temp_orig_{idx}.docx"
    cv = Converter(pdf_name)
    cv.convert(temp_docx)
    cv.close()
    
    doc_orig = docx.Document(temp_docx)
    orig_drawings = doc_orig._body._element.xml.count('w:drawing')
    orig_shapes = len(doc_orig.inline_shapes)
    
    # 2. After process_document
    _, doc_out = process_document(pdf_name)
    out_drawings = doc_out._body._element.xml.count('w:drawing')
    out_shapes = len(doc_out.inline_shapes)
    
    print(f"  • Ban đầu: Shapes = {orig_shapes}, XML <w:drawing> = {orig_drawings}")
    print(f"  • Sau khi convert: Shapes = {out_shapes}, XML <w:drawing> = {out_drawings}")
    if orig_drawings != out_drawings or orig_shapes != out_shapes:
        print(f"  ❌ CẢNH BÁO: BỊ MẤT {orig_drawings - out_drawings} HÌNH ẢNH / DRAWINGS!")
    else:
        print(f"  ✅ GIỮ NGUYÊN 100% HÌNH ẢNH / DRAWINGS!")
        
    if os.path.exists(temp_docx):
        os.remove(temp_docx)
