import os
import sys
from PIL import Image, ImageFilter, ImageStat

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

inspect_dir = "extracted_images_inspect"

def image_has_text(img_path: str) -> bool:
    """
    Detects if an image contains substantial text (e.g. diagrams, flowcharts, infographics)
    vs decorative background/logo/graphics with no text.
    """
    try:
        img = Image.open(img_path).convert('L')
        w, h = img.size
        
        # Small icons/header logos (< 400x200 or < 80,000 pixels) usually don't contain content text
        if w * h < 80000 and (w < 400 or h < 200):
            return False
            
        # Perform edge detection to analyze high-contrast text strokes
        edges = img.filter(ImageFilter.FIND_EDGES)
        stat = ImageStat.Stat(edges)
        mean_edge = stat.mean[0]
        stddev_edge = stat.stddev[0]
        
        # High edge variance + large image dimensions indicate text/diagram content!
        if mean_edge > 5.0 and stddev_edge > 10.0:
            return True
            
        return False
    except Exception as e:
        return True  # Fallback: keep if unsure

print("=== TESTING IMAGE TEXT DETECTOR ON EXTRACTED IMAGES ===")

for fname in sorted(os.listdir(inspect_dir)):
    fpath = os.path.join(inspect_dir, fname)
    if os.path.isfile(fpath) and fname.endswith('.png'):
        has_txt = image_has_text(fpath)
        img = Image.open(fpath)
        status = "✅ CÓ CHỮ (GIỮ)" if has_txt else "🗑️ KHÔNG CHỮ / LOGO / DECORATION (XÓA)"
        print(f"  • {fname} ({img.width}x{img.height}): {status}")
