"""Canonicalisation, stable IDs and filesystem paths.

Pure functions, no network, no I/O. This file determines document identity for
the whole system: get `canonical` wrong and you get duplicates, or worse, two
different pages collapsing into one.

Spec: CUET_SCRAPER_SPEC.md §6.3 to §6.5.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

# The engine's contract, not a copy of it. `make_doc_id` is sha256 of the
# canonical URL truncated to 16 hex chars, which is exactly what spec §6.4
# specifies — so importing it keeps one definition instead of two that drift.
# Spec §12.1.
from engine.contracts.documents import make_doc_id

from . import config

__all__ = [
    "canonical", "page_id", "safe_name", "encode_slug",
    "section_for_url", "group_for_url", "page_path",
    "is_image_url", "is_excluded_url", "in_allowed_host", "looks_like_file",
]

_DEFAULT_PORTS = {"http": "80", "https": "443"}
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
_MULTI_SLASH = re.compile(r"/{2,}")
_EXCLUDE_RE = [re.compile(p, re.I) for p in config.EXCLUDE_PATTERNS]
_IMAGE_RE = [re.compile(p, re.I) for p in config.IMAGE_URL_PATTERNS]


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------

def canonical(url: str) -> str:
    """Collapse the many URLs that mean one page into one string.

        https://CUET.ac.bd/a/           -> https://cuet.ac.bd/a
        https://cuet.ac.bd/a#section    -> https://cuet.ac.bd/a
        https://cuet.ac.bd//a//b        -> https://cuet.ac.bd/a/b
        https://cuet.ac.bd:443/a        -> https://cuet.ac.bd/a
        https://library.cuet.ac.bd/     -> https://library.cuet.ac.bd
        https://cuet.ac.bd/department/CE   unchanged: path case PRESERVED

    Host lowercased, default port dropped, fragment removed, repeated slashes in
    the path collapsed, query string preserved exactly as given.

    Two deliberate non-obvious choices:

    * **Path case is preserved.** `/department/cse` and `/department/CE` are
      different pages (spec §4.1). Lowercasing the path is a bug that silently
      merges documents; lowercasing the host is correct because DNS is
      case-insensitive.
    * **The query string is preserved verbatim, not sorted.** The engine's own
      `canonicalize` sorts params and strips tracking ones, which is right for a
      general crawler. Here the only query strings we construct are API calls
      such as `?academic_headers=1`, where the server's behaviour depends on
      them and no tracking params occur. Reordering would be safe today and is
      one CMS link away from not being.

    Collapsing repeated slashes matters concretely: the site emits
    `app.cuet.ac.bd//storage/Notices/x.pdf` from its own string concatenation
    (spec §4.7). The URL works, and without this the same file is stored twice.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()

    port = parts.port
    netloc = host
    if port is not None and str(port) != _DEFAULT_PORTS.get(scheme, ""):
        netloc = f"{host}:{port}"

    path = _MULTI_SLASH.sub("/", parts.path)
    if path.endswith("/") and path != "/":
        path = path.rstrip("/")
    if path == "/":
        path = ""

    return urlunsplit((scheme, netloc, path, parts.query, ""))


def page_id(url: str) -> str:
    """Stable 16-char id for a URL. Same value on every run and every machine.

    Delegates to the engine contract so this scraper's ids are the engine's ids.

    Note what is NOT used here: Python's built-in `hash()`. String hashing is
    randomised per process by default, so `hash()` returns a different value
    every run — which means every re-run writes new filenames instead of
    overwriting, and resumability silently breaks. Spec §6.4 records that an
    earlier draft made exactly this mistake.
    """
    return make_doc_id(canonical(url))


def encode_slug(slug: str) -> str:
    """Percent-encode a slug for use as a single URL path segment.

    Three of the five faculty slugs contain a literal `&`
    (`science-&-technology`), and so does the `l&e` section. An unencoded `&` in
    a path truncates the request at the ampersand and silently fetches the wrong
    thing. Spec §4.2.

    `safe=""` is the point: the default would leave `/` alone, and a slug is one
    segment, never a path.
    """
    return quote(slug, safe="")


# --------------------------------------------------------------------------
# Filesystem naming
# --------------------------------------------------------------------------

def safe_name(name: str, *, keep_extension: bool = True) -> str:
    """Turn anything derived from a remote URL into a safe filename component.

    Never let a remote URL determine a local path. Concretely, the site serves
    `Teacher List of CUET-2026 (26.07.2026).pdf` — spaces and parentheses — and
    `admissioncuet.ac.bd` serves percent-encoded names. Spec §4.7, §6.5.

    Percent-decode first, THEN sanitise. Doing it the other way round leaves
    `%2e%2e` intact, which decodes to `..` somewhere downstream.
    """
    decoded = unquote(name or "")
    # Normalise so that a composed and decomposed form of the same Bangla or
    # accented character cannot produce two different filenames.
    decoded = unicodedata.normalize("NFKC", decoded)

    stem, dot, ext = decoded.rpartition(".")
    if not keep_extension or not dot or len(ext) > 8 or not ext.isalnum():
        stem, ext = decoded, ""

    stem = _UNSAFE.sub("_", stem).strip("._-")
    ext = _UNSAFE.sub("_", ext).strip("._-")

    # Collapse the runs of underscores that sanitising a spaced name produces,
    # so "Teacher List of CUET (2026).pdf" does not become "Teacher_List__2026_".
    stem = re.sub(r"_{2,}", "_", stem).strip("._-")

    if not stem:
        stem = "index"

    # `..` must not survive in any form. After the substitution above a literal
    # ".." is already gone (dots are kept, but a bare ".." strips to empty and
    # falls back to "index"); this is the belt to that braces.
    stem = stem.replace("..", "_")

    suffix = f".{ext}" if ext else ""
    budget = config.MAX_NAME_LENGTH - len(suffix)
    if budget < 1:                      # pathological extension; drop it
        return stem[:config.MAX_NAME_LENGTH]
    return stem[:budget] + suffix


# --------------------------------------------------------------------------
# Section and group assignment
# --------------------------------------------------------------------------

def section_for_url(url: str) -> str:
    """Which section a URL belongs to. Spec §6.1.

    Applied in order: host rule wins, then an exact path match, then the
    LONGEST matching prefix, then `_unsorted`.

    Longest-prefix rather than first-match is what keeps `/department/` from
    being shadowed by a shorter unrelated prefix as the map grows.
    """
    parts = urlsplit(canonical(url))
    host, path = parts.netloc, parts.path or "/"

    for name, rule in config.SECTIONS.items():
        if host in rule.hosts:
            return name

    for name, rule in config.SECTIONS.items():
        if path in rule.exact:
            return name

    best_name, best_len = "_unsorted", -1
    for name, rule in config.SECTIONS.items():
        for prefix in rule.prefixes:
            if path.startswith(prefix) and len(prefix) > best_len:
                best_name, best_len = name, len(prefix)
    return best_name


def group_for_url(url: str) -> str:
    """Second-level folder, or "" for directly in the section folder. Spec §6.5."""
    parts = urlsplit(canonical(url))
    if parts.netloc == "admissioncuet.ac.bd":
        return "admissioncuet"
    path = parts.path or "/"
    best, best_len = "", -1
    for prefix, group in config.GROUPS:
        if path.startswith(prefix) and len(prefix) > best_len:
            best, best_len = group, len(prefix)
    return best


def page_path(url: str, extension: str, *, root: Path | None = None) -> Path:
    """`<OUT>/<section>/<group>/<slug>__<id8>.<extension>`. Spec §6.5.

    The `id8` suffix is load-bearing, not decoration. The API reports an
    institute slug as `IICT` while the site links `/institutes/iict`; on a
    case-insensitive filesystem — macOS, Windows, this machine — those two would
    overwrite each other. Spec §4.1.
    """
    root = root if root is not None else config.OUT
    parts = urlsplit(canonical(url))
    path = parts.path or "/"

    segments = [s for s in path.split("/") if s]
    if not segments:
        slug = "index"
    elif len(segments) >= 2 and any(
        path.startswith(p) for p in config.TWO_SEGMENT_PREFIXES
    ):
        # /department/cse/contact -> cse__contact, not a bare "contact" that
        # collides across all 18 departments.
        slug = f"{safe_name(segments[-2], keep_extension=False)}__" \
               f"{safe_name(segments[-1], keep_extension=False)}"
    else:
        slug = safe_name(segments[-1], keep_extension=False)

    stem = f"{slug}__{page_id(url)[:8]}"
    section = config.SECTIONS.get(section_for_url(url))
    subdir = section.subdir if section else "_unsorted"
    group = group_for_url(url)

    folder = root / subdir / group if group else root / subdir
    return folder / f"{stem}.{extension.lstrip('.')}"


# --------------------------------------------------------------------------
# Filtering
# --------------------------------------------------------------------------

def is_image_url(url: str) -> bool:
    """True for anything that must never be downloaded. Spec §4.6.

    Checked by URL at one chokepoint rather than by remembering which JSON
    fields hold images. There are already five such field names across two
    endpoints (`mission_banner`, `vision_banner`, `about_banner`,
    `publication_banner`, `image`) and the next endpoint will invent another.
    """
    return any(rx.search(url) for rx in _IMAGE_RE)


def is_excluded_url(url: str) -> bool:
    """Apply EXCLUDE_HOSTS and EXCLUDE_PATTERNS. Spec §6.2."""
    if is_image_url(url):
        return True
    parts = urlsplit(canonical(url))
    if parts.netloc in config.EXCLUDE_HOSTS:
        return True
    target = parts.path + (f"?{parts.query}" if parts.query else "")
    return any(rx.search(target) for rx in _EXCLUDE_RE)


def in_allowed_host(url: str) -> bool:
    return urlsplit(canonical(url)).netloc in config.ALLOWED_HOSTS


def looks_like_file(url: str) -> bool:
    """True if the URL points at a document we would download. Spec §8."""
    path = urlsplit(canonical(url)).path.lower()
    return path.endswith(config.FILE_EXTENSIONS)
