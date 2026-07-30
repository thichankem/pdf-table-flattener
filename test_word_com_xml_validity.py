import win32com.client
import os
import sys
import docx
from doc_table_converter import convert_doc_or_pdf_to_docx, process_document

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pdf_path = "Sản phẩm cho vay CBNV trường đại học Quốc gia TP.Hồ Chí Minh - kênh quầy.docx.pdf"
text, doc = process_document(pdf_path)

test_docx = os.path.abspath("test_xml_check.docx")
test_pdf = os.path.abspath("test_xml_check.pdf")

doc.save(test_docx)

print("Opening test_xml_check.docx with Word COM...")
word = win32com.client.Dispatch("Word.Application")
word.Visible = False
try:
    wdoc = word.Documents.Open(test_docx)
    print(f"Word opened doc successfully! Paragraphs count according to Word: {wdoc.Paragraphs.Count}")
    
    # Check text of Word paragraphs
    for i in range(1, min(wdoc.Paragraphs.Count + 1, 40)):
        ptxt = wdoc.Paragraphs(i).Range.Text.strip()
        if ptxt:
            print(f"Word P{i}: {ptxt[:100]}")

    wdoc.SaveAs2(test_pdf, FileFormat=17)
    wdoc.Close()
finally:
    word.Quit()

print("\nFinished Word COM check.")
