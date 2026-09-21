"""Check every flagged doc for whether it has ANY real corruption,
or is a pure writing-style false positive."""
import json
import re
from pathlib import Path
from scratch.scan_garbled_regions import paragraph_is_garbled, MIN_WORDS_PER_PARAGRAPH, _WORD_RE

_SUSPECT = re.compile(r'[@%®]|[\u0980-\u09FF]')
CORPUS_PATH = Path("corpus/cuet/documents.jsonl")

with CORPUS_PATH.open(encoding="utf-8") as f:
    for line in f:
        doc = json.loads(line)
        text = doc.get("text", "")
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        judged = [p for p in paragraphs if len(_WORD_RE.findall(p)) >= MIN_WORDS_PER_PARAGRAPH]
        flagged = [p for p in judged if paragraph_is_garbled(p)]
        if not flagged:
            continue
        corrupt = sum(1 for p in flagged if _SUSPECT.search(p))
        style = len(flagged) - corrupt
        if corrupt == 0:
            print(f"*** PURE FALSE POSITIVE: {doc.get('doc_id')}  ({style} style-only, 0 corrupt)")
        else:
            print(f"    {doc.get('doc_id')}  corrupt={corrupt} style={style}")