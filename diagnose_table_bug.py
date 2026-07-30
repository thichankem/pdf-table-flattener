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
    if re.match(r'^(\([a-z0-9ivxlcdm]+\)|[a-z0-9]+\.|\([0-9]+\))$', s, re.IGNORECASE):
        return True
    return False

def is_likely_header_row(row):
    if not row or not any(row):
        return False
    if any(len(c) > 250 for c in row if c):
        return False
    first = row[0].strip()
    if re.match(r'^\d+(\.\d+)+\.?$', first):
        return False
    if is_bullet_marker(first):
        return False
    return True

def has_merged_cells_in_row(row, start_col=1):
    """Check if columns start_col..N have identical (merged) values."""
    if len(row) <= start_col:
        return False
    val1 = clean_text_string(row[start_col])
    for c in range(start_col + 1, len(row)):
        if clean_text_string(row[c]) != val1:
            return False
    return True

# Test with the problematic table
grid_scenario = [
    ['Điều kiện', 'Khoản phí đóng vào có thể đủ để duy trì hiệu lực của Hợp đồng bảo hiểm (Giá trị Tài khoản hợp đồng sau khi trừ (các) Khoản nợ (nếu có) lớn hơn 0) đến hết ngày liền trước Ngày đến hạn đóng phí tiếp theo', 'Khoản phí đóng vào có thể đủ để duy trì hiệu lực của Hợp đồng bảo hiểm (Giá trị Tài khoản hợp đồng sau khi trừ (các) Khoản nợ (nếu có) lớn hơn 0) đến hết ngày liền trước Ngày đến hạn đóng phí tiếp theo'],
    ['Tình huống', 'Thỏa điều kiện', 'Không thỏa điều kiện'],
    ['Thứ tự phân bổ phí', 'Đóng cho Phí bảo hiểm định kỳ đến hạn', 'Đóng cho Phí bảo hiểm cơ bản định kỳ đến hạn']
]

# Test with the Fund table (should be standard header)
grid_fund = [
    ['Tên Quỹ', 'Mục tiêu', 'Chính sách đầu tư', 'Rủi ro đầu tư', 'Lĩnh vực đầu tư'],
    ['Quỹ Dẫn đầu', 'Tăng trưởng cao từ trung đến dài hạn', 'Đầu tư chủ yếu vào các danh mục đầu tư bằng đồng Việt Nam có tiềm năng tăng trưởng vốn cao, đồng thời đầu tư vào các tài sản đầu tư có thu nhập ổn định.', 'Cao', '30 cổ phiếu hàng đầu có vốn hóa lớn nhất...'],
    ['Quỹ Tài chính năng động', 'Tăng trưởng cao từ trung đến dài hạn', 'Đầu tư chủ yếu vào các danh mục đầu tư bằng đồng Việt Nam...', 'Cao', 'Cổ phiếu đang được niêm yết...']
]

print("=== SCENARIO MATRIX TABLE ===")
print(f"is_likely_header_row(row0): {is_likely_header_row(grid_scenario[0])}")
print(f"has_merged_cells_in_row(row0): {has_merged_cells_in_row(grid_scenario[0])}")
print(f"len of row0 col1: {len(grid_scenario[0][1])}")

print("\n=== FUND TABLE ===")
print(f"is_likely_header_row(row0): {is_likely_header_row(grid_fund[0])}")
print(f"has_merged_cells_in_row(row0): {has_merged_cells_in_row(grid_fund[0])}")

print("\n=== KEY INSIGHT ===")
print("Scenario matrix: Row0 has MERGED cells (identical cols 1..N) -> should use vertical matrix logic")
print("Fund table: Row0 has DIFFERENT cells -> should use standard header logic")
print(f"\nFix: If row0 has merged cells OR any row has merged cells, use vertical matrix even if is_likely_header_row is True")
