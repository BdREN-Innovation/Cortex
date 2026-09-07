"""Ties fetch -> extract -> normalise together and writes the team-1 artifacts."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from engine.contracts.documents import (
    CleanDocument,
    CrawlManifest,
    content_hash,
    make_doc_id,
)
from engine.contracts.jsonio import write_json, write_jsonl
from engine.crawler.extract import extract
from engine.crawler.fetcher import Fetcher, FetchPolicy
from engine.crawler.frontier import Frontier, ScopeRules, canonicalize

log = logging.getLogger(__name__)


@dataclass
class CrawlConfig:
    site: str
    seeds: list[str]
    allowed_domains: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    max_depth: int = 3
    max_pages: int = 200
    min_text_chars: int = 200
    save_raw_html: bool = True
    fetch: FetchPolicy = field(default_factory=FetchPolicy)

    @classmethod
    def from_dict(cls, payload: dict) -> "CrawlConfig":
        fetch = FetchPolicy(**payload.get("fetch", {}))
        known = {f for f in cls.__dataclass_fields__ if f != "fetch"}
        return cls(fetch=fetch, **{k: v for k, v in payload.items() if k in known})


def _default_domains(seeds: list[str]) -> list[str]:
    return sorted({urlparse(seed).netloc.lower().split(":")[0] for seed in seeds})


def crawl(config: CrawlConfig, out_root: str | Path = "data", run_id: str | None = None) -> Path:
    """Crawl a site and write documents.jsonl + manifest.json. Returns the run directory."""

    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started_at = datetime.now(timezone.utc)

    out_root = Path(out_root)
    doc_dir = out_root / "documents" / config.site / run_id
    raw_dir = out_root / "raw" / config.site / run_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    if config.save_raw_html:
        raw_dir.mkdir(parents=True, exist_ok=True)

    rules = ScopeRules(
        allowed_domains=config.allowed_domains or _default_domains(config.seeds),
        include_patterns=config.include_patterns,
        exclude_patterns=config.exclude_patterns,
        max_depth=config.max_depth,
    )
    frontier = Frontier(config.seeds, rules)
    fetcher = Fetcher(config.fetch)

    documents: list[CleanDocument] = []
    seen_hashes: set[str] = set()
    errors: list[dict] = []
    fetched = skipped = 0

    while frontier and fetched < config.max_pages:
        url, depth = frontier.pop()
        try:
            page = fetcher.fetch(url)
        except Exception as exc:  # noqa: BLE001 - one bad page must not kill the run
            errors.append({"url": url, "error": str(exc)})
            log.warning("giving up on %s: %s", url, exc)
            continue

        if page is None:
            skipped += 1
            continue

        fetched += 1
        if page.status >= 400:
            errors.append({"url": url, "error": f"HTTP {page.status}"})
            continue

        found = extract(page.html, page.url)
        frontier.add_links(page.url, found.links, depth + 1)

        if len(found.text) < config.min_text_chars:
            log.debug("thin page skipped (%s chars): %s", len(found.text), url)
            skipped += 1
            continue

        digest = content_hash(found.text)
        if digest in seen_hashes:
            log.debug("duplicate content skipped: %s", url)
            skipped += 1
            continue
        seen_hashes.add(digest)

        canonical = canonicalize(found.canonical_url or page.url)
        doc_id = make_doc_id(canonical)

        html_path = ""
        if config.save_raw_html:
            target = raw_dir / f"{doc_id}.html"
            target.write_text(page.html, encoding="utf-8")
            html_path = str(target)

        documents.append(
            CleanDocument(
                doc_id=doc_id,
                source_url=page.url,
                canonical_url=canonical,
                title=found.title or canonical,
                text=found.text,
                content_hash=digest,
                fetched_at=page.fetched_at.isoformat(),
                section_path=found.section_path,
                html_path=html_path,
                lang=found.lang,
                meta=found.meta,
            )
        )
        log.info("[%s/%s] %s", len(documents), config.max_pages, canonical)

    written = write_jsonl(doc_dir / "documents.jsonl", documents)

    manifest = CrawlManifest(
        run_id=run_id,
        site=config.site,
        seeds=config.seeds,
        started_at=started_at.isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
        pages_fetched=fetched,
        pages_written=written,
        pages_skipped=skipped,
        errors=errors,
        config={
            "max_depth": config.max_depth,
            "max_pages": config.max_pages,
            "min_text_chars": config.min_text_chars,
            "allowed_domains": rules.allowed_domains,
            "delay_seconds": config.fetch.delay_seconds,
            "obey_robots": config.fetch.obey_robots,
        },
    )
    write_json(doc_dir / "manifest.json", manifest)

    log.info("crawl done: %s documents -> %s", written, doc_dir)
    return doc_dir
