import sys
import re

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def clean_text_string(text: str) -> str:
    if not text:
        return ""
    t = text.replace('\xa0', ' ').replace('\u200b', '').replace('\ufeff', '').replace('\x00', '').replace('\x0c', '')
    lines = [re.sub(r'[ \t]+', ' ', l).strip() for l in t.splitlines() if l.strip()]
    return " ".join(lines).strip()

def is_bullet_marker(text: str) -> bool:
    s = text.strip().lower()
    if not s or s in ['•', '▪', '*', '-', '+', '–', '—', '(v)', '(i)', '(ii)', '(iii)', '(iv)', 'a.', 'b.', 'c.', 'd.']:
        return True
    if re.match(r'^[-—–\.\*\•\+\s]+$', s):
        return True
    if re.match(r'^(\([a-z0-9ivxlcdm]+\)|[a-z0-9]\.|[0-9]+(\.[0-9]+)*\.?|\([0-9]+\))$', s, re.IGNORECASE):
        return True
    return False

grid_t18 = [
    ['Điều kiện', 'Khoản phí đóng vào có thể đủ để duy trì hiệu lực của Hợp đồng bảo hiểm (Giá trị Tài khoản hợp đồng sau khi trừ (các) Khoản nợ (nếu có) lớn hơn 0) đến hết ngày liền trước Ngày đến hạn đóng phí tiếp theo hoặc Ngày đáo hạn hợp đồng', 'Khoản phí đóng vào có thể đủ để duy trì hiệu lực của Hợp đồng bảo hiểm (Giá trị Tài khoản hợp đồng sau khi trừ (các) Khoản nợ (nếu có) lớn hơn 0) đến hết ngày liền trước Ngày đến hạn đóng phí tiếp theo hoặc Ngày đáo hạn hợp đồng'],
    ['Tình huống', 'Thỏa điều kiện', 'Không thỏa điều kiện'],
    ['Thứ tự phân bổ phí', '▪ Đóng cho Phí bảo hiểm của Sản phẩm bán kèm định kỳ đến hạn\n▪ Đóng cho Phí bảo hiểm cơ bản định kỳ đến hạn', '▪ Đóng cho Phí bảo hiểm cơ bản định kỳ đến hạn']
]

def format_grid_smart(grid, separator=" | ", bullet_prefix=True):
    num_rows = len(grid)
    num_cols = max(len(r) for r in grid) if grid else 0
    prefix_str = "- " if bullet_prefix else ""
    lines = []

    # Check if Column 0 contains row labels/categories
    col0_is_labels = True
    for r in grid:
        val0 = clean_text_string(r[0]) if len(r) > 0 else ""
        if not val0 or is_bullet_marker(val0) or len(val0) > 80:
            col0_is_labels = False
            break

    if col0_is_labels and num_cols > 1 and num_rows > 1:
        # Check which rows have identical values across all columns 1..N
        common_rows = []
        varying_rows = []
        
        for r_i, r in enumerate(grid):
            val1 = clean_text_string(r[1]) if len(r) > 1 else ""
            all_same = True
            for c_i in range(2, num_cols):
                val_c = clean_text_string(r[c_i]) if c_i < len(r) else ""
                if val_c != val1:
                    all_same = False
                    break
            if all_same:
                common_rows.append(r_i)
            else:
                varying_rows.append(r_i)
                
        # Output common rows first
        for r_i in common_rows:
            k = clean_text_string(grid[r_i][0])
            v = clean_text_string(grid[r_i][1]) if len(grid[r_i]) > 1 else ""
            if k and v:
                lines.append(f"{prefix_str}{k}: {v}")
            elif v:
                lines.append(f"{prefix_str}{v}")
                
        # Output varying scenario columns
        if varying_rows:
            for c_i in range(1, num_cols):
                col_parts = []
                for r_i in varying_rows:
                    k = clean_text_string(grid[r_i][0])
                    v = clean_text_string(grid[r_i][c_i]) if c_i < len(grid[r_i]) else ""
                    if k and v:
                        col_parts.append(f"{k}: {v}")
                    elif v:
                        col_parts.append(v)
                if col_parts:
                    lines.append(f"{prefix_str}{separator.join(col_parts)}")
                    
        return "\n".join(lines)

    return "Standard format fallback"

res = format_grid_smart(grid_t18)
print("=== KẾT QUẢ ĐỊNH DẠNG BẢNG ĐẶC BIỆT ===")
print(res)
