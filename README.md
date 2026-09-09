# Cortex

Give it a URL. It crawls the site, cleans and chunks what it finds, embeds it
into a vector database, and answers questions about it with citations.

The first two targets are **cuet.ac.bd** and **bdren.net.bd**.

```
   a URL
     │
     ▼
  ┌────────┐   pages.jsonl   ┌─────────┐  documents.jsonl  ┌────────┐
  │ crawl  │ ──────────────▶ │ extract │ ────────────────▶ │ index  │ ──▶ Qdrant
  └────────┘   raw bytes     └─────────┘   clean text      └────────┘        │
    Team A                     Team B                        Team B          │
                                                                             │
                                   ┌─────────────────────────────────────────┘
                                   ▼
                             ┌──────────┐                   ┌──────────┐
                             │   ask    │                   │   eval   │
                             └──────────┘                   └──────────┘
                       answer + citations                    scorecard
                             Team B                            Team C
```

> **This repository is a scaffold, not a finished system.** Every function under
> `engine/src/engine/` raises `NotImplementedError`. Three teams build it over
> 15 days. The docstrings and the shared contracts are the specification.

---

## 1. Setup

### Install uv

Everything runs through [uv](https://docs.astral.sh/uv/). It manages the Python
interpreter, the virtualenv and the dependency lock — you never run `pip`,
`venv` or `python -m` directly.

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

uv --version        # 0.12 or newer
```

### Set up the project

```bash
git clone <this-repo> Cortex
cd Cortex/engine
uv sync --extra dev
```

That single command:

- reads `.python-version` (**3.12**) and downloads that interpreter if needed —
  you do not have to install Python yourself
- creates `.venv/` inside `engine/`
- installs every dependency at the **exact version pinned in `uv.lock`**
- adds the `dev` extra (black, flake8)

The scaffold deliberately ships with almost nothing — PyYAML and numpy, because
the given code uses them. **No library is prescribed anywhere in this project.**
Which HTTP client, which HTML parser, which PDF library, which embeddings
provider: those are the engineering judgements the teams are here to make. §2
covers how to add what you settle on and keep everyone in sync.

### Check it worked

```bash
uv run python scripts/progress.py     # 0/54 — this is the assignment
uv run engine --help                  # the CLI wiring is already in place
```

### Restore gitignored data

Some files are too large for Git (scraped PDFs, raw API dumps, scraper specs).
They are stored on Google Drive:

> **[📁 Cortex — Gitignored Data (Google Drive)](https://drive.google.com/drive/folders/1FhWXKBVmA1X_y4S0mvD5qgIQgtiZ7xVA)**

Download the folders and place them at these paths:

| Drive Folder             | Restore To (relative to repo root)          |
|--------------------------|---------------------------------------------|
| `01_scraped_documents/*` | `engine/corpus/cuet/_files/`                |
| `02_api_metadata/*`      | `engine/corpus/cuet/_meta/`                 |
| `03_scraper_specs/*`     | the repo root                               |

The specs are worth restoring rather than skipping if you are working on the
CUET scraper: its code cites them 123 times, and each citation is where the
reasoning behind a measured constant lives.

The Drive folder contains a `README.md` with full details on what each file is,
the naming conventions, and important notes for the embedding team.

### Rebuild the CUET corpus files

`engine/corpus/cuet/documents.jsonl`, `pages.jsonl` and `manifest.json` are
generated, not committed — they are rebuilt from the per-portion shards in
`_shards/`, which are. After a pull:

```bash
cd engine
uv run python -m engine.crawler.cuet --stage merge
```

No network, about a second. They are generated because four people each rewrite
them in full, and a committed file that four people rewrite conflicts on every
pull request. See
[the scraper README](engine/src/engine/crawler/cuet/README.md).

---

## 2. Working with uv

### Running things

`uv run` executes a command inside the project venv. **Never activate the venv
by hand and never call `pip`** — that installs into your environment without
recording it, so it works for you and breaks for everyone else.

```bash
uv run engine crawl --config configs/crawl.acme.yaml
uv run python scripts/progress.py
uv run python -c "import numpy; print(numpy.__version__)"
uv run black src scripts        # format
uv run flake8 src scripts       # lint
```

### Adding a package

**The scaffold ships with almost nothing** — PyYAML and numpy, because the
given code uses them. Every other library is your choice. Decide what you need,
then add it:

```bash
uv add <package>                # adds to pyproject.toml, resolves, updates uv.lock, installs
uv add <package> <package>      # several at once
uv add --optional dev <package> # into the `dev` extra rather than core dependencies
uv remove <package>             # and back out again
```

`uv add` does four things in one step: edits `pyproject.toml`, re-resolves the
whole dependency graph, writes `uv.lock`, and installs into `.venv/`. You do not
run anything else afterwards.

### Keeping the team in sync

This is the part that goes wrong, and the rule is short:

> **`uv add` changes two files — `pyproject.toml` and `uv.lock`. Commit both, together.**

```bash
uv add <package>
git add pyproject.toml uv.lock
git commit -m "Add <package> for <the reason>"
```

Your teammates then get it with one command:

```bash
git pull
uv sync            # makes your venv match the lock exactly
```

`uv sync` both installs what is missing **and removes what is no longer in the
lock**, so everyone converges on the same environment rather than accumulating
private extras.

Two failure modes worth recognising:

| Symptom | Cause | Fix |
|---|---|---|
| Teammate gets `ModuleNotFoundError` for a package that works for you | you committed `pyproject.toml` but not `uv.lock` — or they have not run `uv sync` | commit both files; they run `uv sync` |
| It works for you, fails on a clean clone | you `pip install`ed something instead of `uv add` | `uv add` it properly |

**Merge conflicts in `uv.lock`**: never resolve them by hand — it is a generated
file and hand-merging produces a lock that resolves to nothing coherent. Take
either side, then regenerate:

```bash
git checkout --theirs uv.lock     # or --ours; it does not matter which
uv lock                           # regenerate from the merged pyproject.toml
git add uv.lock
```

If `pyproject.toml` itself conflicts, resolve that normally first — it is
hand-written and the conflict is real — then run `uv lock`.

### Optional extras

Extras group packages that only some people need, so a fresh clone stays small.
The scaffold defines one (`dev`); add your own if a dependency is heavy or only
relevant to one team:

```bash
uv add --optional pdf <package>      # creates a `pdf` extra
uv sync --extra dev --extra pdf      # install it
uv sync --all-extras                 # everything
```

Worth doing for anything large — a 2 GB machine-learning dependency that only
one person needs should not be in everyone's install.

### Pinning versions

Two layers doing two different jobs:

| File | Holds | Purpose |
|---|---|---|
| `pyproject.toml` | ranges — `<package>>=2.1` | what the project is *compatible with* |
| `uv.lock` | exact versions — `<package>==2.1.4` | what everyone *actually installs* |

`uv.lock` is committed on purpose. It is why your machine, a teammate's machine
and a fresh clone all resolve to identical versions.

```bash
uv add "<package>"                  # default: >=current, allow anything newer
uv add "<package>>=2.1,<3"          # allow patches, block breaking changes
uv add "<package>==2.1.4"           # hard pin: exactly this version
```

Prefer a range in `pyproject.toml` and let `uv.lock` do the pinning. Reach for a
hard `==` only when a specific version is genuinely required — and leave a
comment saying why, or the next person will "helpfully" bump it.

### Updating

```bash
uv lock --upgrade-package <package>    # bump ONE package, leave the rest alone
uv lock --upgrade                      # bump everything — deliberately, not casually
uv sync                                # apply the lock to your venv
```

Commit the new `uv.lock` and tell the team, because everyone will need
`uv sync` after they pull it.

### Reproducible installs

```bash
uv sync --frozen --extra dev    # install exactly the lock; fail if it is stale
```

`--frozen` refuses to silently re-resolve. Use it on a shared machine or in CI so
"works on my machine" becomes an explicit failure instead of a mystery.

### Inspecting

```bash
uv tree --depth 1     # direct dependencies, and which extra each belongs to
uv tree               # the full graph, when something pulls in a surprise
uv pip list           # what is actually installed right now
```

### Python version

`.python-version` pins **3.12** and `pyproject.toml` enforces
`requires-python = ">=3.12,<3.13"`. uv downloads and manages that interpreter
itself — you do not need a system Python, pyenv or conda.

```bash
uv python list
uv python install 3.12
```

---

## 3. Repository structure

```
Cortex/
└── engine/                   everything lives here
    ├── pyproject.toml        dependencies, extras, tool config
    ├── uv.lock               exact pinned versions — COMMITTED, never hand-edited
    ├── .python-version       3.12
    ├── .env.example          API keys template — copy to .env (gitignored)
    ├── CODEOWNERS            which team reviews which directory
    │
    ├── configs/              one YAML per pipeline stage per site (COMMITTED)
    │   └── README.md         how the four config types fit together + worked example
    │
    ├── datasets/             Team C's golden Q&A sets (COMMITTED, reviewed in PRs)
    │   └── acme/             worked example + documents.sample.jsonl to author against
    │
    ├── fixtures/site/        a 5-page fake site + 2 real PDFs. Serve it locally to
    │                         develop against with no network and nobody's permission
    │
    ├── corpus/               CAPTURED SITES, committed. Not runtime output —
    │   └── cuet/             this is a finished capture other teams build on.
    │       ├── _shards/          one JSON per portion. The source of truth.
    │       ├── <section dirs>    the .html/.md/.json triple per document
    │       ├── documents.jsonl   GENERATED by `--stage merge`, gitignored
    │       ├── pages.jsonl       GENERATED — the `extract --run` interface
    │       └── _files/           PDFs, on Google Drive: too large for git
    │
    ├── data/                 ALL runtime artifacts — GITIGNORED, never committed
    │   ├── sites/<site>/<run>/
    │   │   ├── pages.jsonl       Team A's deliverable: what was captured, no text
    │   │   ├── documents.jsonl   Team B's extract output: CleanDocument rows
    │   │   ├── manifest.json     counts, errors, asset tallies
    │   │   ├── raw/              HTML exactly as fetched
    │   │   ├── docs/             PDFs and other linked files
    │   │   └── tables/           markdown copies (also inlined into the text)
    │   ├── index/<site>/<id>/    vectors + index_meta.json
    │   └── runs/<run_id>/        report.json + report.md
    │
    ├── scripts/
    │   ├── progress.py           how much of the scaffold is filled in
    │   └── browse_documents.py   Team C's dataset authoring tool
    │
    └── src/engine/
        ├── contracts/        GIVEN. Shared schemas — the only cross-team surface.
        │                     Frozen after day 3. Imports no team package.
        ├── crawler/          TEAM A. fetcher, frontier, discover, pipeline
        │   └── cuet/         CUET scraper (API-first). Split into four portions,
        │       └── builders/ one module per person. See its README.
        ├── knowledge/        TEAM B. extraction, parsers, pdf, documents, chunking,
        │                             embedding, store, indexer, retriever, rag
        ├── evaluation/       TEAM C. dataset, metrics/, runner, report
        └── cli/              GIVEN. argparse wrappers. Calls your code, no logic.
```

**The dependency arrow points one way.** Teams depend on `contracts/`, never on
each other. `crawler/` does not import `knowledge/`; `knowledge/` does not import
`evaluation/`. That is what lets three teams work at once without collisions.

---

## 4. The three teams

Each package has its own README with the build order, library guidance, the
traps, and a definition of done. **Read yours before writing anything.**

Who owns what, including the boundaries and the handoffs, is written up in
**[RESPONSIBILITIES.md](RESPONSIBILITIES.md)**. Read that first if you are
wondering whether something is your job.

| Team | Owns | Brief | Functions |
|---|---|---|---|
| **A — Crawler** | fetch a site, save the bytes | [crawler/README.md](engine/src/engine/crawler/README.md) | 16 |
| **B — Knowledge** | clean → chunk → embed → answer | [knowledge/README.md](engine/src/engine/knowledge/README.md) | 24 |
| **C — Evaluation** | golden dataset + scorecard | [evaluation/README.md](engine/src/engine/evaluation/README.md) | 14 |

Those counts are the stubs the scaffold defines. They will grow — the scaffold
fixes the interfaces, and the classes behind them are yours to write.

Config reference: [engine/configs/README.md](engine/configs/README.md).

### How they stay in sync

They integrate through **files with frozen schemas**, never by importing each
other's modules.

```
Team A ──▶ data/sites/<site>/<run>/  ──▶ Team B ──▶ a Retriever object ──▶ Team C
           pages.jsonl + raw bytes                  (a 3-line Protocol)
```

**Citations are the one requirement that spans all three.** Team A captures the
provenance, Team B carries it into the vector store and out into the answer,
Team C finds out whether it worked. Agree in week one what a citation has to
show a reader and work backwards from there — discovering it in week three
means a re-crawl.

Two things make the rest work:

1. **Nobody is ever blocked.** Team C builds against the `Retriever` protocol
   with a ten-line fake and a sample corpus that ships with the repo. Team B
   works from `fixtures/site/` without waiting for a real crawl.
2. **Every stub says what it must do.** Signature, behaviour, the decisions that
   matter, the traps, and which libraries to look at.

---

## 5. The one rule

**`engine/src/engine/contracts/` is frozen after day 3.**

`CrawledPage`, `CleanDocument`, `Chunk`, `Retriever`, `Answer`, `EvalCase` are
how the three teams integrate without reading each other's code. Changing a
field after the freeze costs everyone a re-run.

Get all three teams in a room on day 2, agree the schemas, then treat that
directory as requiring all-team sign-off. `CODEOWNERS` already enforces it.

---

## 6. Tracking progress

```bash
uv run python scripts/progress.py
```

```
  Team A  crawler — capture a site             ███████·················   5/16   31%
  Team B  knowledge — clean, embed, answer     ██······················   4/31   13%
  Team C  evaluation — dataset and scoring     ████████████············   7/14   50%

  TOTAL   functions implemented                ████····················  16/61   26%
```

The denominator grows as you add your own classes — the scaffold fixes the
interfaces, not the implementations.

`--detail` breaks it down file by file.

**It does not check that the code is correct.** Correctness is judged by
running the pipeline and reading the output, which is what the
definition-of-done checklist in each team's README is for.

---

## 7. Commands

Each becomes usable as the team that owns it finishes their part.

| Command | Does | Team |
|---|---|---|
| `engine crawl --config configs/crawl.<site>.yaml` | Capture a site → `pages.jsonl` + bytes | A |
| `engine extract --run data/sites/<site>/<run>` | Bytes → `documents.jsonl` | B |
| `engine index --documents <path> --site <site>` | Chunk, embed, store | B |
| `engine ask "<question>" --index <dir>` | Answer with citations | B |
| `engine eval --dataset <path> --index <dir>` | Scorecard | C |

The whole chain against the bundled fixture site, which needs no network:

```bash
cd engine
python3 -m http.server 8765 --directory fixtures/site &

uv run engine crawl   --config configs/crawl.acme.yaml
uv run engine extract --run data/sites/acme/<run> --min-text-chars 50
uv run engine index   --documents data/sites/acme/<run>/documents.jsonl --site acme
uv run engine ask     "how long does a refund take" --index data/index/acme/<id>
```

See [engine/configs/README.md](engine/configs/README.md) for the annotated
version with every knob explained.

---

## 8. Providers and keys

```bash
cd engine && cp .env.example .env      # then fill in
```

The project fixes two things and leaves the rest open:

- **Embeddings come from a hosted API.** Nothing runs a model locally — the
  machines are 8 GB with no GPU. Which provider and which model are open.
- **Qdrant Cloud is the vector store target.** How you get there, and whether
  you build something simpler to develop against first, is open.

`.env.example` lists the variables those imply. Add your own as you choose
providers. `configs/` is committed; `.env` is not — **keys never go in a config
file.**

`engine ask` defaults to the `extractive` provider, which needs no key and just
returns the best matching passage. That is enough to confirm retrieval works
before spending anything on generation.

`configs/` is committed; `.env` is not. **Keys never go in a config file.**

---

## 9. Suggested 15 days

| Days | Team A | Team B | Team C |
|---|---|---|---|
| 1–3 | agree contracts; `fetcher`, `frontier` | agree contracts; `extraction`, `pdf` | agree contracts; metrics; **map the two sites with A and B** |
| 4–8 | `discover`, `pipeline`; first real site | `parsers`, `documents`, `chunking` | `dataset`, `runner`; ~60 cases; **review A and B's output** |
| 9–12 | 2–4 sites captured and tuned | `embedding`, `store`, `indexer`, `retriever`, `rag`; Qdrant Cloud | run eval against the real index; **feed failures back** |
| 13–15 | freeze, handover notes | demo path end to end | final scorecard, written verdict |

Two sequencing notes that matter more than they look:

- **Team C does not wait for a pipeline.** For the first two weeks they work
  alongside Teams A and B — reading captures and extracted text as *content*,
  which is how the missing section or the mangled table gets found while it is
  still a config change rather than a re-crawl. Their first real evaluation
  runs on day 8, not day 14: a scorecard at the end is a post-mortem.
- **Team B gets `extract` working before anything else.** It unblocks their own
  iteration loop and gives Team A a way to check their captures.

---

## 10. Roadmap

| | Status |
|---|---|
| Engine: crawl → extract → index → ask → eval | **In progress** — the 15-day build |
| Qdrant Cloud as the vector store | Designed in; Team B implements |
| `engine serve` — a minimal HTTP API + single-page UI | Planned, deferred until the engine works |
| Django + Next.js frontend (auth, billing, multi-user) | Deferred. A SaaS boilerplate exists and can be brought in later; the `Answer` contract is already the API shape it would consume |

The UI is deliberately last. Wiring an interface onto a pipeline that does not
exist yet means building against imagined behaviour, and the first thing that
changes when the crawler hits a real site is the shape of the data.

---

## 11. Crawling responsibly

`obey_robots: true` and `delay_seconds >= 1.0` on every site you do not own. An
impolite crawler gets the whole team's IP blocked on the first serious run, and
that is not recoverable inside fifteen days.

## License

See [LICENSE](LICENSE).
