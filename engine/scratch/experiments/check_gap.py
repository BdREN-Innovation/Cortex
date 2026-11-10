import pdfplumber

with pdfplumber.open('corpus/cuet/_files/de1bedf5__69e479fa7ce5b.pdf') as pdf:
    for page in pdf.pages:
        text = page.extract_text() or ''
        if 'TOTALCREDITS' in text.upper().replace(' ', ''):
            chars = page.chars
            target = 'TOTALCREDITS'
            buf = ''
            start_idx = None
            for i, c in enumerate(chars):
                buf = (buf + c['text'].upper())[-len(target):]
                if buf == target:
                    start_idx = i - len(target) + 1
                    break
            if start_idx is not None:
                region = chars[start_idx:start_idx + len(target)]
                for i in range(1, len(region)):
                    gap = region[i]['x0'] - region[i - 1]['x1']
                    print(region[i - 1]['text'], '->', region[i]['text'], ': gap=', round(gap, 3))
            break