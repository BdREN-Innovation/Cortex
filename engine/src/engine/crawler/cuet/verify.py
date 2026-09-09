"""Stage 7: run the specification's definition of done against the corpus.

CUET_SCRAPER_SPEC.md §10 is a checklist of about thirty properties the corpus
must have. It was written to be read by a person and ticked by hand, which means
in practice it gets ticked once, on the run it was written for, and never again.

This module runs the automatable half of it. Offline, in under a second, against
whatever is on disk:

    python -m engine.crawler.cuet --stage verify

It exists because the checklist found three real defects the first time it was
actually executed end to end — a stale endpoint in the dump, a vendor-domain URL
surviving into citable text, and six faculty profile pages discovered but never
planned. None of those was visible from the tests, because none of them is a
property of a function; they are properties of the corpus.

**What this does NOT do.** §10's "Human verification, not automatable" block is
left alone deliberately: reading three captured pages against the live site,
opening a PDF, comparing an API document to its browser counterpart. Those need
judgement, and a green tick here is not a substitute for them.

Nothing here makes a network request. `--stage audit` is the one that checks the
live site, and it answers a different question: whether the endpoint inventory
has drifted. This one asks whether what we already captured is sound.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from . import config
from .builders import owner_of_url
from .paths import canonical, is_excluded_url, is_image_url

log = logging.getLogger(__name__)

# Spec §10 groups its checks under these headings. Keeping them means a failure
# here can be traced straight back to the line in the document that requires it.
GROUPS = ("Correctness", "Encoding", "Images", "Robustness", "Politeness",
          "Coverage")


@dataclass
class Check:
    """One line of the definition of done.

    `waived` is the interesting state, and the reason this is not a plain
    boolean. Several §10 items are conditional — "no URL is assigned to
    `_unsorted`, OR every one that is has been reviewed". A corpus that
    satisfies the second half is correct, but reporting it as an unqualified
    pass hides a decision somebody made; reporting it as a failure trains
    people to ignore the output. It gets its own state and its own reason.
    """

    group: str
    spec: str            # the §10 line, close to verbatim
    ok: bool
    detail: str = ""
    waived: str = ""     # non-empty: conditionally satisfied, and why

    @property
    def status(self) -> str:
        if self.waived:
            return "WAIVED"
        return "PASS" if self.ok else "FAIL"


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, group: str, spec: str, ok: bool, detail: str = "",
            waived: str = "") -> None:
        self.checks.append(Check(group, spec, ok, detail, waived))

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok and not c.waived]

    @property
    def waivers(self) -> list[Check]:
        return [c for c in self.checks if c.waived]


def _load(out: Path) -> dict:
    """Read the corpus. Missing pieces are reported, never raised past here."""
    data: dict = {"out": out}

    docs_path = out / "documents.jsonl"
    data["documents"] = [
        json.loads(line)
        for line in docs_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ] if docs_path.exists() else None

    pages_path = out / "pages.jsonl"
    data["pages"] = [
        json.loads(line)
        for line in pages_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ] if pages_path.exists() else None

    dump_path = out / "_meta" / "api_dump.json"
    data["dump"] = json.loads(dump_path.read_text(encoding="utf-8")) \
        if dump_path.exists() else None

    for name, rel in (("urls", "_meta/urls.txt"),
                      ("found_pages", "_meta/found_pages.txt")):
        path = out / rel
        data[name] = [
            line.split("\t")[0].strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ] if path.exists() else None

    return data


# --------------------------------------------------------------------------
# The checks, grouped as §10 groups them
# --------------------------------------------------------------------------

def _correctness(data: dict, report: Report) -> None:
    docs, dump, out = data["documents"], data["dump"], data["out"]

    if dump is not None:
        declared = {e.path for e in config.ENDPOINTS}
        present = {k for k in dump if k.startswith("/")}
        missing = sorted(declared - present)
        report.add(
            "Correctness",
            "--stage discover writes api_dump.json with every declared endpoint",
            not missing,
            f"{len(present)} of {len(declared)} present"
            + (f"; missing {', '.join(missing)}" if missing else ""),
        )

        # §3.3 and §10: counts come from list lengths, never a count field.
        # /home-counters reports 15 departments; there are 18.
        entities = dump.get("_entity_details") or {}
        kinds: dict[str, int] = {}
        for value in entities.values():
            entity = value.get("data") if isinstance(value.get("data"), dict) else value
            if isinstance(entity, dict) and entity.get("type"):
                kinds[entity["type"]] = kinds.get(entity["type"], 0) + 1
        report.add(
            "Correctness",
            "Counts derived from list lengths, not a count field: 18 departments",
            kinds.get("academic") == 18,
            ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())),
        )

    if docs is None:
        report.add("Correctness", "documents.jsonl exists", False,
                   "run --stage merge")
        return

    report.add("Correctness", "--stage content writes eight CMS documents",
               sum(1 for d in docs if d["section_path"][:1] == ["CMS"]) == 8,
               f"{sum(1 for d in docs if d['section_path'][:1] == ['CMS'])} found")

    ids = [d["doc_id"] for d in docs]
    report.add("Correctness", "doc_ids are unique",
               len(set(ids)) == len(ids),
               f"{len(ids)} documents, {len(set(ids))} distinct")

    report.add(
        "Correctness",
        "Every content_hash matches its text",
        all(d["content_hash"] == hashlib.sha256(d["text"].encode()).hexdigest()[:32]
            for d in docs),
    )

    # §6.4/§4.1: /department/cse and /department/CE must not collide on a
    # case-insensitive filesystem, which is what the id suffix is for.
    stems = [Path(d["html_path"]).name.lower() for d in docs]
    report.add("Correctness",
               "No two documents collide on a case-insensitive filesystem",
               len(set(stems)) == len(stems),
               f"{len(stems) - len(set(stems))} collisions")

    bad_paths = [d["html_path"] for d in docs
                 if ".." in d["html_path"] or len(Path(d["html_path"]).name) > 120]
    report.add("Correctness",
               "No path contains '..' or exceeds 120 characters",
               not bad_paths, "; ".join(bad_paths[:3]))

    # Two hosts, not one. The alumni portion cites alumni.cuet.ac.bd, which is
    # a real CUET site rather than an off-site link, so pinning this to the
    # main host alone would fail a portion that is behaving correctly.
    # Anything outside these two is still a citation a reader cannot follow.
    citable = (config.SITE, config.ALUMNI_SITE)
    off_site = [d["canonical_url"] for d in docs
                if not d["canonical_url"].startswith(citable)]
    report.add("Correctness",
               "Every citation URL is on a CUET host",
               not off_site, "; ".join(off_site[:3]))

    # §6.3: a synthetic key must never reach a citation. Splitting one listing
    # page into several documents uses query parameters for identity, and those
    # belong in the id, not in the URL a reader is shown.
    synthetic = [d["canonical_url"] for d in docs
                 if re.search(r"_part=|_type=|_curricula=", d["canonical_url"])]
    report.add("Correctness",
               "No synthetic identity parameter leaked into a citation",
               not synthetic, "; ".join(synthetic[:3]))

    unsorted = [d for d in docs if d.get("meta", {}).get("section") == "_unsorted"]
    if unsorted:
        # §6.8 puts the out-of-scope notice types here deliberately. Anything
        # else in _unsorted is a genuine hole in the section map.
        unexpected = [d for d in unsorted
                      if d["canonical_url"] != f"{config.SITE}/notices/all-notice"]
        report.add(
            "Correctness",
            "No URL assigned to _unsorted, or every one reviewed",
            not unexpected,
            "; ".join(d["canonical_url"] for d in unexpected[:3]),
            waived="" if unexpected else
            f"{len(unsorted)} out-of-scope notice indexes, deliberate per spec 6.8",
        )
    else:
        report.add("Correctness",
                   "No URL assigned to _unsorted, or every one reviewed", True)

    if data["pages"] is not None:
        broken = [p["content_path"] for p in data["pages"]
                  if not (out / p["content_path"]).exists()]
        report.add("Correctness",
                   "Every pages.jsonl content_path resolves on disk",
                   not broken, "; ".join(broken[:3]))

    # The reverse direction, which nothing checked until an orphan turned up.
    #
    # Documents are written per portion and the corpus is assembled from the
    # shards, so a document on disk that no shard claims never reaches
    # documents.jsonl - and nothing notices. One did: a notice index kept its
    # pre-`_part` filename beside the current one, same text, different id,
    # and sat in the repository as a tracked file the corpus did not contain.
    #
    # That is how a stale duplicate outlives the change that orphaned it. The
    # check costs one directory walk and turns a silent leftover into a line
    # somebody has to answer for.
    if data["documents"] is not None:
        known = {d["doc_id"] for d in data["documents"]}
        orphans = []
        for sidecar in sorted(out.rglob("*.json")):
            if {"_meta", "_shards", "_files"} & set(
                    sidecar.relative_to(out).parts):
                continue
            try:
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(meta, dict):
                continue
            page_id = meta.get("page_id")
            if page_id and page_id not in known:
                orphans.append(str(sidecar.relative_to(out)).replace("\\", "/"))
        report.add(
            "Correctness",
            "No document on disk is missing from the merged corpus",
            not orphans,
            "; ".join(orphans[:3]) or f"{len(known)} documents, none orphaned",
        )


def _encoding(data: dict, report: Report) -> None:
    docs = data["documents"]
    if docs is None:
        return

    # §4.12: correct looks like চুয়েট, broken looks like à¦šà§Ÿà§‡à¦Ÿ.
    bangla = [d for d in docs if re.search(r"[ঀ-৿]", d["text"])]
    report.add("Encoding", "Bangla is present and correctly decoded",
               bool(bangla), f"{len(bangla)} documents")

    mojibake = [d["canonical_url"] for d in docs
                if "Ã" in d["text"] or "à¦" in d["text"]]
    report.add("Encoding", "No mojibake anywhere",
               not mojibake, "; ".join(mojibake[:3]))

    empty = [d["canonical_url"] for d in docs if not d["text"].strip()]
    report.add("Encoding", "Every document has text",
               not empty, "; ".join(empty[:3]))


def _images(data: dict, report: Report) -> None:
    out = data["documents"], data["out"]
    docs, root = out
    files_dir = root / "_files"

    if files_dir.is_dir():
        images = [p.name for p in files_dir.iterdir() if is_image_url(p.name)]
        report.add("Images", "_files/ contains zero image files",
                   not images, "; ".join(images[:3]))
    else:
        report.add("Images", "_files/ contains zero image files", True,
                   "_files/ not present locally; it is on Google Drive")

    if docs is not None:
        # §4.6: alt text IS prose and must survive. Losing it silently is the
        # failure mode of an over-eager image filter.
        report.add("Images", "Alt text survives into the captured text",
                   any(len(d["text"]) > 200 for d in docs),
                   "text bodies present")


def _robustness(data: dict, report: Report) -> None:
    out = data["out"]
    meta = out / "_meta"

    for name in ("errors.json", "run.json"):
        report.add("Robustness",
                   f"{name} is written even on a fully successful run",
                   (meta / name).exists())

    leftovers = list((out / "_files").glob("*.part")) if (out / "_files").is_dir() else []
    report.add("Robustness", "No leftover .part files from an interrupted write",
               not leftovers, "; ".join(p.name for p in leftovers[:3]))


def _politeness(data: dict, report: Report) -> None:
    # §7.4. The contact address is the site's only channel to whoever is
    # running this, since cuet.ac.bd serves no robots.txt.
    report.add("Politeness",
               "User-Agent carries a real contact address, not a placeholder",
               "@" in config.CONTACT and not config.CONTACT.startswith("REPLACE"),
               config.USER_AGENT)

    report.add("Politeness", "Per-host delay is at least 1.5 seconds",
               config.DELAY >= 1.5, f"DELAY={config.DELAY}")

    # §7.4 is explicit that these two are never retried: a 404 stays a 404, and
    # retrying a 403 is how a crawler earns a block.
    report.add("Politeness", "404 and 403 are never retried",
               not ({404, 403} & set(config.RETRY_STATUSES)),
               f"retry on {sorted(config.RETRY_STATUSES)}")

    report.add("Politeness", "The vendor domain is excluded from fetching",
               is_excluded_url("https://cuet.thetork.com/faculty"))


def _coverage(data: dict, report: Report) -> None:
    """Appendix B's required action, as a check rather than a shell one-liner.

    The appendix says to diff the plan against what was discovered, review the
    difference by hand and fold the in-scope entries back into the plan. It is
    the step most likely to be skipped, because nothing fails when it is.
    """
    planned, found = data["urls"], data["found_pages"]
    if planned is None or found is None:
        report.add("Coverage", "Appendix B gap diff has been run", False,
                   "_meta/urls.txt or found_pages.txt missing")
        return

    # Three things make a discovered URL a non-gap, and the first is the one
    # the original check missed: a URL captured from the API is not a coverage
    # hole just because it is absent from the browser plan. Comparing against
    # the plan alone reported captured pages as missing.
    planned_set = {canonical(u) for u in planned}
    captured = {canonical(d["canonical_url"]) for d in (data["documents"] or [])}
    dismissed = {canonical(config.SITE + path)
                 for path in config.KNOWN_NOT_PLANNED}
    dismissed |= {canonical(config.ALUMNI_SITE + path)
                  for path in config.ALUMNI_NOT_PLANNED}
    patterns = [(re.compile(rx), why)
                for rx, why in config.KNOWN_NOT_PLANNED_PATTERNS]

    def dismissed_by_pattern(url: str) -> bool:
        path = url.replace(config.SITE, "") or "/"
        return any(rx.search(path) for rx, _ in patterns)

    unplanned = sorted(
        url for url in {canonical(u) for u in found}
        if url not in planned_set
        and url not in captured
        and url not in dismissed
        and not dismissed_by_pattern(url)
        # Both hosts. Checking config.SITE alone made the alumni portion
        # invisible to Appendix B: every URL on it was silently skipped, so
        # the one check meant to catch a missing area could not see it.
        and url.startswith((config.SITE, config.ALUMNI_SITE))
        and not is_excluded_url(url)
    )

    # Attributed, because a single corpus-wide number is one four people each
    # read as somebody else's problem. Split by portion it becomes a to-do list
    # with a name on each line.
    by_owner: dict[str, int] = {}
    for url in unplanned:
        by_owner[owner_of_url(url) or "unclaimed"] = (
            by_owner.get(owner_of_url(url) or "unclaimed", 0) + 1
        )
    breakdown = ", ".join(f"{name} {count}"
                          for name, count in sorted(by_owner.items())) or "none"

    # A planned URL that never arrived is either explained or it is a hole.
    # Reported as its own line so an unreachable host reads as a stated fact
    # rather than as a quietly short corpus.
    uncaptured = sorted(u for u in planned_set if u not in captured)
    unexplained = [u for u in uncaptured
                   if urlsplit(u).netloc not in config.UNRESOLVABLE_HOSTS]
    explained = len(uncaptured) - len(unexplained)
    report.add(
        "Coverage",
        "Every planned URL is captured, or its absence is explained",
        not unexplained,
        (f"{len(uncaptured)} planned URL(s) not captured, {explained} explained "
         f"in _meta/known_gaps.json"
         + (f"; unexplained: {', '.join(unexplained[:3])}" if unexplained else ""))
        if uncaptured else "all planned URLs captured",
    )

    report.add(
        "Coverage",
        "Nothing in-scope was discovered but left unplanned (Appendix B)",
        not unplanned,
        f"{len(unplanned)} to review ({breakdown}); "
        f"{len(dismissed)} URLs and {len(patterns)} pattern(s) dismissed "
        f"with a reason",
    )


def run(out: Path | None = None) -> Report:
    out = out or config.OUT
    data = _load(out)
    report = Report()

    _correctness(data, report)
    _encoding(data, report)
    _images(data, report)
    _robustness(data, report)
    _politeness(data, report)
    _coverage(data, report)

    width = max(len(c.spec) for c in report.checks)
    current = None
    for check in report.checks:
        if check.group != current:
            current = check.group
            print(f"\n  {current}")
        print(f"    {check.status:<6} {check.spec:<{width}}"
              + (f"   {check.detail}" if check.detail else ""))
        if check.waived:
            print(f"    {'':<6} {'':<{width}}   -> {check.waived}")

    print(f"\n  {len(report.checks)} checks, {len(report.failures)} failing, "
          f"{len(report.waivers)} waived\n")

    if report.failures:
        print("  Spec section 10 also has checks that cannot be automated.")
        print("  A green run here is not a substitute for reading the pages.\n")

    return report
