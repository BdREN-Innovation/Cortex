"""Capture a site: fetch pages and linked files, save the bytes, record what was found.

This stage deliberately produces no extracted text. It writes pages.jsonl —
one CrawledPage per URL — beside the bytes those records point at.

Raw HTML is preserved exactly as fetched. A normalized representation is used
only for page-change detection so volatile HTML such as scripts, comments,
nonces, and formatting differences do not create unnecessary change events.

Turning captured bytes into documents is engine extract, which Team B owns.

TEAM A OWNS THIS FILE.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from bs4 import BeautifulSoup, Comment

from engine.contracts.documents import CrawlManifest, CrawledPage, make_doc_id
from engine.crawler.discover import discover
from engine.crawler.fetcher import FetchPolicy, Fetcher
from engine.crawler.frontier import Frontier, ScopeRules, canonicalize

log = logging.getLogger(__name__)


@dataclass
class AssetPolicy:
    """What to download besides HTML."""

    download_documents: bool = True
    max_documents: int = 25


@dataclass
class CrawlConfig:
    """Configuration for one site crawl."""

    site: str
    seeds: list[str]
    allowed_domains: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    max_depth: int = 3
    max_pages: int = 200
    fetch: FetchPolicy = field(default_factory=FetchPolicy)
    assets: AssetPolicy = field(default_factory=AssetPolicy)

    @classmethod
    def from_dict(cls, payload: dict) -> "CrawlConfig":
        """Build a CrawlConfig from parsed YAML."""

        fetch_data = payload.get("fetch") or {}
        asset_data = payload.get("assets") or {}

        fetch_fields = {
            "user_agent",
            "delay_seconds",
            "timeout_seconds",
            "max_retries",
            "max_bytes",
            "max_asset_bytes",
            "obey_robots",
            "concurrency",
        }

        asset_fields = {
            "download_documents",
            "max_documents",
        }

        fetch_config = {
            key: value
            for key, value in fetch_data.items()
            if key in fetch_fields
        }

        asset_config = {
            key: value
            for key, value in asset_data.items()
            if key in asset_fields
        }

        return cls(
            site=str(payload["site"]),
            seeds=list(payload.get("seeds", [])),
            allowed_domains=list(payload.get("allowed_domains", [])),
            include_patterns=list(payload.get("include_patterns", [])),
            exclude_patterns=list(payload.get("exclude_patterns", [])),
            max_depth=int(payload.get("max_depth", 3)),
            max_pages=int(payload.get("max_pages", 200)),
            fetch=FetchPolicy(**fetch_config),
            assets=AssetPolicy(**asset_config),
        )


def _utcnow() -> datetime:
    """Return the current UTC time."""

    return datetime.now(timezone.utc)


def _safe_filename(value: str, fallback: str = "asset") -> str:
    """Turn a URL/path-derived value into a safe filesystem filename."""

    value = value.strip()

    if not value:
        value = fallback

    value = value.replace("\\", "_").replace("/", "_")
    value = value.replace("..", "_")

    value = re.sub(
        r'[<>:"|?*\x00-\x1f]',
        "_",
        value,
    )

    stem = value.split(".")[0].upper()

    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }

    if stem in reserved:
        value = f"_{value}"

    value = value.strip(" .")

    if not value:
        value = fallback

    if len(value) > 180:
        value = value[:180]

    return value


def _write_jsonl(path: Path, records: list[dict]) -> None:
    """Write dictionaries as one JSON object per line."""

    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )


def _config_to_dict(config: CrawlConfig) -> dict:
    """Convert crawl configuration into a manifest-friendly dictionary."""

    return {
        "site": config.site,
        "seeds": config.seeds,
        "allowed_domains": config.allowed_domains,
        "include_patterns": config.include_patterns,
        "exclude_patterns": config.exclude_patterns,
        "max_depth": config.max_depth,
        "max_pages": config.max_pages,
        "fetch": {
            "user_agent": config.fetch.user_agent,
            "delay_seconds": config.fetch.delay_seconds,
            "timeout_seconds": config.fetch.timeout_seconds,
            "max_retries": config.fetch.max_retries,
            "max_bytes": config.fetch.max_bytes,
            "max_asset_bytes": config.fetch.max_asset_bytes,
            "obey_robots": config.fetch.obey_robots,
            "concurrency": config.fetch.concurrency,
        },
        "assets": {
            "download_documents": config.assets.download_documents,
            "max_documents": config.assets.max_documents,
        },
    }


def _make_run_id(site: str) -> str:
    """Create a sortable UTC run ID."""

    timestamp = _utcnow().strftime("%Y%m%dT%H%M%SZ")
    return f"{site}-{timestamp}"






def _document_subfolder(url: str) -> str:
    """Derive a section-name subfolder from a document URL's path."""

    path = urlsplit(url).path.strip("/")
    segments = path.split("/")

    if not segments or not segments[0]:
        return "misc"

    return _safe_filename(segments[0], fallback="misc")








def _document_filename(url: str, ordinal: int) -> str:
    """Create a safe filename for a downloaded document."""

    path = urlsplit(url).path
    name = Path(path).name

    if not name:
        name = f"document-{ordinal}.bin"

    name = _safe_filename(
        name,
        fallback=f"document-{ordinal}.bin",
    )

    return f"{ordinal:04d}-{name}"


def _sha256(value: str) -> str:
    """Return SHA-256 for a UTF-8 string."""

    return hashlib.sha256(
        value.encode(
            "utf-8",
            errors="replace",
        )
    ).hexdigest()


def _normalize_html_for_change_detection(html: str) -> str:
    """Create a stable representation of HTML for change detection.

    Raw HTML is never modified on disk.

    The normalized representation removes common volatile content that can
    change between requests even when the useful page itself has not changed.

    This is crawler-level change detection only. It is not semantic document
    extraction, which belongs to Team B.
    """

    try:
        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        # Scripts/styles commonly contain timestamps, analytics identifiers,
        # generated bundles, session information, and other volatile values.
        for tag in soup.find_all(
            [
                "script",
                "style",
                "noscript",
            ]
        ):
            tag.decompose()

        # HTML comments can contain build timestamps or server-side debug data.
        for comment in soup.find_all(
            string=lambda value: isinstance(
                value,
                Comment,
            )
        ):
            comment.extract()

        # Remove attributes that are commonly generated per request/session.
        volatile_attributes = {
            "nonce",
            "integrity",
            "crossorigin",
        }

        for tag in soup.find_all(True):
            for attribute in list(
                tag.attrs.keys()
            ):
                attribute_lower = (
                    attribute.lower()
                )

                if (
                    attribute_lower
                    in volatile_attributes
                ):
                    del tag.attrs[attribute]

                    continue

                # Framework-generated IDs frequently change without the
                # actual page content changing.
                if attribute_lower in {
                    "data-reactid",
                    "data-reactroot",
                }:
                    del tag.attrs[attribute]

        normalized = str(soup)

        # Whitespace differences caused by rendering/template formatting
        # should not count as content changes.
        normalized = re.sub(
            r">\s+<",
            "><",
            normalized,
        )

        normalized = re.sub(
            r"\s+",
            " ",
            normalized,
        )

        return normalized.strip()

    except Exception as exc:
        log.warning(
            "HTML normalization failed; "
            "using whitespace normalization only: %s",
            exc,
        )

        return re.sub(
            r"\s+",
            " ",
            html,
        ).strip()


def _raw_content_hash(html: str) -> str:
    """Hash the exact raw HTML."""

    return _sha256(html)


def _normalized_content_hash(html: str) -> str:
    """Hash normalized HTML for change detection."""

    normalized = (
        _normalize_html_for_change_detection(
            html
        )
    )

    return _sha256(normalized)


def _load_previous_page_hashes(
    out_root: str | Path,
    site: str,
    current_run_id: str,
) -> dict[str, str]:
    """Load normalized hashes from the latest useful previous crawl.

    If the previous run predates normalized hashing, its saved raw HTML is
    loaded and normalized on the fly. This lets existing crawl data become
    the baseline without requiring another full reset crawl.
    """

    site_dir = (
        Path(out_root)
        / "sites"
        / site
    )

    if not site_dir.exists():
        return {}

    try:
        previous_runs = sorted(
            (
                path
                for path in site_dir.iterdir()
                if path.is_dir()
                and path.name != current_run_id
            ),
            key=lambda path: path.name,
            reverse=True,
        )

    except OSError as exc:
        log.warning(
            "Could not inspect previous runs "
            "for site %s: %s",
            site,
            exc,
        )

        return {}

    for previous_run in previous_runs:
        pages_path = (
            previous_run
            / "pages.jsonl"
        )

        if not pages_path.exists():
            continue

        hashes: dict[str, str] = {}

        try:
            with pages_path.open(
                "r",
                encoding="utf-8",
            ) as handle:

                for line in handle:
                    line = line.strip()

                    if not line:
                        continue

                    try:
                        record = json.loads(
                            line
                        )

                    except json.JSONDecodeError:
                        continue

                    canonical_url = (
                        record.get(
                            "canonical_url"
                        )
                    )

                    if not canonical_url:
                        continue

                    try:
                        canonical_key = (
                            canonicalize(
                                str(
                                    canonical_url
                                )
                            )
                        )

                    except ValueError:
                        continue

                    meta = (
                        record.get("meta")
                        or {}
                    )

                    # Preferred path: previous run already has normalized
                    # change-detection hashes.
                    normalized_hash = (
                        meta.get(
                            "normalized_content_sha256"
                        )
                    )

                    if normalized_hash:
                        hashes[
                            canonical_key
                        ] = str(
                            normalized_hash
                        )

                        continue

                    # Compatibility path for our previous implementation:
                    # derive a normalized hash from saved raw HTML.
                    content_path = (
                        record.get(
                            "content_path"
                        )
                    )

                    if not content_path:
                        continue

                    raw_html_path = (
                        previous_run
                        / str(content_path)
                    )

                    if not raw_html_path.exists():
                        continue

                    try:
                        previous_html = (
                            raw_html_path.read_text(
                                encoding="utf-8",
                                errors="replace",
                            )
                        )

                    except OSError:
                        continue

                    hashes[
                        canonical_key
                    ] = (
                        _normalized_content_hash(
                            previous_html
                        )
                    )

        except OSError as exc:
            log.warning(
                "Could not read previous crawl %s: %s",
                pages_path,
                exc,
            )

            continue

        if hashes:
            log.info(
                "Loaded %d normalized page hashes "
                "from previous run %s",
                len(hashes),
                previous_run.name,
            )

            return hashes

    log.info(
        "No previous page hashes found "
        "for site %s",
        site,
    )

    return {}


async def crawl_async(
    config: CrawlConfig,
    out_root: str | Path = "data",
    run_id: str | None = None,
) -> Path:
    """Capture one site asynchronously and write its crawl artifacts."""

    if not config.seeds:
        raise ValueError(
            "Crawl configuration has no seeds"
        )

    if config.fetch.delay_seconds < 1.0:
        raise ValueError(
            "delay_seconds must be at least 1.0"
        )

    if config.fetch.concurrency < 1:
        raise ValueError(
            "concurrency must be at least 1"
        )

    run_id = (
        run_id
        or _make_run_id(
            config.site
        )
    )

    previous_page_hashes = (
        _load_previous_page_hashes(
            out_root=out_root,
            site=config.site,
            current_run_id=run_id,
        )
    )

    run_dir = (
        Path(out_root)
        / "sites"
        / config.site
        / run_id
    )

    raw_dir = run_dir / "raw"
    docs_dir = run_dir / "docs"

    raw_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    docs_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    started_at = _utcnow()

    rules = ScopeRules(
        allowed_domains=config.allowed_domains,
        include_patterns=config.include_patterns,
        exclude_patterns=config.exclude_patterns,
        max_depth=config.max_depth,
    )

    frontier = Frontier(
        config.seeds,
        rules,
    )

    pages: list[CrawledPage] = []
    errors: list[dict] = []

    written_canonical_urls: set[str] = set()

    pages_fetched = 0
    pages_written = 0
    pages_skipped = 0
    documents_saved = 0

    pages_new = 0
    pages_changed = 0
    pages_unchanged = 0

    assets_saved: dict[str, str] = {}

    try:
        async with Fetcher(
            config.fetch
        ) as fetcher:

            while (
                frontier
                and pages_fetched
                < config.max_pages
            ):
                remaining = (
                    config.max_pages
                    - pages_fetched
                )

                batch_size = min(
                    config.fetch.concurrency,
                    remaining,
                )

                batch: list[
                    tuple[str, int]
                ] = []

                while (
                    frontier
                    and len(batch)
                    < batch_size
                ):
                    batch.append(
                        frontier.pop()
                    )

                if not batch:
                    break

                batch_urls = [
                    url
                    for url, _depth in batch
                ]

                depth_by_url = {
                    url: depth
                    for url, depth in batch
                }

                log.info(
                    "Crawling HTML batch: "
                    "size=%d remaining=%d",
                    len(batch_urls),
                    remaining,
                )

                try:
                    raw_pages = (
                        await fetcher.fetch_many(
                            batch_urls
                        )
                    )

                except Exception as exc:
                    pages_skipped += len(
                        batch_urls
                    )

                    errors.append(
                        {
                            "urls": batch_urls,
                            "stage": "fetch_batch",
                            "error": repr(exc),
                        }
                    )

                    log.exception(
                        "Failed to fetch HTML batch"
                    )

                    continue

                pages_skipped += max(
                    0,
                    len(batch_urls)
                    - len(raw_pages),
                )

                for raw_page in raw_pages:
                    if (
                        pages_fetched
                        >= config.max_pages
                    ):
                        break

                    pages_fetched += 1

                    depth = depth_by_url.get(
                        raw_page.url
                    )

                    if depth is None:
                        depth = min(
                            (
                                item_depth
                                for (
                                    _url,
                                    item_depth,
                                ) in batch
                            ),
                            default=0,
                        )

                    try:
                        discovered = discover(
                            raw_page.html,
                            raw_page.url,
                        )

                    except Exception as exc:
                        pages_skipped += 1

                        errors.append(
                            {
                                "url": raw_page.url,
                                "stage": "discover",
                                "error": repr(exc),
                            }
                        )

                        log.exception(
                            "Failed to discover "
                            "page metadata for %s",
                            raw_page.url,
                        )

                        continue

                    canonical_source = (
                        discovered.canonical_url
                        or raw_page.url
                    )

                    try:
                        canonical_url = canonicalize(
                            canonical_source
                        )

                    except ValueError:
                        log.warning(
                            "Invalid canonical URL %s; "
                            "falling back to fetched URL",
                            canonical_source,
                        )

                        try:
                            canonical_url = canonicalize(
                                raw_page.url
                            )

                        except ValueError:
                            pages_skipped += 1

                            errors.append(
                                {
                                    "url": raw_page.url,
                                    "stage": "canonicalize",
                                    "error": (
                                        "Invalid canonical URL: "
                                        f"{canonical_source}"
                                    ),
                                }
                            )

                            continue

                    if canonical_url in written_canonical_urls:
                        pages_skipped += 1

                        log.info(
                            "Skipping duplicate "
                            "canonical page: %s",
                            canonical_url,
                        )

                        try:
                            frontier.add_links(
                                raw_page.url,
                                discovered.links,
                                depth,
                            )

                        except Exception as exc:
                            errors.append(
                                {
                                    "url": raw_page.url,
                                    "stage": (
                                        "discover_links_duplicate"
                                    ),
                                    "error": repr(exc),
                                }
                            )

                            log.exception(
                                "Failed to add links "
                                "from duplicate page %s",
                                raw_page.url,
                            )

                        continue

                    raw_hash = _raw_content_hash(
                        raw_page.html
                    )

                    normalized_hash = (
                        _normalized_content_hash(
                            raw_page.html
                        )
                    )

                    previous_normalized_hash = (
                        previous_page_hashes.get(
                            canonical_url
                        )
                    )

                    if previous_normalized_hash is None:
                        change_status = "new"

                    elif previous_normalized_hash == normalized_hash:
                        change_status = "unchanged"

                    else:
                        change_status = "changed"

                    page_id = make_doc_id(
                        canonical_url
                    )

                    html_subfolder = _document_subfolder(
                        raw_page.url
                    )

                    html_subfolder_dir = (
                        raw_dir / html_subfolder
                    )

                    html_subfolder_dir.mkdir(
                        parents=True,
                        exist_ok=True,
                    )

                    html_filename = (
                        f"{page_id}.html"
                    )

                    html_path = (
                        html_subfolder_dir
                        / html_filename
                    )

                    try:
                        # Raw bytes/content remain untouched for downstream.
                        html_path.write_text(
                            raw_page.html,
                            encoding="utf-8",
                        )

                    except OSError as exc:
                        pages_skipped += 1

                        errors.append(
                            {
                                "url": raw_page.url,
                                "stage": "write_html",
                                "error": repr(exc),
                            }
                        )

                        log.exception(
                            "Failed to save HTML "
                            "for %s",
                            raw_page.url,
                        )

                        continue

                    written_canonical_urls.add(
                        canonical_url
                    )

                    relative_content_path = str(
                        Path("raw")
                        / html_subfolder
                        / html_filename
                    ).replace(
                        "\\",
                        "/",
                    )

                    page_record = CrawledPage(
                        page_id=page_id,
                        url=raw_page.url,
                        canonical_url=canonical_url,
                        status=raw_page.status,
                        content_type=(
                            raw_page.headers.get(
                                "Content-Type",
                                (
                                    "text/html; "
                                    "charset=utf-8"
                                ),
                            )
                        ),
                        content_path=(
                            relative_content_path
                        ),
                        fetched_at=(
                            raw_page
                            .fetched_at
                            .isoformat()
                        ),
                        depth=depth,
                        links=discovered.links,
                        document_links=(
                            discovered.document_links
                        ),
                        parent_url="",
                        meta={
                            "lang": discovered.lang,
                            "elapsed_ms": (
                                raw_page.elapsed_ms
                            ),
                            "fetcher": (
                                raw_page.headers.get(
                                    "X-Cortex-Fetcher",
                                    "crawl4ai",
                                )
                            ),

                            # Kept for compatibility with the first
                            # change-detection implementation.
                            "content_sha256": (
                                raw_hash
                            ),

                            "raw_content_sha256": (
                                raw_hash
                            ),

                            "normalized_content_sha256": (
                                normalized_hash
                            ),

                            "change_status": (
                                change_status
                            ),
                        },
                    )

                    pages.append(
                        page_record
                    )

                    pages_written += 1

                    if change_status == "new":
                        pages_new += 1

                    elif (
                        change_status
                        == "changed"
                    ):
                        pages_changed += 1

                    else:
                        pages_unchanged += 1

                    log.debug(
                        "Normalized change status: "
                        "%s -> %s",
                        canonical_url,
                        change_status,
                    )

                    try:
                        frontier.add_links(
                            raw_page.url,
                            discovered.links,
                            depth,
                        )

                    except Exception as exc:
                        errors.append(
                            {
                                "url": raw_page.url,
                                "stage": "discover_links",
                                "error": repr(exc),
                            }
                        )

                        log.exception(
                            "Failed to add discovered "
                            "links from %s",
                            raw_page.url,
                        )

                    if (
                        config.assets.download_documents
                        and documents_saved
                        < config.assets.max_documents
                    ):
                        for document_url in (
                            discovered.document_links
                        ):
                            if (
                                documents_saved
                                >= config.assets.max_documents
                            ):
                                break

                            if (
                                document_url
                                in assets_saved
                            ):
                                continue

                            if not rules.in_scope(
                                document_url,
                                0,
                            ):
                                continue

                            document_ordinal = (
                                documents_saved + 1
                            )

                            try:
                                asset = (
                                    await asyncio.to_thread(
                                        fetcher.fetch_asset,
                                        document_url,
                                    )
                                )

                            except Exception as exc:
                                errors.append(
                                    {
                                        "url": (
                                            document_url
                                        ),
                                        "stage": (
                                            "fetch_document"
                                        ),
                                        "error": repr(exc),
                                    }
                                )

                                log.exception(
                                    "Failed to fetch "
                                    "document %s",
                                    document_url,
                                )

                                continue

                            if asset is None:
                                continue

                            subfolder = _document_subfolder(
                                document_url
                            )

                            filename = _document_filename(
                                document_url,
                                document_ordinal,
                            )

                            subfolder_dir = (
                                docs_dir / subfolder
                            )

                            subfolder_dir.mkdir(
                                parents=True,
                                exist_ok=True,
                            )

                            document_path = (
                                subfolder_dir
                                / filename
                            )

                            try:
                                document_path.write_bytes(
                                    asset.content
                                )

                            except OSError as exc:
                                errors.append(
                                    {
                                        "url": (
                                            document_url
                                        ),
                                        "stage": (
                                            "write_document"
                                        ),
                                        "error": repr(exc),
                                    }
                                )

                                log.exception(
                                    "Failed to save "
                                    "document %s",
                                    document_url,
                                )

                                continue

                            documents_saved += 1

                            relative_document_path = str(
                                Path("docs")
                                / subfolder
                                / filename
                            ).replace(
                                "\\",
                                "/",
                            )

                            assets_saved[
                                document_url
                            ] = (
                                relative_document_path
                            )

                            log.info(
                                "Saved document %s -> %s",
                                document_url,
                                relative_document_path,
                            )

    except Exception as exc:
        errors.append(
            {
                "stage": "crawl",
                "error": repr(exc),
            }
        )

        log.exception(
            "Unexpected crawler error"
        )

    pages_jsonl = (
        run_dir
        / "pages.jsonl"
    )

    _write_jsonl(
        pages_jsonl,
        [
            {
                "page_id": page.page_id,
                "url": page.url,
                "canonical_url": (
                    page.canonical_url
                ),
                "status": page.status,
                "content_type": (
                    page.content_type
                ),
                "content_path": (
                    page.content_path
                ),
                "fetched_at": (
                    page.fetched_at
                ),
                "depth": page.depth,
                "links": page.links,
                "document_links": (
                    page.document_links
                ),
                "parent_url": (
                    page.parent_url
                ),
                "meta": page.meta,
            }
            for page in pages
        ],
    )

    finished_at = _utcnow()

    manifest = CrawlManifest(
        run_id=run_id,
        site=config.site,
        seeds=config.seeds,
        started_at=(
            started_at.isoformat()
        ),
        finished_at=(
            finished_at.isoformat()
        ),
        pages_fetched=pages_fetched,
        pages_written=pages_written,
        pages_skipped=pages_skipped,
        errors=errors,
        config=_config_to_dict(
            config
        ),
        assets_saved=assets_saved,
        documents_parsed=0,
    )

    manifest_path = (
        run_dir
        / "manifest.json"
    )

    manifest_path.write_text(
        json.dumps(
            {
                "run_id": manifest.run_id,
                "site": manifest.site,
                "seeds": manifest.seeds,
                "started_at": (
                    manifest.started_at
                ),
                "finished_at": (
                    manifest.finished_at
                ),
                "pages_fetched": (
                    manifest.pages_fetched
                ),
                "pages_written": (
                    manifest.pages_written
                ),
                "pages_skipped": (
                    manifest.pages_skipped
                ),
                "errors": manifest.errors,
                "config": manifest.config,
                "assets_saved": (
                    manifest.assets_saved
                ),
                "documents_parsed": (
                    manifest.documents_parsed
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    log.info(
        "Crawl complete: site=%s "
        "pages=%d new=%d changed=%d unchanged=%d "
        "documents=%d errors=%d run=%s",
        config.site,
        pages_written,
        pages_new,
        pages_changed,
        pages_unchanged,
        documents_saved,
        len(errors),
        run_dir,
    )

    return run_dir


def crawl(
    config: CrawlConfig,
    out_root: str | Path = "data",
    run_id: str | None = None,
) -> Path:
    """Synchronous CLI-compatible wrapper around the async crawler."""

    return asyncio.run(
        crawl_async(
            config=config,
            out_root=out_root,
            run_id=run_id,
        )
    )


def load_config(
    path: str | Path,
) -> CrawlConfig:
    """Load a CrawlConfig from YAML."""

    with Path(path).open(
        "r",
        encoding="utf-8",
    ) as handle:
        payload = (
            yaml.safe_load(handle)
            or {}
        )

    return CrawlConfig.from_dict(
        payload
    )