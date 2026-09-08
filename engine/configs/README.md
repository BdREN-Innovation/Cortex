# Configs

Four config types, one per pipeline stage. Each is owned by exactly one team,
which is what lets several people tune several sites at once without ever
editing the same file.

```
engine crawl ──▶ engine extract ──▶ engine index ──▶ engine ask / eval
crawl.<site>     extract.<site>     index.<site>      eval.<site>
   Team A           Team B             Team B           Team C
```

| File | Drives | Owner | Documented in |
|---|---|---|---|
| `crawl.<site>.yaml` | fetching and saving bytes | Team A | [crawl.example.yaml](crawl.example.yaml) |
| `extract.<site>.yaml` | bytes → `documents.jsonl` | Team B | [extract.example.yaml](extract.example.yaml) |
| `index.<site>.yaml` | chunk, embed, store | Team B | [index.example.yaml](index.example.yaml) |
| `eval.<site>.yaml` | scoring against the golden set | Team C | [eval.example.yaml](eval.example.yaml) |

**Every `*.example.yaml` documents every knob it supports.** Copy the example,
rename it for your site, edit. `CODEOWNERS` assigns each pattern to its team.

---

## Naming

`<type>.<site>.yaml`, where `<site>` matches the `site:` field inside and
becomes the folder name under `data/`. So `crawl.bdren.yaml` with `site: bdren`
produces `data/sites/bdren/<run>/`.

**One config per site, one owner each.** Four people crawling four sites means
four config files and zero merge conflicts — nobody edits a shared module.
Do not write `scrape_site1.py`; put the differences here.

---

## Worked example, end to end

Using the bundled fixture site, which needs no network:

```bash
# 0. serve the fake site
python3 -m http.server 8765 --directory fixtures/site &

# 1. CAPTURE — Team A. Fetches and saves bytes. No text.
uv run engine crawl --config configs/crawl.acme.yaml
#    -> data/sites/acme/20260908T091500Z/
#         pages.jsonl, manifest.json, raw/, docs/

# 2. EXTRACT — Team B. Reads those bytes offline. Free to re-run.
uv run engine extract \
    --run data/sites/acme/20260908T091500Z \
    --config configs/extract.example.yaml \
    --min-text-chars 50
#    -> documents.jsonl (+ tables/) in the same folder

# 3. INDEX — Team B. Chunk, embed, store.
uv run engine index \
    --documents data/sites/acme/20260908T091500Z/documents.jsonl \
    --config configs/index.example.yaml
#    -> data/index/acme/<index_id>/

# 4a. ASK — a single question.
uv run engine ask "how long does a refund take" \
    --index data/index/acme/<index_id>

# 4b. EVAL — Team C. Score the whole golden dataset.
uv run engine eval \
    --dataset datasets/acme/golden.v1.yaml \
    --index   data/index/acme/<index_id> \
    --config  configs/eval.example.yaml
#    -> data/runs/<run_id>/report.md
```

`--min-text-chars 50` is needed for the fixture only: its pages are short, and
the 200-char default would drop them all as navigation.

---

## Config vs CLI flag

Anything that describes **how the pipeline behaves** goes in a config file, so
it is committed, reviewable, and reproducible.

Anything that is a **one-off for this invocation** is a CLI flag:

| Flag | Why it is not in a config |
|---|---|
| `--out` | where to write this particular comparison run |
| `--min-text-chars` | quick override while tuning |
| `--min-pass-rate` | a CI gate, not a property of the evaluation |
| `--provider`, `--model` | try a different model without editing a file |

CLI flags override the config file where both apply.

---

## Secrets never go here

`configs/` is **committed**. `engine/.env` is not.

```bash
# engine/.env  — copy from .env.example
QDRANT_URL=https://xyz.aws.cloud.qdrant.io:6333
QDRANT_API_KEY=...
OPENAI_API_KEY=...
```

A config may name a *collection* or a *provider*; it must never contain a key.

---

## The comparison configs

`extract.builtin.yaml`, `extract.pdfplumber.yaml` and `extract.docling.yaml`
are not per-site configs. They exist so Team B can run the same crawl through
three PDF parsers and diff the output:

```bash
uv run engine extract --run <run> --config configs/extract.builtin.yaml    --out builtin.jsonl
uv run engine extract --run <run> --config configs/extract.pdfplumber.yaml --out pdfplumber.jsonl
```

Whichever wins is an empirical fact about your sites' PDFs. Each file documents
what that parser costs and what it buys.

---

## Two traps

**`exclude_patterns` also applies to linked files.** A `"\.pdf$"` rule in a
crawl config silently switches off the entire PDF pipeline — no error, the PDFs
just never appear.

**`save_tables` does not control whether tables reach the index.** Tables are
*always* inlined into the document text as markdown, so they embed with the
paragraph that introduces them. The flag only mirrors a copy to `tables/` for
you to eyeball.
