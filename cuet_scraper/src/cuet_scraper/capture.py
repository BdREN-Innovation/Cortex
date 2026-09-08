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
from .content import Document, Stage2Result, harvest, write_document
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
    """
    head = markdown[:600].lower()
    return any(marker in head for marker in config.NOT_FOUND_MARKERS)


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
    return asyncio.run(_capture_all(plan, out))


async def _capture_all(plan: list[tuple[str, str]], out: Path) -> dict:
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
        cache_mode=CacheMode.ENABLED,
        # UNVERIFIED (spec §6.10). Validate against one department page before a
        # full run; alternatives are wait_for="css:table" or a longer timeout
        # with no wait condition.
        wait_for="js:document.querySelectorAll('a').length > 40",
        markdown_generator=md_generator,
        remove_overlay_elements=True,
        exclude_external_links=False,
    )

    result_bag = Stage2Result()
    errors: list[dict] = []
    captured = failed = not_found = 0
    semaphore = asyncio.Semaphore(config.MAX_CONCURRENT)

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
                            log.warning("render failed (%s) on %s; retry %d",
                                        reason, url, attempt)
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
                        extra={"planned_reason": why, "render_ok": True},
                    )
                    doc.files = harvest(html, url, result_bag,
                                        linked_from=url,
                                        meta={"document_type": "page"})
                    write_document(doc, out)
                    captured += 1
                    log.info("capture %6d chars  %s", len(markdown), url)
                    return

                errors.append({"url": url, "stage": "capture",
                               "error": "GaveUp", "message": "all attempts failed",
                               "attempt": config.MAX_RETRIES, "when": _now()})

        # Sleep DELAY * batch between batches, so the effective per-host rate
        # stays polite regardless of concurrency. Spec §6.10.
        batch = config.MAX_CONCURRENT
        for start in range(0, len(plan), batch):
            group = plan[start:start + batch]
            await asyncio.gather(*(one(u, w) for u, w in group))
            await asyncio.sleep(config.DELAY * len(group))

    meta = out / "_meta"
    _merge_found(meta / "found_files.json", result_bag.found_files)
    _append_lines(meta / "found_pages.txt", result_bag.found_pages)

    log.info("capture: %d captured, %d failed renders, %d not found, %d errors",
             captured, failed, not_found, len(errors))
    return {"captured": captured, "failed_renders": failed,
            "not_found": not_found, "errors": errors}


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
