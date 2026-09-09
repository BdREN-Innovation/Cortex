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

# Resolved from this file, NOT from the working directory.
#
# It was a relative path until four people needed to run this. `Path("cuet_data")`
# means "wherever you happened to be standing", so the corpus landed in a
# different place for each person and none of those places was the one the repo
# tracks. Anchoring it here means `--stage content` writes into the committed
# corpus whether you ran it from the repo root, from `engine/`, or from an IDE
# with its own idea of the working directory. `--out` still overrides, which is
# how you point a trial run somewhere disposable.
#
# parents: [0] cuet [1] crawler [2] engine [3] src [4] engine/ [5] repo root
_ENGINE_DIR = Path(__file__).resolve().parents[4]
OUT = _ENGINE_DIR / "corpus" / "cuet"
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
# The alumni site. Spec §13 Q9 left it open; answered 2026-09-09.
#
# It is a second Next.js frontend on its own host, and it has its own JSON API
# on the vendor's domain rather than on cuet.ac.bd. Nothing forbids fetching
# it: alumni.cuet.ac.bd/robots.txt returns 404 exactly as the main site's does,
# and the homepage carries no robots meta tag of any kind.
#
# Two properties differ from the main site and both matter:
#
# * **It returns real 404 status codes.** /contact, /gallery, /notice and
#   /alumins are linked from its own navigation and every one is a genuine
#   HTTP 404, so the content-based detection the main site forces is not
#   needed here.
# * **It shares a backend with the main site.** api.cuet.thetork.com serves the
#   same /notices, /news and /download-types rows that api.cuet.ac.bd does -
#   102 of its 114 news rows were already in the corpus. Only the endpoints
#   below are alumni-specific, and capturing the shared ones would put one
#   notice under two citable URLs.
ALUMNI_SITE = "https://alumni.cuet.ac.bd"
ALUMNI_API = "https://api.cuet.thetork.com/api/v1"

# Alumni-only endpoints. Derived from the site's own JS chunks, not guessed:
# each route's page chunk names the endpoints it calls. Verified 2026-09-09,
# all returning HTTP 200.
#
# Deliberately EXCLUDED, having been checked and found to be the main site's
# data served through the vendor host: /notices (312 rows), /news (114, of
# which 102 already captured), /notice-types, /download-types, /downloads,
# /administrative-departments-mini-index. The alumni-scoped subsets of news and
# notices arrive inside /alumni-home-data instead, which is the right source
# because it is the one the alumni site itself renders.
ALUMNI_ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint("/alumni-settings", required=True,
             note="the alumni CMS pages: about_us, privacy and copyright policy"),
    Endpoint("/alumni-home-data", required=True,
             note="alumni-scoped news, notices, events, galleries and sliders"),
    Endpoint("/alumni-responsibilities", note="4 items with real description bodies"),
    Endpoint("/alumni-sites", note="4 linked alumni chapter sites"),
    Endpoint("/alumni-counters", note="4 stale counts. Capture, never derive"),
    Endpoint("/alumnis", note="the directory. See ALUMNI_PRIVATE_FIELDS"),
    Endpoint("/student-sessions", note="10 session labels; reference data"),
)

# Dropped from every alumni directory record before it is written.
#
# The two rows currently served are the vendor's own seed data - "Mr Alumni",
# employed "at Tork", with a placeholder LinkedIn URL - so nothing real is lost
# today. That is exactly why the rule belongs here now: when the directory
# fills with actual graduates, the field list is already in place and nobody
# has to remember. A retrieval corpus needs a person's degree, batch and
# department; it has no use for their home address.
ALUMNI_PRIVATE_FIELDS = ("email", "phone", "address")

# Empty, and that is the finding rather than an omission.
#
# The two candidates were /alumni-membership-form and /about/alumnis. Both were
# rendered on 2026-09-09 and both produce the same thing: about 1,470 characters
# of navigation followed by an empty table - `| | | | |` repeated - because the
# grid is filled client-side by a request the crawler never completes. For
# comparison the site's own 404 page renders 1,485 characters. Real page and
# missing page are the same size here, so no length threshold can separate
# them, and there is nothing in either body worth keeping.
#
# Everything these pages would have shown is already captured from the API:
# the directory from /alumnis, the prose from /alumni-settings. The browser
# adds nothing on this host, so it is not pointed at it.
ALUMNI_STATIC_ROUTES: tuple[tuple[str, str], ...] = ()

# Discovered on the alumni host, reviewed, deliberately not planned. The same
# idea as KNOWN_NOT_PLANNED, kept separate because these are on another host
# and the reasons are specific to it.
ALUMNI_NOT_PLANNED: dict[str, str] = {
    "/alumni-membership-form":
        "renders chrome plus an empty client-side grid, 1,474 chars against the "
        "site's own 404 at 1,485; nothing to capture",
    "/about/alumnis":
        "same empty grid; the directory itself is captured from /api/v1/alumnis",
    "/contact": "linked from the site's own nav and genuinely HTTP 404",
    "/gallery": "linked from the site's own nav and genuinely HTTP 404",
    "/notice": "linked from the site's own nav and genuinely HTTP 404",
    "/alumins": "typo in the site's own nav; HTTP 404",
}


# Per-entity detail route. Built by concatenation in the site's own bundle, which
# is why a quote-anchored grep misses it — spec §3.0.
ENTITY_DETAIL = "/administrative-departments/{slug}"

# The faculty. VERIFIED 2026-09-09.
#
# This was missed for a long time and the way it was missed is worth recording:
# every /department/<slug>/faculty-members/... page renders navigation and an
# empty grid, so rendering them said "no content here". The content was never
# in the page. It arrives from this endpoint, which no audited page referenced
# because `--stage audit` never sampled a faculty-members route.
#
# One request returns all 374 faculty across 23 departments. The per-person
# detail adds the profile intro, education, experience, research, publications,
# courses, supervisions and awards.
FACULTY_LIST = "/app-admins?admin_type=faculty_member"
FACULTY_DETAIL = "/app-admins/{slug}"

# Dropped from every faculty record before anything is written.
#
# The test that decides each field is simple: does the person's own public
# profile page show it? VERIFIED against dr-sumit-majumder, whose API record
# carries both a personal email and a home address and whose public page at
# /profile/faculty-member/<slug> contains neither.
#
# So work email, office phone and room number stay - those ARE on the page, and
# they are what makes a directory useful. The personal contact details go.
#
# The identity block (nid, date_of_birth, blood_group, parents' names,
# permanent_address, religion, file_no, prl_date) came back null for all 13
# people sampled, so today this drops nothing. It is listed anyway: the field
# names exist in the response, and a backend change that starts populating them
# must not silently push national ID numbers into a public corpus.
FACULTY_PRIVATE_FIELDS = (
    "nid", "date_of_birth", "blood_group", "father_name", "mother_name",
    "permanent_address", "religion", "file_no", "prl_date", "district_id",
)
# Same rule, applied inside the nested `profile` object.
FACULTY_PRIVATE_PROFILE_FIELDS = ("personal_email", "address")

ALLOWED_HOSTS = {
    "cuet.ac.bd",
    "www.cuet.ac.bd",       # current routes only; .php excluded below, spec §6.2
    "app.cuet.ac.bd",       # file host only, never crawled as a site
    "api.cuet.ac.bd",       # the JSON API: data source, never a crawl target
    "admissioncuet.ac.bd",  # admission notices
    "alumni.cuet.ac.bd",        # the alumni site, spec Q9 - see ALUMNI_API below
    "api.cuet.thetork.com",     # the alumni site's JSON API, never a crawl target
    "app.cuet.thetork.com",     # the alumni site's file host, never crawled
}

EXCLUDE_HOSTS = {
    # NOTE the exact host. Matching is exact (paths.is_excluded_url compares
    # netloc), so this excludes `cuet.thetork.com` ONLY. `api.` and `app.` on
    # the same domain are the alumni site's live backend and file store, are
    # allowed above, and must not be confused with this staging leak.
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

# RECALIBRATED 2026-09-08 against real headless renders. The original 4500 was
# derived from raw-fetch sizes and is dangerously low for browser output,
# because the rendered nav and footer alone are far larger than that.
#
#   chrome only, no content loaded            11,879 chars   <- MUST be rejected
#   /academic-information/academic-calendars  17,824 chars   <- must be accepted
#   /news-events                              19,561 chars
#   /departments (18 cards loaded)            19,893 chars
#
# 4500 would have passed the chrome-only render as a valid page. Three listing
# pages were in fact saved that way before this was caught — all three byte
# identical, which is what gave it away.
#
# 13000 sits above the chrome baseline and below the smallest real page.
# Residual risk: a genuinely thin page lands near the chrome size and is
# rejected. That is the safer direction to err — a rejected page is recorded in
# errors.json and can be retried, whereas a saved chrome-only page is silent
# corruption that looks like content.
EMPTY_RENDER_THRESHOLD = 13_000

# The empty four-column data grid: a table whose cells are all blank. Its
# presence means the data component mounted and received nothing.
EMPTY_TABLE_RE = re.compile(
    r"<table[^>]*>(?:\s|<t[rdh][^>]*>|</t[rdh]>|<tbody[^>]*>|</tbody>)*</table>",
    re.I,
)

# Spec §4.5. A dynamic route returns HTTP 200 for a slug that does not exist,
# so "not found" must be detected in the CONTENT. Status codes are useless here.
#
# TWO tiers, because one is not enough and the reason cost 18 bogus documents.
#
# The site renders its 404 INSIDE the normal layout: full header, full nav, full
# footer, with the not-found block in the middle. Checking only the opening of
# the document — which is all `NOT_FOUND_HEAD_MARKERS` can safely do — sees
# nothing but chrome and passes it. Eighteen `/dept/<slug>/postgraduate` pages
# were saved as real documents that way, byte-identical, every one of them a
# 404, each citing a URL that does not resolve.
#
# The fix is not to widen the loose markers: "404" appears in any page that
# discusses HTTP status codes, and a false positive here discards real content.
# Instead the exact sentence the site's own error component renders is matched
# anywhere in the document. It is specific enough that a page containing it is
# a 404, and it does not care where in the layout the block sits.
NOT_FOUND_BODY_MARKERS = (
    "the page you were looking for could not be found",
    "oops! page not found",
)

# Loose markers, checked only near the START of the text, where a real page
# would not open with them.
NOT_FOUND_HEAD_MARKERS = ("page not found", "404", "could not be found")
NOT_FOUND_HEAD_CHARS = 600


# A page that exists but whose content CUET has not published yet. Twenty of
# the 36 /department/<slug>/academic/<level> pages render this and nothing
# else: the route is real, the layout is real, the curriculum simply is not
# there. That is NOT a 404 and must not be treated as one - the page is a true
# statement about the site, and it will fill in later.
#
# It is not silently dropped either. Spec 4.4 puts thin-page filtering
# downstream, where it can be reconsidered without another crawl, so the
# document is written with content_state="placeholder" in its metadata and
# Team B decides what to do with it.
PLACEHOLDER_MARKERS = (
    "academic curriculam data is in progress",
    "we're unable to locate the data you're looking for",
)

# Stage 4 render wait. Spec §6.10 proposed an anchor-count condition and marked
# it UNVERIFIED. Verified 2026-09-08, and it was wrong twice over:
#
#   1. "js:document.querySelectorAll('a').length > 40" is an EXPRESSION.
#      crawl4ai evaluates the string as a FUNCTION, so it raises
#      "userFunction is not a function" and every page fails as a render error.
#      The arrow form "js:() => ..." parses correctly.
#
#   2. Fixing the syntax made it worse, not better. **The rendered nav and
#      footer alone contain 182 anchors**, so any anchor threshold is already
#      true at first paint. The condition returned immediately and crawl4ai
#      captured the DOM *before* the API data arrived — producing three
#      byte-identical chrome-only pages that the length check then accepted.
#
# An anchor count cannot work on this site at any threshold. What the page is
# actually waiting on is a client-side fetch to api.cuet.ac.bd, so the reliable
# signal is elapsed time. Measured on /departments:
#
#   2.0s -> 11,879 chars, no department names   (data had not arrived)
#   4.0s -> 19,893 chars, all 18 present
#
# 5s is 4s plus margin. Content-specific conditions such as
# "js:() => document.body.innerText.includes('Computer Science')" also work and
# are faster, but need one per page type, which is a maintenance burden for a
# stage this small.
WAIT_FOR = None
RENDER_DELAY_SECONDS = 8.0

# Stage 4 renders ONE page at a time, unlike the other stages.
#
# The delay above is wall-clock, not per-page work, so three tabs rendering
# concurrently on one machine starve each other and all three finish short. That
# is what produced three byte-identical chrome-only captures that the length
# check then accepted. Measured: sequential renders return ~19,500 chars, the
# same three pages at MAX_CONCURRENT=3 return 4,533.
#
# It costs nothing here. Stage 4 is a few dozen pages, and a wall-clock wait
# cannot be parallelised away without reintroducing exactly this bug.
CAPTURE_CONCURRENCY = 1

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
                  "/department/", "/dept/", "/institutes", "/centers",
                  # The heads of departments, faculties, institutes and centres.
                  # Without this rule all 30 land in _unsorted, which the
                  # definition of done forbids. Added 2026-09-09.
                  "/profile/faculty-member/"),
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
    # Routed by HOST, which section_for_url applies before any path rule. That
    # ordering is what matters here: the alumni site has its own /news and
    # /about, and a path rule would file them under the university's sections
    # and put two different pages in one folder.
    "alumni": SectionRule(
        subdir="alumni",
        hosts=("alumni.cuet.ac.bd",),
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
    ("/profile/faculty-member/", "profiles"),
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
    # Found 2026-09-09 by the Appendix B gap diff, after the first browser run.
    ("/academic-information/academic-calendars",
     "real page, no endpoint; the 3 calendar notices are separate from it"),
    # Linked from ONE faculty profile page, not from any department page. A
    # deeper route than /dept/<slug>/postgraduate, and a different prefix.
    # Only EEE is planned because only EEE was discovered: probing the same
    # shape across all 18 departments would be 36 requests on a guess, and a
    # dynamic route returns 200 either way (spec §4.5), so the requests would
    # not even settle the question. If these two render real content, widen it.
    # EEE's two rendered real content (18,084 and 15,825 characters), which
    # promoted this from "one discovered link" to a route worth trying across
    # every department. See DEPT_ACADEMIC_TEMPLATES.
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

# --------------------------------------------------------------------------
# Discovered, reviewed, and deliberately NOT planned. Appendix B.
# --------------------------------------------------------------------------
#
# The gap diff surfaces every URL the site links that nothing captured. Some of
# those are not pages worth having, and without somewhere to record that
# judgement the diff stays permanently red and people stop reading it.
#
# A URL belongs here only once somebody has looked at it and can say why. The
# reason is the point: "not planned" is a decision, and a decision nobody wrote
# down gets re-litigated every run.
KNOWN_NOT_PLANNED: dict[str, str] = {
    # The site's footer links all four institutes under /centers/. The API says
    # `type: institute` for every one, and spec §3.4 makes the API slug the
    # authority. They are already captured at /institutes/<slug>; capturing the
    # /centers/ form too would put one entity under two citable URLs.
    "/centers/IEER": "institute mislinked under /centers; captured at /institutes/IEER",
    "/centers/IET": "institute mislinked under /centers; captured at /institutes/IET",
    "/centers/IICT": "institute mislinked under /centers; captured at /institutes/IICT",
    "/centers/IRHES": "institute mislinked under /centers; captured at /institutes/IRHES",

    # Case variant. The API reports the slug as IICT and the site links iict.
    # Path case is preserved deliberately (spec §4.1, /department/cse vs
    # /department/CE are different pages), so these do not collapse on their
    # own and the API spelling wins.
    "/institutes/iict": "case variant of /institutes/IICT, the API spelling",

    # The site's own broken hrefs, in the same family as the mailto:undefined
    # and tel:undefined that spec §4.8 records.
    "/profile/faculty-member/null": "site emits a literal null where a slug should be",
    "/profile/faculty-member/Md. Zubair": "site emits a display name where a slug should be",

    # Same family, found a different way: this one is typed into the "Website"
    # field of qdhossain_94's own profile, so the page links to a name-shaped
    # alias of itself. VERIFIED 2026-09-09 - it returns HTTP 200, as every
    # Next.js [slug] route does, and renders an empty profile shell of 12,099
    # characters, where a populated profile clears the 13,000 threshold.
    "/profile/faculty-member/dr-quazi-delwar-hossain":
        "self-referential alias in the profile's own Website field; renders an "
        "empty shell, the person is captured at /profile/faculty-member/qdhossain_94",
}

# The same judgement, but for URLs that come in families too large to list one
# by one. A pattern is only allowed here with the evidence that produced it,
# because a regex silences every future URL that matches, including ones nobody
# has looked at.
KNOWN_NOT_PLANNED_PATTERNS: tuple[tuple[str, str], ...] = (
    # 17 routes x 18 departments = 306 URLs, every one of them a shell.
    #
    # VERIFIED 2026-09-09 by rendering all 17 for Civil Engineering. They differ
    # from each other ONLY in their own self-referential navigation links: the
    # bodies are byte-comparable chrome, around 13.6k characters of header,
    # sidebar and footer with nothing between them. `laboratories` looks bigger
    # at 18k, but the extra 4.4k is the expanded faculty-and-department dropdown,
    # not content.
    #
    # The content those pages are named for is real, and we already have it. It
    # arrives in the /administrative-departments/<slug> payload as `vision`,
    # `mission`, `laboratories_intro`, `contacts`, `photoGalleries`, `news` and
    # `events`, and lands in the single document at /department/<slug>. Checked
    # both ways for CE: every sampled span of `laboratories_intro` is in that
    # document and none of it is on the live /laboratories page.
    #
    # So crawling these would add 306 documents of navigation, each citing a URL
    # whose content is already citable elsewhere. That is worse than not having
    # them - a reader following the citation finds nothing.
    (r"^/department/[^/]+/(?!academic/)",
     "department subpage renders chrome only; its content is in the API payload "
     "already captured at /department/<slug> (verified on CE, all 17 routes)"),
)

# The per-department academic pages, one per level. VERIFIED 2026-09-09.
#
# Note the prefix: `/department/`, not `/dept/`. The spec named `/dept/` and
# that route does not exist at all, while this one renders real content. The
# two were found the same way and only one survived being rendered, which is
# the argument for rendering before believing.
#
# Discovered from a single faculty profile page linking EEE's pair. Widened to
# every department only after EEE's two came back with real bodies. Any
# department that does not have them returns the site's 404, which the
# content-based detector now catches (NOT_FOUND_BODY_MARKERS), so a department
# without these pages costs one rejected render rather than a bogus document.
DEPT_ACADEMIC_TEMPLATES = (
    "/department/{slug}/academic/postgraduate",
    "/department/{slug}/academic/undergraduate",
)

# EMPTY, and deliberately so. Spec §8 called `/dept/<slug>/postgraduate` "the
# one per-department page with no API coverage", and Appendix B listed it as a
# known gap. VERIFIED 2026-09-09 by rendering all eighteen: **the route does
# not exist.** Every one returns the site's 404 inside the normal layout, and
# all eighteen renders were byte-identical at 11,552 characters.
#
# They were saved as real documents on the first pass, because the not-found
# check only looked at the opening of the text and the 404 block sits below the
# whole navigation. See NOT_FOUND_BODY_MARKERS.
#
# `/department/<slug>/contact` needs no entry either: it IS the `contacts`
# array on the entity detail endpoint. Spec §3.5.
#
# If a real per-department subpage turns up, add its template here. Do not
# re-add postgraduate without rendering one first and reading the output.
DEPT_SUBPAGE_TEMPLATES: tuple[str, ...] = ()

# The head's profile page, one per entity. Found 2026-09-09 by the Appendix B
# gap diff — five of these were in `found_pages.txt` and in no plan, which is
# exactly the discovered-but-unplanned case that procedure exists to catch.
#
# The diff found five; there are thirty. The five are the entities whose body
# HTML happens to embed the link, but EVERY one of the 30 entities carries
# `department_head.slug`, so the route is derived from data rather than from
# whichever pages happened to mention it. Deriving it is also what spec §3.4
# requires: prefer the API's slug over one scraped out of markup.
#
# Two of the thirty are worth knowing about before you read the output:
#
#   * IEER's head is linked via `cuet.thetork.com`, the vendor domain (§4.11).
#     The slug is the same, so the cuet.ac.bd URL built here is the right one
#     and the vendor link is simply not followed.
#   * These are dynamic routes, so a wrong slug returns HTTP 200 and renders
#     not-found on the client (§4.5). Stage 4's content-based detection is what
#     catches that; status codes cannot.
# The route a faculty member's page lives at. No longer used to PLAN anything:
# every profile is built from /app-admins now, including the 30 heads this
# template used to reach. Kept because builders/academic still composes the
# citation URL from it, and one definition of the route beats two.
HEAD_PROFILE_TEMPLATE = "/profile/faculty-member/{slug}"

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

# Hosts cuet.ac.bd links to that do not exist in DNS.
#
# These stay in EXTERNAL_ENTRY_POINTS on purpose. Removing them would make the
# plan complete by pretending the links were never there, and the fact that the
# university's admission pages point at a dead host is true and worth recording.
# So they are planned, they fail, and the failure is explained here and written
# into the corpus by `merge` as `_meta/known_gaps.json`.
#
# VERIFIED 2026-09-09 against a public resolver, not inferred from a browser
# error: cuet.ac.bd resolves to 165.245.185.131 from the same query where
# admissioncuet.ac.bd returns no record at all. The name has no address, so
# there is nothing to retry, no delay that would help, and no user-agent that
# changes the answer.
UNRESOLVABLE_HOSTS: dict[str, str] = {
    "admissioncuet.ac.bd":
        "no DNS record (checked 2026-09-09). Linked from the Admission menu "
        "and planned as an external entry point; both /  and /about-us fail to "
        "resolve. cuet.ac.bd resolves from the same query, so this is the host, "
        "not the network.",
    "admissionckruet.ac.bd":
        "no DNS record. Appears only inside CMS HTML, never planned.",
}
