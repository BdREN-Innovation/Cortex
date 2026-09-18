import pdfplumber

with pdfplumber.open('corpus/cuet/_files/de1bedf5__69e479fa7ce5b.pdf') as pdf:
    for page in pdf.pages:
        text = page.extract_text() or ''
        if 'PHASEDIAGRAMSANDTRANSFORMATIONS' in text.upper().replace(' ', ''):
            for tol in [3, 2, 1.5, 1]:
                words = page.extract_words(x_tolerance=tol)
                hits = [w['text'] for w in words if 'TRANSFORMATIONS' in w['text'].upper()]
                print(f'x_tolerance={tol}:', hits)
            break