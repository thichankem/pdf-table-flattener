import os
import sys
import io
import docx
from PIL import Image, ImageFilter, ImageStat
from pdf2docx import Converter

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_name = "Bảo hiểm nhân thọ - Lộc Phát Hưng Thịnh - Quy định sản phẩm.pdf"
temp_docx = "temp_filter_img_f1.docx"

cv = Converter(pdf_name)
cv.convert(temp_docx)
cv.close()

doc = docx.Document(temp_docx)

def is_text_heavy_image(img_bytes: bytes) -> bool:
    try:
        img = Image.open(io.BytesIO(img_bytes)).convert('L')
        w, h = img.size
        # Header logos or small decorative icons (<400x200 or <80,000 pixels) -> False
        if w * h < 80000 and (w < 400 or h < 200):
            return False
        
        edges = img.filter(ImageFilter.FIND_EDGES)
        stat = ImageStat.Stat(edges)
        mean_edge = stat.mean[0]
        stddev_edge = stat.stddev[0]
        
        if mean_edge > 4.5 and stddev_edge > 9.0:
            return True
        return False
    except Exception:
        return True

def filter_paragraph_drawings(p: docx.text.paragraph.Paragraph) -> bool:
    drawings = p._element.xpath('.//w:drawing')
    has_valid_drawing = False
    
    for drawing in drawings:
        blips = drawing.xpath('.//a:blip/@r:embed')
        keep_drawing = False
        if blips:
            rId = blips[0]
            try:
                img_part = p.part.related_parts[rId]
                img_bytes = img_part.blob
                if is_text_heavy_image(img_bytes):
                    keep_drawing = True
            except Exception:
                keep_drawing = True
        
        if keep_drawing:
            has_valid_drawing = True
        else:
            drawing.getparent().remove(drawing)
            
    return has_valid_drawing

print("=== TESTING PARAGRAPH DRAWING FILTERING ON FILE 1 ===")
removed_count = 0
kept_count = 0

for p_i, p in enumerate(doc.paragraphs):
    if 'w:drawing' in p._element.xml:
        had = filter_paragraph_drawings(p)
        if had:
            kept_count += 1
            print(f"Paragraph {p_i}: ✅ KEPT text-heavy diagram image!")
        else:
            removed_count += 1
            print(f"Paragraph {p_i}: 🗑️ REMOVED logo/background image!")

print(f"\nTotal kept text diagrams: {kept_count}, Total removed background logos: {removed_count}")

if os.path.exists(temp_docx):
    os.remove(temp_docx)
