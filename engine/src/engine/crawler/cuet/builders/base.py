"""Shared vocabulary for the builders: the document model and the helpers.

Split out of `content.py` so that four people can each own a builder module
without any of them editing a file the others also edit. Nothing here is
portion-specific — if you find yourself adding something that only your portion
needs, it belongs in your own module, not in this one.

Spec: CUET_SCRAPER_SPEC.md §6.8.
"""

from __future__ import annotations

import html as html_module
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin

from .. import config
from ..markdown import unescape_once
from ..paths import canonical, is_excluded_url, is_image_url, looks_like_file

log = logging.getLogger(__name__)

_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
_SRC_RE = re.compile(r'src=["\']([^"\']+)["\']', re.I)
# Bare document URLs, for files that appear in text rather than inside an <a>.
_FILE_URL_RE = re.compile(
    r'https?://[^\s"\'<>]+?\.(?:pdf|docx?|xlsx?|pptx?|zip|csv)', re.I
)
# Unescaping a CMS value leaves the wrapper its editor put around it holding
# block-level children: `<p><p>text</p><ul>...</ul></p>`. No parser keeps that
# nesting — every one auto-closes the outer <p> at the first block child — so
# the tree the markdown converter walks stops matching the tree the .html file
# shows. These patterns delete the wrapper rather than leave it to be guessed.
#
# Both match only sequences that cannot occur in valid HTML (`<p><p`, `<p><ul`,
# or `</ul></p>` with no opener), so well-formed values are left alone.
_BLOCK_IN_P = ("p", "ul", "ol", "div", "table", "blockquote",
               "h1", "h2", "h3", "h4", "h5", "h6")
_P_BEFORE_BLOCK = re.compile(
    r"<p\s*>\s*(?=<(?:" + "|".join(_BLOCK_IN_P) + r")\b)", re.I)
_P_AFTER_BLOCK = re.compile(
    r"(</(?:" + "|".join(_BLOCK_IN_P) + r")>\s*)</p\s*>", re.I)
# A bare `&` is what unescaping a legitimate `&amp;` leaves behind ("Industry &
# Government Collaboration"). Entities that are already well formed stay as they
# are; `convert_charrefs` decodes both, so the markdown is identical either way.
_BARE_AMP = re.compile(r"&(?!(?:[a-zA-Z][a-zA-Z0-9]*|#\d+|#[xX][0-9a-fA-F]+);)")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Document:
    """One captured document, before it is written to disk.

    `url` and `key` are separate on purpose.

    * **`url` is what a citation shows a reader**, so it must be a page that
      actually resolves on cuet.ac.bd.
    * **`key` is what the document is identified by** — it becomes `doc_id` and
      the filename.

    They differ only where one real page yields several documents: the 265 NOC
    notices are one listing page but five index documents, and those five need
    distinct ids while still citing the page a reader can open. Defaulting `key`
    to `url` keeps the ordinary case a single value.

    **A key must survive canonicalisation.** `page_id()` canonicalises before
    hashing and `canonical()` strips fragments (spec §6.3), so a `#part-2`
    suffix silently collapses every part onto one id — which is exactly what
    happened on the first run here. Use a query parameter instead;
    canonicalisation preserves those. `_part` is named with a leading
    underscore to mark it as ours rather than something the site would accept.
    """
    url: str
    title: str
    html: str
    section: str
    group: str
    section_path: list[str]
    key: str = ""
    source: str = "api"
    extra: dict = field(default_factory=dict)
    files: list[dict] = field(default_factory=list)
    double_escaped: bool = False

    def __post_init__(self) -> None:
        if not self.key:
            self.key = self.url


@dataclass
class Stage2Result:
    documents: list[Document] = field(default_factory=list)
    found_files: dict[str, dict] = field(default_factory=dict)
    found_pages: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)   # written metadata records


# --------------------------------------------------------------------------
# Link and file harvesting
# --------------------------------------------------------------------------

def harvest(html: str, base: str, result: Stage2Result, *,
            linked_from: str, meta: dict | None = None) -> list[dict]:
    """Pull links and document URLs out of a block of HTML.

    CMS HTML contains real URLs the navigation never shows — `/admission/msc/`,
    `admissionckruet.ac.bd`, and the vendor domain from spec §4.11 — so the same
    filtering pipeline runs over it. Spec §6.8.

    Returns the document links found, and records everything in `result`.
    """
    files: list[dict] = []
    if not html:
        return files

    candidates = set(_HREF_RE.findall(html)) | set(_SRC_RE.findall(html))
    candidates |= set(_FILE_URL_RE.findall(html))

    for raw in candidates:
        # An href in HTML is entity-encoded: the faculty slug that reads
        # `architecture-&-planning` in a URL bar is written
        # `architecture-&amp;-planning` in the markup. Without decoding, every
        # such link is recorded as a URL that does not exist.
        #
        # This is not a rare edge: 903 of 1,127 harvested URLs carried a raw
        # `&amp;` before this was added, and it made the Appendix B gap diff
        # unusable — three faculty pages that ARE in the corpus were reported
        # as never captured, because the discovered form and the stored form
        # were different strings.
        #
        # Decoded before anything else touches it, so the scheme filter, the
        # image check and canonicalisation all see the real URL. Spec §4.2,
        # which documents the ampersand slugs.
        raw = html_module.unescape(raw.strip())
        # Filter by scheme before anything tries to fetch. The page carries
        # href="#" on every dropdown toggle, plus mailto:undefined and
        # tel:undefined, which are the site's own bugs. Spec §4.8.
        if not raw or raw.startswith(("#", "javascript:", "data:")):
            continue
        if raw.startswith(("mailto:", "tel:")):
            continue

        url = canonical(urljoin(base, raw))
        parts = url.split("://", 1)
        if len(parts) != 2 or not parts[0].startswith("http"):
            continue

        # Images are refused here rather than later. Note that CMS HTML holds
        # RELATIVE image paths such as /assets/images/undergraduate.jpg, which
        # only look like images after being resolved against the base. Spec §4.6.
        if is_image_url(url):
            continue
        if is_excluded_url(url):
            continue

        if looks_like_file(url):
            record = result.found_files.setdefault(
                url, {"url": url, "linked_from": [], **(meta or {})}
            )
            # linked_from accumulates: the same PDF is linked from many pages.
            # Overwriting would lose every source but the last. Part 2 §12.3.
            if linked_from not in record["linked_from"]:
                record["linked_from"].append(linked_from)
            files.append({"url": url})
        else:
            result.found_pages.add(url)

    return files


def _normalise_unescaped(html: str) -> str:
    """Make an unescaped CMS value well formed.

    Unescaping is only half the job. The value arrives as a real wrapper around
    escaped markup — `<h2>..</h2><p>&lt;p&gt;..&lt;ul&gt;..`  — so once the
    inner layer becomes tags, that wrapper holds block children and the document
    is no longer well formed. Dropping the wrapper is what the parsers do
    silently anyway; doing it here means the .html on disk says the same thing
    they infer.
    """
    for pattern, repl in ((_P_BEFORE_BLOCK, ""), (_P_AFTER_BLOCK, r"\1")):
        for _ in range(10):  # bounded: nesting this deep is already a bug
            html, n = pattern.subn(repl, html)
            if not n:
                break
    return _BARE_AMP.sub("&amp;", html)


def _clean_html(value: str, result: Stage2Result, label: str) -> tuple[str, bool]:
    """Return (html, was_escaped). Spec §3.3, §6.8.

    The flag is named `double_escaped` throughout for continuity, but what is
    actually found in the wild is ONE escaped layer inside an unescaped wrapper:
    `&amp;lt;` appears nowhere in the corpus. Unescaping twice would corrupt it.
    """
    if value and any(marker in value for marker in config.DOUBLE_ESCAPE_MARKERS):
        log.warning("escaped markup in CMS value: %s (unescaping once)", label)
        result.warnings.append(f"double_escaped:{label}")
        return _normalise_unescaped(unescape_once(value)), True
    return value or "", False


# --------------------------------------------------------------------------
# Builders, one per API source
# --------------------------------------------------------------------------

def _body(block) -> dict | list | None:
    if isinstance(block, dict) and "body" in block:
        return block["body"]
    return None


def _rows(block, key: str = "data") -> list[dict]:
    body = _body(block)
    if isinstance(body, dict):
        rows = body.get(key)
    elif isinstance(body, list):
        rows = body
    else:
        rows = None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _setting_value(settings: dict, key: str) -> str:
    """Read one /general-settings value.

    VERIFIED 2026-09-08: every setting is wrapped as `{"id", "key", "value"}`,
    with the HTML in `value` — NOT a bare string as spec §3.3 describes. The
    plain-string form is still accepted here in case the wrapper is a newer
    addition and an older dump is replayed.
    """
    raw = settings.get(key)
    if isinstance(raw, dict):
        raw = raw.get("value")
    return raw if isinstance(raw, str) else ""


def _headline_body(title: str, facts: list[tuple[str, object]]) -> str:
    """A minimal body for a record whose `description` is empty.

    Some news and event records carry no description at all — but a headline
    and a date ARE content, and one such event carries the only link to
    `ecce2027.cuet.ac.bd` anywhere on the site.

    An earlier version dropped these as "no text after conversion", which was
    wrong: it conflated *an item with a short body* with *a failed capture*.
    Spec §4.4 forbids exactly that — thin-page filtering belongs downstream,
    where it can be reconsidered without a re-crawl. The only thing that should
    ever be dropped here is a record with no title either.
    """
    parts = [f"<h1>{title}</h1>"]
    for label, value in facts:
        if value:
            parts.append(f"<p>{label}: {value}</p>")
    return "\n".join(parts)

