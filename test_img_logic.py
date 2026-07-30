import os
import sys
import re
import docx

def has_drawing(p: docx.text.paragraph.Paragraph) -> bool:
    xml = p._element.xml
    return ('w:drawing' in xml) or ('w:pict' in xml)

# Let's test checking drawings in a paragraph
print("Checking has_drawing helper")
