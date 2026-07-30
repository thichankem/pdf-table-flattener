import re

def is_bullet_marker(text: str) -> bool:
    s = text.strip().lower()
    if not s or s in ['•', '▪', '*', '-', '+', '–', '—', '(v)', '(i)', '(ii)', '(iii)', '(iv)', 'a.', 'b.', 'c.', 'd.']:
        return True
    if re.match(r'^[-—–\.\*\•\+\s]+$', s):
        return True
    # Require a dot or parenthesis for number bullets: '1.', '2.', '(1)', '(a)'
    # Plain '0', '1', '2' without dot are NOT bullet markers!
    if re.match(r'^(\([a-z0-9ivxlcdm]+\)|[a-z0-9]+\.|\([0-9]+\))$', s, re.IGNORECASE):
        return True
    return False

def is_likely_header_row(row: list[str]) -> bool:
    if not row or not any(row):
        return False
    # Allow descriptive header cells up to 200 chars
    if any(len(c) > 200 for c in row if c):
        return False
    first = row[0].strip()
    if re.match(r'^\d+(\.\d+)+\.?$', first):
        return False
    if is_bullet_marker(first):
        return False
    return True

grid_713 = [
    ['Tuổi của Người được bảo hiểm chính tại thời điểm tử vong hoặc bị Thương tật toàn bộ và vĩnh viễn', 'Tỷ lệ phần trăm (%) của Số tiền bảo hiểm'],
    ['0', '25%'],
    ['1', '50%'],
    ['2', '75%']
]

print("=== TESTING TABLE 713 FIX ===")
print("is_likely_header_row(grid_713[0]):", is_likely_header_row(grid_713[0]))
print("is_bullet_marker('0'):", is_bullet_marker('0'))
print("is_bullet_marker('1.'):", is_bullet_marker('1.'))
