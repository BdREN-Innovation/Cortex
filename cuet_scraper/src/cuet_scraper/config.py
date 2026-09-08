"""Every tunable value in one place, and the evidence for the non-obvious ones.

Numbers here that look arbitrary are not. Where a value was measured against the
live site, the measurement is in the comment beside it, because the next person
to touch this file needs to know whether they are changing a guess or a finding.

Spec: CUET_SCRAPER_SPEC.md §8.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------
# Hosts and endpoints
# --------------------------------------------------------------------------

SITE = "https://cuet.ac.bd"
API = "https://api.cuet.ac.bd/api/v1"

OUT = Path("cuet_data")
FILES = OUT / "_files"
META = OUT / "_meta"
CMS = OUT / "_cms"

# Spec §3.0. Seventeen endpoints, verified 2026-09-08. The frontend references
# all of these; `--stage audit` re-derives this list from the live JS bundles
# and tells you when it no longer matches.
#
# Order matters only for readability. `required` is what stops a silent
# half-empty run: spec §6.7 says a failed endpoint is a warning EXCEPT for the
# two that everything else is built from.


@dataclass(frozen=True)
class Endpoint:
    path: str
    required: bool = False
    note: str = ""


ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint("/home-parameters?academic_headers=1", required=True,
             note="structural index: faculties, departments, institutes, centers"),
    Endpoint("/administrative-departments", required=True,
             note="63 entities WITH body HTML. The highest-value endpoint."),
    Endpoint("/general-settings", note="8 CMS page bodies, spec §3.3"),
    Endpoint("/administrative-academic-faculties", note="faculty -> department tree"),
    Endpoint("/footer-data", note="directorates, offices, APA types"),
    Endpoint("/notices", note="976 notices, every one with a PDF. Spec §3.6"),
    Endpoint("/notice-types", note="the 8 types. Slugs, NOT the titles /notices returns"),
    Endpoint("/news", note="157 items with full HTML bodies"),
    Endpoint("/events", note="3 items with full HTML bodies"),
    Endpoint("/student-organizations", note="15 organisations"),
    Endpoint("/academic-curriculums", note="31 curricula, PDF links in short_description"),
    Endpoint("/app-admin-research-types", note="1,560 publications. 1.24 MB. Part 2"),
    Endpoint("/apa-sections", note="7 sections, 35 APA types. Part 2"),
    Endpoint("/download-types", note="2 download categories"),
    Endpoint("/home-counters", note="STALE COUNTS - capture, never derive. Spec §3.3"),
    # Found by --stage audit on its first real run, 2026-09-08 - not by hand.
    # Returns every field null (students, graduates, officers, teachers,
    # subjects, degrees). Kept in the inventory because it exists and the audit
    # should not keep reporting it; produces no documents.
    Endpoint("/counters", note="EMPTY: all fields null. Distinct from /home-counters"),
    Endpoint("/sliders?type=department", note="banners. Images: excluded at fetch time"),
)

# Per-entity detail route. Built by concatenation in the site's own bundle, which
# is why a quote-anchored grep misses it — spec §3.0.
ENTITY_DETAIL = "/administrative-departments/{slug}"

ALLOWED_HOSTS = {
    "cuet.ac.bd",
    "www.cuet.ac.bd",       # current routes only; .php excluded below, spec §6.2
    "app.cuet.ac.bd",       # file host only, never crawled as a site
    "api.cuet.ac.bd",       # the JSON API: data source, never a crawl target
    "admissioncuet.ac.bd",  # admission notices
}

EXCLUDE_HOSTS = {
    "cuet.thetork.com",     # vendor/staging domain leaked into CMS HTML, spec §4.11
    "v2.cuet.ac.bd",        # legacy site
    "course.cuet.ac.bd",    # login required, Part 2 §9
    "student.cuet.ac.bd",   # login required, Part 2 §9
}

# --------------------------------------------------------------------------
# Politeness. Spec §7.4. This is the section with real consequences.
# --------------------------------------------------------------------------

DELAY = 1.5              # seconds, PER HOST. Do not lower.
MAX_CONCURRENT = 3
PAGE_TIMEOUT_MS = 60_000
HTTP_TIMEOUT = 30        # seconds, per request
MAX_RETRIES = 3
MAX_FILE_BYTES = 100 * 1024 * 1024
RETRY_STATUSES = frozenset({429, 502, 503, 504})   # spec §7.4. NEVER 404 or 403.
BACKOFF_CAP = 60         # seconds

# VERIFIED 2026-09-08: https://cuet.ac.bd/robots.txt returns HTTP 404. There is
# no robots.txt. Per the standard that means allow-all, and urllib.robotparser
# already handles a 4xx correctly, so we keep using it rather than special-casing.
#
# Two traps, both spec §7.4:
#   1. The 404 BODY is 51 KB of styled HTML. Never hand a body to the parser
#      without checking status first.
#   2. No robots.txt is not permission. It removes the site's only chance to
#      state a limit, which makes DELAY and USER_AGENT the only restraint left.
OBEY_ROBOTS = True

# This string lands in CUET's logs on every request. It is the difference
# between an administrator emailing you and an administrator blocking you.
#
# A CUET address is the best case here: it identifies the crawler as belonging
# to one of the university's own students rather than an anonymous scraper, and
# there is no robots.txt on cuet.ac.bd for them to have stated limits in, so
# this is the site's only channel to reach whoever is running it.
#
# NOTE: this is a contact address, nothing more. It is NOT a credential and
# grants no access. Part 2 §9.1 still stands in full: nothing behind a login is
# in scope, and a student account must never be used to reach content that a
# member of the public could not.
CONTACT = "u2104038@student.cuet.ac.bd"
USER_AGENT = f"CUET-Research-Crawler/1.0 (+contact: {CONTACT})"

# --------------------------------------------------------------------------
# Failed-render detection. Spec §7.2. Stage 4 only.
# --------------------------------------------------------------------------

# Calibrate against real pages before trusting it. Measured 2026-09-08:
#   /departments        shell only        ~0 chars of markdown body
#   academic-calendars  partial render    title+breadcrumb+sidebar, no data grid
#   /  homepage         full render       well above any threshold
# A length check alone passes the partial case, which is why EMPTY_TABLE_RE
# exists as a second, independent condition.
EMPTY_RENDER_THRESHOLD = 4500

# The empty four-column data grid: a table whose cells are all blank. Its
# presence means the data component mounted and received nothing.
EMPTY_TABLE_RE = re.compile(
    r"<table[^>]*>(?:\s|<t[rdh][^>]*>|</t[rdh]>|<tbody[^>]*>|</tbody>)*</table>",
    re.I,
)

# Spec §4.5. A dynamic route returns HTTP 200 for a slug that does not exist,
# so "not found" must be detected in the CONTENT. Status codes are useless here.
NOT_FOUND_MARKERS = ("page not found", "404", "could not be found")

# --------------------------------------------------------------------------
# Exclusion. Spec §6.2 and §4.6.
# --------------------------------------------------------------------------

EXCLUDE_PATTERNS = [
    r"\.php($|\?)",                  # legacy PHP site on www.cuet.ac.bd
    r"^/_next/",                     # Next.js build assets
    r"^/assets/(images|js|css)/",    # site chrome, not content
    r"\.(jpg|jpeg|png|gif|webp|svg|ico|woff2?|ttf|eot|css|js|map)($|\?)",
    # NOTE: \.pdf is deliberately absent. A "\.pdf$" rule here silently switches
    # off the entire document pipeline with no error. Spec §6.2, and the same
    # trap is called out in engine/configs/README.md.
]

# Spec §4.6. Images are OUT OF SCOPE — a firm requirement, not a default.
# Four hosts, and the fourth is the dangerous one: it arrives inside JSON
# (*_banner fields on every entity) rather than inside HTML, so anything that
# walks a payload looking for URLs will find it.
IMAGE_URL_PATTERNS = [
    r"^https?://app\.cuet\.ac\.bd/+storage/(News|Student-Organization|Student-Halls"
    r"|Admins|General-Settings|Photo-Galleries)/",
    r"^https?://api\.cuet\.ac\.bd/+storage/Administrative-Departments/",  # NEW 2026-09-08
    r"^https?://[^/]*cuet[^/]*/assets/images/",
    r"^https?://cuet\.ac\.bd/og\.jpeg",
    r"\.(jpg|jpeg|png|gif|webp|svg|ico|bmp|tiff?)($|\?)",
]

# Documents only. Image extensions deliberately absent — spec §4.6.
FILE_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx",
                   ".ppt", ".pptx", ".zip", ".csv")

# --------------------------------------------------------------------------
# CMS keys. Spec §3.3.
# --------------------------------------------------------------------------

CMS_CONTENT_KEYS = {
    "about_us":                  "/about/cuet",
    "history":                   "/about/history",
    "mission_vision":            "/about/vision-and-mission",
    "campus_life":               "/about/campus-life",
    "undergraduate_prospective": "/academic-information/undergraduate-studies",
    "postgraduate_prospective":  "/academic-information/graduate-studies",
    "research_highlight":        "/research/research-highlights",
    "research_area":             "/research/research-area",
}

# research_highlight and research_area are DOUBLE-ESCAPED: their values contain
# literal &lt;p&gt; rather than real tags. Unescape once, flag it, log it.
# Spec §3.3 and §6.8.
DOUBLE_ESCAPE_MARKERS = ("&lt;p&gt;", "&lt;div", "&lt;h2&gt;", "&lt;ul&gt;", "&lt;br")

# --------------------------------------------------------------------------
# Notices. Spec §3.6.
# --------------------------------------------------------------------------

# Matched against `notice_type_title` — the DISPLAY string /notices returns, not
# the slug /notice-types carries. They are different strings and neither is
# derivable from the other, so the mapping stays explicit.
#
# 283 of 976 are in scope for Part 1. The other 693 belong to Part 2.
#
# The route is the REAL page each type is listed on. It matters because
# `canonical_url` is what a citation shows a reader: a fabricated URL such as
# /notices/detail/1024 does not exist on this site and would 404 for anyone who
# clicked it. Every document this scraper emits must cite a URL that resolves.
NOTICE_TYPES_IN_SCOPE = {
    #  title as returned          section      real listing route
    "Offices Orders/NOC":         ("top-bar",   "/notices/noc"),                       # 265
    "Scholarship & Financial Aids": ("admission", "/notices/scholarship-financial-aids"),  # 15
    "Academic Calender":          ("academic",  "/notices/academic-calender"),         # 3
}

# How many notices to list in one document before splitting. 265 NOC notices in
# a single document would be one enormous row-set; splitting keeps each document
# to a size that chunks sensibly for embedding.
NOTICES_PER_DOCUMENT = 60

# Capturing metadata for out-of-scope notices costs nothing (they arrive in the
# same response); downloading their PDFs does. Separate decisions, so separate
# switches. Part 2 §3.4.
CAPTURE_OUT_OF_SCOPE_NOTICE_METADATA = True
DOWNLOAD_OUT_OF_SCOPE_NOTICE_FILES = False

# --------------------------------------------------------------------------
# Sections. Spec §6.1. Sections are DATA, not code.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionRule:
    subdir: str
    exact: tuple[str, ...] = ()
    prefixes: tuple[str, ...] = ()
    hosts: tuple[str, ...] = ()


# Assignment order (spec §6.1): host rule wins, then exact, then longest prefix,
# then _unsorted with a WARNING.
#
# `exact` exists separately from `prefixes` for one reason: an earlier draft gave
# `home` the prefix "/", which is a prefix of every path on the site. It worked
# under longest-prefix matching while making `home` a silent catch-all that hid
# genuinely unassigned URLs.
SECTIONS: dict[str, SectionRule] = {
    "home": SectionRule(
        subdir="home",
        exact=("/",),
        prefixes=("/about/cuet", "/about/campus-life",
                  "/student/organizations", "/student/organization/"),
    ),
    "top-bar": SectionRule(
        subdir="top-bar",
        exact=("/notices/noc",),
    ),
    "academic": SectionRule(
        subdir="academic",
        prefixes=("/academic-information", "/faculty", "/departments",
                  "/department/", "/dept/", "/institutes", "/centers"),
    ),
    "admission": SectionRule(
        subdir="admission",
        prefixes=("/admission", "/fsc",
                  "/student/undergraduate-student",
                  "/student/postgraduate-student",
                  "/student/scholarship-financial-aids"),
        hosts=("admissioncuet.ac.bd",),
    ),
    "news-events": SectionRule(
        subdir="news-events",
        prefixes=("/news-events", "/news/", "/event-details/",
                  "/events", "/student/events"),
    ),
}

# Second-level folder, so a section is not one flat directory of ninety files.
# Explicit mapping, never inferred. Spec §6.5.
GROUPS: tuple[tuple[str, str], ...] = (
    ("/academic-information", "information"),
    ("/faculty", "faculty"),
    ("/departments", "departments"),
    ("/department/", "departments"),
    ("/dept/", "departments"),
    ("/institutes", "institutes"),
    ("/centers", "centers"),
    ("/news/", "news"),
    ("/event-details/", "event-details"),
    ("/news-events", "listing"),
    ("/events", "listing"),
    ("/student/events", "listing"),
    ("/student/organization/", "organizations"),
    ("/student/organizations", "organizations"),
    ("/notices/", "notices"),
)

# Multi-segment paths under these prefixes join their last TWO segments, so
# /department/cse/contact becomes "cse__contact" rather than a bare "contact"
# that collides across all 18 departments. Spec §6.5.
TWO_SEGMENT_PREFIXES = ("/department/", "/dept/")

MAX_NAME_LENGTH = 120

# --------------------------------------------------------------------------
# Static routes. Spec §8, revised §6.9 — this is now the RESIDUAL list: what
# stage 2 cannot produce from JSON. Each entry says why it survives.
# --------------------------------------------------------------------------

STATIC_ROUTES: tuple[tuple[str, str], ...] = (
    ("/", "homepage; fully server-rendered, but the only source for its own layout"),
    ("/academic-information", "landing page, no endpoint found"),
    ("/academic-information/international-students", "no endpoint found"),
    ("/admission", "no endpoint found"),
    ("/admission/msc/", "found only in CMS content, spec §4.11; no endpoint"),
    ("/fsc", "no endpoint found"),
    ("/student/undergraduate-student", "no endpoint found"),
    ("/student/postgraduate-student", "no endpoint found"),
    ("/news-events", "listing page; the 157 items are already captured from /news"),
    ("/events", "listing page; items already captured from /events"),
    ("/student/events", "listing page"),
    ("/notices/noc", "listing page; the 265 notices are already captured"),
    ("/departments", "listing page; the 18 entities are already captured"),
    ("/faculty", "listing page"),
    ("/institutes", "listing page"),
    ("/centers", "listing page"),
)

# /dept/<slug>/postgraduate is the one per-department page with no API coverage.
# /department/<slug>/contact IS covered: it is the `contacts` array on the
# entity detail endpoint. Spec §3.5.
DEPT_SUBPAGE_TEMPLATES = ("/dept/{slug}/postgraduate",)

# VERIFIED 2026-09-08: admissioncuet.ac.bd has NO DNS RECORD. Confirmed against
# a public resolver, with cuet.ac.bd resolving normally in the same check.
# admissionckruet.ac.bd fails identically. Spec §7.4.1.
#
# Kept configured rather than deleted, so that if the domain returns the
# configuration is already right. They fail as recorded errors, which is the
# honest outcome: the spec had this host in scope on the strength of a search
# index hit, and a search index only proves a host was live once.
EXTERNAL_ENTRY_POINTS = (
    "https://admissioncuet.ac.bd/",
    "https://admissioncuet.ac.bd/about-us",
)
UNRESOLVABLE_HOSTS = {"admissioncuet.ac.bd", "admissionckruet.ac.bd"}
