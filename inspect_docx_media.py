import os
import sys
import zipfile
import docx
from pdf2docx import Converter

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_name = "Bảo hiểm nhân thọ - Lộc Phát Tràng An - Quy định sản phẩm.pdf"
temp_docx = "temp_inspect_media.docx"

cv = Converter(pdf_name)
cv.convert(temp_docx)
cv.close()

# Extract media files from docx zip
media_files = []
with zipfile.ZipFile(temp_docx, 'r') as z:
    for filename in z.namelist():
        if filename.startswith('word/media/'):
            media_files.append(filename)

print(f"Total media files in {pdf_name}: {len(media_files)}")
for m in media_files[:10]:
    print(f"  Media: {m}")

if os.path.exists(temp_docx):
    os.remove(temp_docx)
