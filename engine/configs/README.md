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

Copy the example, rename it for your site, edit. `CODEOWNERS` assigns each
pattern to its team.

**The example files are a starting shape, not a fixed schema.** The keys exist
because the pipeline has stages that need configuring, not because these are
the right knobs. Add, rename or drop them as your design needs — just keep the
YAML and the matching dataclass in step.

---

## Naming

`<type>.<site>.yaml`, where `<site>` matches the `site:` field inside and
becomes the folder name under `data/`. So `crawl.bdren.yaml` with `site: bdren`
produces `data/sites/bdren/<run>/`.

**One config per site, one owner each.** The two targets already have starter
crawl configs committed — `crawl.cuet.yaml` and `crawl.bdren.yaml` — with an
OWNER line to fill in on day one. Put the per-site differences in these files
rather than in code: nobody should be editing a shared module to fix one site,
and there is then nothing to merge at the end.

`crawl.acme.yaml` points at the bundled fixture site and is there to check your
crawler works before you aim it at a real one.

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
| `--gate-metric`, `--gate-min` | a CI gate, not a property of the evaluation |
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

## Two traps

**`exclude_patterns` also applies to linked files.** A `"\.pdf$"` rule in a
crawl config silently switches off the entire PDF pipeline — no error, the PDFs
just never appear.

**`save_tables` does not control whether tables reach the index.** Tables are
*always* inlined into the document text as markdown, so they embed with the
paragraph that introduces them. The flag only mirrors a copy to `tables/` for
you to eyeball.
