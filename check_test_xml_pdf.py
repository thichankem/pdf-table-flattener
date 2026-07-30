import fitz

doc = fitz.open("test_xml_check.pdf")
all_txt = "\n".join(p.get_text("text") for p in doc)
print("3.2 in test_xml_check.pdf:", "3.2" in all_txt)
print("1.000 in test_xml_check.pdf:", "1.000" in all_txt)
print("3.1 in test_xml_check.pdf:", "3.1" in all_txt)
