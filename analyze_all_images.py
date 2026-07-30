import os
import sys
import zipfile
from PIL import Image
from pdf2docx import Converter

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_files = [
    "Bảo hiểm nhân thọ - Lộc Phát Hưng Thịnh - Quy định sản phẩm.pdf",
    "Bảo hiểm nhân thọ - Lộc Phát Tràng An - Quy định sản phẩm.pdf",
    "Sản phẩm cho vay CBNV trường đại học Quốc gia TP.Hồ Chí Minh - kênh quầy.docx.pdf",
    "Sản phẩm cho vay kinh doanh xi măng Xuân Thành - Kênh quầy.docx.pdf",
    "Sản phẩm cho vay tái tài trợ - kênh quầy.docx.pdf"
]

output_inspect_dir = "extracted_images_inspect"
os.makedirs(output_inspect_dir, exist_ok=True)

for idx, pdf_name in enumerate(pdf_files, 1):
    print(f"\n==================================================")
    print(f"ANALYZING IMAGES IN FILE {idx}: {pdf_name}")
    print(f"==================================================")
    
    temp_docx = f"temp_media_{idx}.docx"
    cv = Converter(pdf_name)
    cv.convert(temp_docx)
    cv.close()
    
    img_idx = 0
    with zipfile.ZipFile(temp_docx, 'r') as z:
        for filename in z.namelist():
            if filename.startswith('word/media/'):
                img_data = z.read(filename)
                img_name = f"file{idx}_img{img_idx}_{os.path.basename(filename)}"
                save_path = os.path.join(output_inspect_dir, img_name)
                with open(save_path, "wb") as f:
                    f.write(img_data)
                
                # Analyze image with PIL
                img = Image.open(save_path)
                w, h = img.size
                mode = img.mode
                
                # Calculate color variance / unique colors or aspect ratio
                colors = img.getcolors(maxcolors=10000)
                num_colors = len(colors) if colors else ">10000"
                
                print(f"  • {img_name}: Size = {w}x{h}, Mode = {mode}, Colors = {num_colors}")
                img_idx += 1
                
    if os.path.exists(temp_docx):
        os.remove(temp_docx)
