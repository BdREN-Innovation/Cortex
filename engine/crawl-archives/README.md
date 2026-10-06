# `crawl-archives/` — every website's data, one zip each

Everything too heavy to commit as loose files is committed here instead, as one
zip per website. The zips are stored with **Git LFS**: git holds a small pointer
per zip and GitHub's LFS storage holds the bytes, which is what lets a 565 MB
zip past GitHub's 100 MB limit on a single file.

| Zip | Unzip into | What is inside |
|---|---|---|
| `cuet.zip` | `engine/corpus/` | `cuet/_files/`: the 1,106 downloaded PDFs and Word files listed in `_files/index.json`. `cuet/_meta/api_dump.json`: every API response verbatim. `cuet/_meta/chunk_cache/`: 47 JavaScript bundles saved from the site. The rest of the CUET corpus is committed unzipped in `engine/corpus/cuet/` |
| `bdren.zip` | `engine/data/sites/` | Crawl runs `bdren-20260911T042956Z`, `bdren-20260913T073128Z` |
| `bubt.zip` | `engine/data/sites/` | Crawl runs `bubt-20260908T220949Z`, `bubt-20260913T073849Z` |
| `daffodil.zip` | `engine/data/sites/` | Crawl run `daffodil-20260913T071704Z` |
| `green.zip` | `engine/data/sites/` | Crawl runs `green-20260908T220124Z`, `green-20260913T074606Z` |
| `startech.zip` | `engine/data/sites/` | Crawl run `startech-20260913T070817Z` |
| `thedailystar.zip` | `engine/data/sites/` | Crawl run `thedailystar-20260913T062819Z` |
| `uiu.zip` | `engine/data/sites/` | Crawl run `uiu-20260913T075008Z` |

Where they came from, and how each was checked:

- The seven crawl zips were built from commit `1fa4f21`, the last commit that
  held the runs unzipped, and compared file-for-file against it.
- `cuet.zip` holds exactly the files `_files/index.json` records as downloaded,
  each checked against the size recorded there. It leaves out `index.json` and
  `_files/README.md` on purpose: those are committed, and unzipping must never
  overwrite them with an older copy.

## Using them

Install Git LFS once per machine, then fetch the zips. Without LFS, every
`.zip` here is a tiny text pointer that will not open.

```powershell
git lfs install
git lfs pull
Expand-Archive engine/crawl-archives/cuet.zip -DestinationPath engine/corpus
Expand-Archive engine/crawl-archives/bubt.zip -DestinationPath engine/data/sites
```

`engine/data/` and CUET's `_files/` are gitignored, so unzipped files never end
up in a commit.

## Adding data

A zip is always rebuilt whole. Unzip the current one first, so nothing already
in it is lost, then zip the site folder again with Windows' own `tar`, in
PowerShell from the repository root:

```powershell
# After a new crawl of a site
tar -a -c -f engine/crawl-archives/bubt.zip -C engine/data/sites bubt

# After new CUET downloads. index.json and README.md stay out: they are committed.
tar -a -c -f engine/crawl-archives/cuet.zip -C engine/corpus --exclude cuet/_files/index.json --exclude cuet/_files/README.md cuet/_files cuet/_meta/api_dump.json cuet/_meta/chunk_cache
```

Then commit the zip, and add the new run to the table above and to Section 7 of
`DATA_GUIDE.md`.

## Rules

- **Rebuild a zip from a complete folder.** Zipping a site folder that is
  missing an old run removes that run from the zip.
- **Unzip into the folder in the table, and never mix runs.** Every
  `content_path` in a run is relative to that run's folder, so files from two
  runs mixed together point at each other's missing files, and nothing warns
  you.
- **Every rebuild stores a full new copy.** LFS keeps old versions, so
  rebuilding `bdren.zip` adds another 565 MB to the organisation's LFS storage.
  Rebuild when there is new data, not on every commit.
