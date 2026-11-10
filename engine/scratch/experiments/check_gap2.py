import pdfplumber

def print_gaps(page, target):
    chars = page.chars
    buf = ''
    start_idx = None
    for i, c in enumerate(chars):
        buf = (buf + c['text'].upper())[-len(target):]
        if buf == target:
            start_idx = i - len(target) + 1
            break
    if start_idx is None:
        print(f'{target}: not found on this page')
        return
    region = chars[start_idx:start_idx + len(target)]
    print(f'--- {target} ---')
    for i in range(1, len(region)):
        gap = region[i]['x0'] - region[i - 1]['x1']
        print(region[i - 1]['text'], '->', region[i]['text'], ': gap=', round(gap, 3))
    print()

with pdfplumber.open('corpus/cuet/_files/de1bedf5__69e479fa7ce5b.pdf') as pdf:
    for page in pdf.pages:
        text = page.extract_text() or ''
        if 'EXCLUDES3WEEKSOFINDUSTRIALTRAINING' in text.upper().replace(' ', ''):
            print_gaps(page, 'WEEKSOFINDUSTRIALTRAINING')
        if 'PHASEDIAGRAMSANDTRANSFORMATIONS' in text.upper().replace(' ', ''):
            print_gaps(page, 'ANDTRANSFORMATIONS')