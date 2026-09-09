"""Stage 4: render the residual pages in a browser. Spec §6.10.

After the 2026-09-08 revision this is the SMALLEST stage, not the largest — a
few dozen URLs the API does not cover, rather than the ~525 the original design
put through Chromium.

All of §7.2's failed-render machinery is kept regardless. It now guards fewer
pages, but they are precisely the pages with no API second source, which makes a
silent empty capture here unrecoverable rather than merely annoying.

crawl4ai is an optional dependency (`uv sync --extra browser`), so this module
is imported late and says something useful when it is missing.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .builders.base import Document, Stage2Result, harvest
from .content import rows_on_disk, write_document, write_shard
from .paths import canonical, group_for_url, page_path, section_for_url

log = logging.getLogger(__name__)


def _require_crawl4ai():
    try:
        from crawl4ai import (AsyncWebCrawler, BrowserConfig, CacheMode,  # noqa
                              CrawlerRunConfig)
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    except ImportError as exc:
        raise SystemExit(
            "Stage 4 needs crawl4ai, which is an optional extra.\n"
            "  uv sync --extra browser\n"
            "  uv run crawl4ai-setup      # installs the browser, once\n"
            "\n"
            "Stages discover, content, files and audit need no browser and are "
            "unaffected - that ordering is deliberate (spec §5)."
        ) from exc
    return (AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig,
            DefaultMarkdownGenerator)


def render_failed(markdown: str, html: str) -> tuple[bool, str]:
    """Detect a page whose JavaScript did not run. Spec §7.2.

    Two conditions, because a length threshold alone is not sufficient. The
    hybrid rendering in §2 means `/academic-information/academic-calendars`
    returns its title, breadcrumb and sidebar while its data grid is empty — it
    comfortably exceeds any threshold set for the fully-empty case.
    """
    if len(markdown.strip()) < config.EMPTY_RENDER_THRESHOLD:
        return True, "below_threshold"
    if config.EMPTY_TABLE_RE.search(html):
        # The data component mounted and received nothing. A failure even on an
        # otherwise well-populated page.
        return True, "empty_data_grid"
    return False, ""


def looks_not_found(markdown: str) -> bool:
    """Content-based 404 detection. Spec §4.5.

    Status codes cannot be used: a Next.js `[slug]` route returns HTTP 200 for
    any slug and renders not-found on the client. Twelve URLs were tested,
    including a known misspelling; every one returned 200.

    Two tiers. The exact sentence the site's error component renders is matched
    ANYWHERE, because the 404 is drawn inside the normal layout and sits below
    the whole navigation. The loose markers stay confined to the opening, where
    a real page would not begin with them, so that an article about HTTP status
    codes is not mistaken for one.

    Checking only the opening is what let 18 `/dept/<slug>/postgraduate` 404s
    into the corpus as real documents.
    """
    text = markdown.lower()
    if any(marker in text for marker in config.NOT_FOUND_BODY_MARKERS):
        return True
    head = text[:config.NOT_FOUND_HEAD_CHARS]
    return any(marker in head for marker in config.NOT_FOUND_HEAD_MARKERS)


def looks_placeholder(markdown: str) -> bool:
    """True when the page exists but CUET has not published its content yet.

    Distinct from `looks_not_found` on purpose. A 404 is a page that is not
    there and must never become a document; a placeholder IS the page, and the
    fact that the curriculum is unpublished is itself true of the site today.
    Twenty of the 36 per-department academic pages are in this state.

    The caller records it as `content_state` rather than dropping the document,
    because spec 4.4 puts thin-page filtering downstream where it can be
    revisited without another crawl.
    """
    text = markdown.lower()
    return any(marker in text for marker in config.PLACEHOLDER_MARKERS)


def _load_plan(out: Path, sections: list[str] | None, limit: int | None,
               force: bool) -> list[tuple[str, str]]:
    path = out / "_meta" / "urls.txt"
    if not path.exists():
        raise SystemExit(f"{path} not found. Run --stage discover first.")

    planned: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        url, _, why = line.partition("\t")
        planned.append((url.strip(), why.lstrip("# ").strip()))

    if sections:
        planned = [(u, w) for u, w in planned if section_for_url(u) in sections]

    if not force:
        # The .json is the completion marker because it is written last: if HTML
        # exists but JSON does not, the page was interrupted and is retried,
        # which is correct. Spec §7.1.
        planned = [(u, w) for u, w in planned
                   if not page_path(u, "json", root=out).exists()]

    # --limit applies AFTER every other filter, so the first run of a new
    # configuration is cheap. Spec §5.
    return planned[:limit] if limit else planned


def run(client, out: Path | None = None, *, limit: int | None = None,
        sections: list[str] | None = None, force: bool = False) -> dict:
    out = out or config.OUT
    plan = _load_plan(out, sections, limit, force)
    if not plan:
        log.info("capture: nothing to do (all planned URLs already captured)")
        return {"captured": 0, "failed_renders": 0, "not_found": 0, "errors": []}

    log.info("capture: %d URLs planned", len(plan))
    return asyncio.run(_capture_all(plan, out, force=force))


async def _capture_all(plan: list[tuple[str, str]], out: Path, *,
                       force: bool = False) -> dict:
    (AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig,
     DefaultMarkdownGenerator) = _require_crawl4ai()

    browser = BrowserConfig(
        headless=True,
        user_agent=config.USER_AGENT,
        viewport_width=1920,
        viewport_height=1080,
    )
    md_generator = DefaultMarkdownGenerator(
        # Alt text is prose and belongs in the text; an image link is something
        # nothing downstream may fetch. Spec §4.6.
        options={"ignore_images": True, "image_alt_text": True},
    )
    run_config = CrawlerRunConfig(
        page_timeout=config.PAGE_TIMEOUT_MS,
        # BYPASS when --force, ENABLED otherwise. Spec §6.10 wants ENABLED during
        # development so repeated tuning runs do not re-hit the server — but the
        # cache will happily serve a BAD render forever, which is exactly what
        # happened here: three chrome-only pages were cached, and every retry
        # returned the cached emptiness in ~1s instead of re-rendering.
        # --force must therefore invalidate the cache, not just the resume check.
        cache_mode=CacheMode.BYPASS if force else CacheMode.ENABLED,
        # VERIFIED 2026-09-08. An anchor-count condition cannot work here at any
        # threshold — the chrome alone has 182 anchors, so it is true at first
        # paint and the capture beats the data. Time is the reliable signal.
        # See config.WAIT_FOR for the measurements.
        wait_for=config.WAIT_FOR,
        delay_before_return_html=config.RENDER_DELAY_SECONDS,
        markdown_generator=md_generator,
        # OFF, contradicting spec §6.10's suggested config. VERIFIED 2026-09-08:
        # on this site the overlay heuristic deletes the CONTENT. Same page,
        # same delay, only this flag changed:
        #
        #   remove_overlay_elements=True    html 101,211   markdown  7,343
        #   remove_overlay_elements=False   html 168,019   markdown 18,817
        #
        # The news and event cards are being classified as overlays and stripped.
        # There are no cookie banners or modals on cuet.ac.bd for it to remove,
        # so the flag has nothing to gain here and 11k of content to lose.
        remove_overlay_elements=False,
        exclude_external_links=False,
    )

    result_bag = Stage2Result()
    rows: list[dict] = []
    errors: list[dict] = []
    captured = failed = not_found = 0
    semaphore = asyncio.Semaphore(config.CAPTURE_CONCURRENCY)

    async with AsyncWebCrawler(config=browser) as crawler:
        async def one(url: str, why: str) -> None:
            nonlocal captured, failed, not_found
            async with semaphore:
                for attempt in range(1, config.MAX_RETRIES + 1):
                    try:
                        res = await crawler.arun(url=url, config=run_config)
                    except Exception as exc:              # noqa: BLE001
                        errors.append({"url": url, "stage": "capture",
                                       "error": type(exc).__name__,
                                       "message": str(exc), "attempt": attempt,
                                       "when": _now()})
                        await asyncio.sleep(config.DELAY * attempt)
                        continue

                    html = res.html or ""
                    markdown = str(getattr(res, "markdown", "") or "")

                    if looks_not_found(markdown):
                        not_found += 1
                        errors.append({"url": url, "stage": "capture",
                                       "error": "NotFound",
                                       "message": "content-based 404, HTTP was "
                                                  f"{getattr(res, 'status_code', '?')}",
                                       "attempt": attempt, "when": _now()})
                        return

                    bad, reason = render_failed(markdown, html)
                    if bad:
                        if attempt < config.MAX_RETRIES:
                            log.warning("render failed (%s) on %s; retry %d "
                                        "[md=%d html=%d]",
                                        reason, url, attempt, len(markdown), len(html))
                            await asyncio.sleep(config.DELAY * attempt)
                            continue
                        failed += 1
                        # Never saved as a valid page. Spec §7.2.
                        errors.append({"url": url, "stage": "capture",
                                       "error": "FailedRender", "message": reason,
                                       "attempt": attempt, "when": _now()})
                        return

                    doc = Document(
                        url=url, title=_title(res, url), html=html,
                        section=section_for_url(url) or "_unsorted",
                        group=group_for_url(url),
                        section_path=_breadcrumb(url),
                        source="browser",
                        extra={"planned_reason": why, "render_ok": True,
                               "content_state": ("placeholder"
                                                 if looks_placeholder(markdown)
                                                 else "published")},
                    )
                    doc.files = harvest(html, url, result_bag,
                                        linked_from=url,
                                        meta={"document_type": "page"})
                    # The row was previously discarded, which meant a
                    # browser-captured page landed on disk and then reached
                    # nothing: no documents.jsonl, no pages.jsonl, no manifest
                    # count. Three real captures sat orphaned that way. Keeping
                    # it puts browser pages through the same shard-and-merge
                    # path as everything else.
                    rows.append(write_document(doc, out))
                    captured += 1
                    log.info("capture %6d chars  %s", len(markdown), url)
                    return

                errors.append({"url": url, "stage": "capture",
                               "error": "GaveUp", "message": "all attempts failed",
                               "attempt": config.MAX_RETRIES, "when": _now()})

        # Sleep DELAY * batch between batches, so the effective per-host rate
        # stays polite regardless of concurrency. Spec §6.10.
        batch = config.CAPTURE_CONCURRENCY
        for start in range(0, len(plan), batch):
            group = plan[start:start + batch]
            await asyncio.gather(*(one(u, w) for u, w in group))
            await asyncio.sleep(config.DELAY * len(group))

    if rows:
        rebuild_shard(out)

    meta = out / "_meta"
    _merge_found(meta / "found_files.json", result_bag.found_files)
    _append_lines(meta / "found_pages.txt", result_bag.found_pages)

    log.info("capture: %d captured, %d failed renders, %d not found, %d errors",
             captured, failed, not_found, len(errors))
    return {"captured": captured, "failed_renders": failed,
            "not_found": not_found, "errors": errors}


def rebuild_shard(out: Path | None = None) -> Path:
    """Rebuild the browser shard from the HTML already on disk. No network.

    Stage 4 owns one shard, exactly as each content portion owns one. It is
    named for the stage rather than for a person because what lands here is
    decided by the residual URL plan, not by whose slice of the site it is.

    Two things make this a function rather than four lines inside the run:

    **It reads what is on disk, not what this run rendered.** Stage 4 is
    resumable and skips URLs already captured, so the rows from one run hold
    only the new pages. Building the shard from those drops everything captured
    before, silently.

    **It re-harvests the links.** The saved HTML is the same bytes the browser
    returned, so changing what `harvest` considers a link does not require
    fetching those pages again. That is the property spec §4.4 asks for, and it
    is what made fixing the HTML-entity bug cost a second rather than 61
    requests to a university's servers.

        python -m engine.crawler.cuet --stage reharvest
    """
    out = out or config.OUT
    rows = rows_on_disk(out, source="browser")
    if not rows:
        log.info("reharvest: no browser documents on disk")
        return out / "_shards" / "browser.json"

    result = Stage2Result()
    for row in rows:
        html_path = out / row["html_path"]
        if not html_path.is_file():
            log.warning("%s has no HTML at %s", row.get("page_id"), row["html_path"])
            continue
        row["files"] = harvest(
            html_path.read_text(encoding="utf-8"), row["url"], result,
            linked_from=row["url"], meta={"document_type": "page"},
        )
        _backfill_content_state(row, out)

    path = write_shard(out, ["browser"], rows, result)
    log.info("reharvest: %d documents, %d files, %d pages discovered",
             len(rows), len(result.found_files), len(result.found_pages))
    return path


def _backfill_content_state(row: dict, out: Path) -> None:
    """Give an older sidecar the `content_state` field, from bytes on disk.

    Documents captured before placeholder detection existed carry no such key.
    Recomputing it from the saved markdown is the same offline-repair property
    that made the HTML-entity fix cost one second instead of 61 requests, so a
    metadata field added later never means re-crawling a university's site.

    Only written when the value actually changes, so a rebuild of an already
    correct corpus stays byte-identical and produces no diff.
    """
    state = "placeholder" if looks_placeholder(row.get("_text", "")) else "published"
    if row.get("content_state") == state:
        return
    row["content_state"] = state
    sidecar = row.get("_json_path")
    if not sidecar:
        return
    payload = {k: v for k, v in row.items() if not k.startswith("_")}
    sidecar.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _title(res, url: str) -> str:
    meta = getattr(res, "metadata", None) or {}
    return (meta.get("title") or url.rstrip("/").rsplit("/", 1)[-1] or url).strip()


def _breadcrumb(url: str) -> list[str]:
    section = section_for_url(url)
    group = group_for_url(url)
    crumb = [section.replace("-", " ").title()]
    if group:
        crumb.append(group.replace("-", " ").title())
    tail = canonical(url).rstrip("/").rsplit("/", 1)[-1]
    if tail:
        crumb.append(tail)
    return crumb


def _merge_found(path: Path, found: dict) -> None:
    existing = {}
    if path.exists():
        existing = {r["url"]: r for r in json.loads(path.read_text(encoding="utf-8"))}
    for url, record in found.items():
        if url in existing:
            merged = set(existing[url].get("linked_from", [])) | set(record.get("linked_from", []))
            existing[url]["linked_from"] = sorted(merged)
        else:
            existing[url] = record
    path.write_text(json.dumps(list(existing.values()), ensure_ascii=False, indent=2),
                    encoding="utf-8")


def _append_lines(path: Path, values: set[str]) -> None:
    existing = set()
    if path.exists():
        existing = {line.strip()
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip()}
    path.write_text("\n".join(sorted(existing | values)) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
