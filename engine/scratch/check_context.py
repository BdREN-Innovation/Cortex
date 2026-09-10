import re
from engine.knowledge.parsers import parse_pdf

path = 'corpus/cuet/_files/de1bedf5__69e479fa7ce5b.pdf'
result = parse_pdf(path, engine='pdfplumber_positioned')
text = result['text']

for term in ['TOTALCREDITS', 'DEPTCORESUBJECT', 'RELATEDENGINEERING', 'WEEKSOFINDUSTRIALTRAINING', 'ANDTRANSFORMATIONS']:
    idx = text.find(term)
    if idx != -1:
        context = text[max(0, idx - 60):idx + 60]
        print(f'--- {term} ---')
        print(repr(context))
        print()