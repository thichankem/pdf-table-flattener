import sys
import fitz

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

original = "Sản phẩm cho vay CBNV trường đại học Quốc gia TP.Hồ Chí Minh - kênh quầy.docx.pdf"
converted = "output/Sản phẩm cho vay CBNV trường đại học Quốc gia TP.Hồ Chí Minh - kênh quầy.docx_convert.pdf"

# Extract all text from both
doc_orig = fitz.open(original)
orig_text = ""
for p in doc_orig:
    orig_text += p.get_text("text")
doc_orig.close()

doc_conv = fitz.open(converted)
conv_text = ""
for p in doc_conv:
    conv_text += p.get_text("text")
doc_conv.close()

# Find important phrases in original that might be missing in converted
important_phrases = [
    "3.1",
    "Đối tượng khách hàng",
    "3.2",
    "Điều kiện khách hàng",
    "3.3",
    "Điều kiện về đơn vị công tác",
    "3.4",
    "Phân nhóm khách hàng",
    "3.5",
    "Hạn mức thấu chi",
    "3.6",
    "Mục đích cấp hạn mức thấu chi",
    "3.7",
    "hạn duy trì HMTC",
    "3.8",
    "Đồng tiền thấu chi",
    "3.9",
    "kiện về hệ số trả nợ",
    "DTI",
    "3.10",
    "ng thức trả nợ",
    "3.11",
    "quyền quyết định",
    "3.12",
    "chỉnh HMTC",
    "3.13",
    "tái cấp HMTC",
    "3.14",
    "nợ quá hạn",
    "3.15",
    "vay vốn",
    "Nhóm chức danh",
    "HMTC (triệu đồng)",
    "1.000",
    "Số lần cấp HMTC theo TN lương",
]

print("=== KIỂM TRA NỘI DUNG BỊ THIẾU ===\n")
for phrase in important_phrases:
    in_orig = phrase.lower() in orig_text.lower()
    in_conv = phrase.lower() in conv_text.lower()
    status = "✅" if in_conv else "❌ THIẾU"
    if in_orig and not in_conv:
        print(f"  {status}: '{phrase}'")
    elif in_orig and in_conv:
        print(f"  ✅: '{phrase}'")

# Check table data specifically
print("\n=== KIỂM TRA DỮ LIỆU BẢNG ===")
table_data = ["1.000", "700", "200", "15", "12", "10"]
for d in table_data:
    in_conv = d in conv_text
    print(f"  {'✅' if in_conv else '❌ THIẾU'}: Giá trị bảng '{d}'")

# Count original pages vs converted pages
doc_orig = fitz.open(original)
doc_conv = fitz.open(converted)
print(f"\n=== SỐ TRANG ===")
print(f"  Gốc:    {len(doc_orig)} trang")
print(f"  Convert: {len(doc_conv)} trang")
doc_orig.close()
doc_conv.close()

# Check for specific content chunks that span table cells
print("\n=== KIỂM TRA BỊ CẮT NỘI DUNG GIỮA DÒNG ===")
# The original has multi-row table cells. Check if key text was truncated
truncation_checks = [
    ("Khách hàng là Cán bộ nhân viên", "Đối tượng KH bị cắt?"),
    ("không bao gồm lái xe, bảo vệ", "Chi tiết loại trừ bị cắt?"),
    ("Đối với cán bộ và công chức", "Chi tiết cán bộ công chức bị cắt?"),
    ("Đối với viên chức", "Chi tiết viên chức bị cắt?"),
    ("Đối với CBNV còn lại", "Chi tiết CBNV còn lại bị cắt?"),
    ("Tối đa 80%", "DTI 80% bị cắt?"),
    ("Bản sao Căn cước công dân", "Hồ sơ vay bị cắt?"),
]
for phrase, desc in truncation_checks:
    in_conv = phrase.lower() in conv_text.lower()
    print(f"  {'✅' if in_conv else '❌ THIẾU'}: {desc} - '{phrase[:50]}'")
