# CUET Website Scraper: Implementation Specification

**Target site:** `https://cuet.ac.bd`
**Stack:** Python 3.12, `requests` (primary), `crawl4ai` (residual pages only)
**Status:** specification, implementation in progress
**Site facts verified:** 2026-09-08
**Revised:** 2026-09-08, after answering sections 13 Q1, Q3 and Q5 against the
live site. The revision is substantial: see section 0.1.

---

## 0. How to read this document

This is a build specification. Sections 1 to 4 describe the site and why it
behaves the way it does. Sections 5 to 9 describe what to build. Section 10 is
the definition of done. Section 13 lists what is still unknown.

Anything marked **VERIFIED** was confirmed by an actual HTTP request against the
live site or its API on the date above. Anything marked **UNVERIFIED** has not
been checked and must be validated during implementation. Do not promote an
unverified assumption into code without testing it, and when you do test it,
update the marker so the next person inherits the answer.

Two things to read before writing any code: **section 2**, which explains why a
browser is needed at all, and **section 3.3**, which explains why a large part
of the content does not need one.

---

## 0.1 What the 2026-09-08 revision changed, and why

The three questions left open in section 13 were answered against the live site
on the same day this document was written. Two of the three answers invalidated
design decisions that ran through the whole specification, so the revision is
not cosmetic.

**The short version: the site's public JSON API returns the content of almost
every page. The browser is still needed, but for tens of pages rather than
hundreds.**

| Was | Is |
|---|---|
| 4 API endpoints (section 3) | **16.** Ten were undocumented; see section 3.0 for how they were found |
| Render ~525 URLs through a browser | Render a few dozen. The rest arrive as JSON |
| Enumerate news IDs 1–260 and event IDs 1–160, ~419 requests, mostly 404s | **Two requests.** `/news` returns all 157 with full bodies, `/events` all 3 |
| `/academic-information/academic-calendars` is the hard hybrid-render case | It is three rows of `/notices`, filtered by type |
| robots.txt unread | **There is no robots.txt.** It 404s. See section 7.4 |
| `RSC: 1` might skip the browser | It does not. Verified negative; see section 2 |

Nothing was deleted from the original analysis. Where a conclusion changed, the
original reasoning is kept and marked, because the reasoning is what makes the
next surprise recognisable. Section 4 in particular is almost entirely intact:
the site's traps — mixed-case slugs, ampersands, double slashes, double-escaped
CMS values, Bangla encoding — are all still real, and several got worse rather
than better.

**One trap did get worse and is worth reading now.** Section 4.5 said a 404 page
has content. It is stronger than that: on a dynamic route such as
`/directorate/<slug>`, an invalid slug returns **HTTP 200**, because the Next.js
route matches any slug and renders not-found on the client. Twelve URLs were
tested, including a slug known to be misspelled; every one returned 200. Any
design that distinguishes real pages from missing ones by status code is
therefore wrong on this site.

---

## 1. Purpose and scope

Capture the CUET public website in a form suitable for downstream text
processing: clean text per page, the original HTML kept alongside it, every
linked PDF downloaded, and enough metadata that any captured document can be
traced back to the exact URL it came from.

### In scope

| Section | Entry point |
|---|---|
| Homepage | `/` |
| Top bar | mail link, Alumni, NOC |
| Academic | Academic Information, Faculties, Departments, Institutes, Centers |
| Admission | `/admission` plus the separate admission portal |
| News & Events | `/news-events`, individual news and event pages |

### Explicitly out of scope

- **Images. Do not download any image.** See section 4.6. This is a firm
  requirement, not a default that can be relaxed for convenience.
- Research listing pages, notice listings other than NOC, APA, About (except
  the two pages the homepage links), Administration offices and sections,
  Directorates, Downloads, E-resources, Directories.
- The legacy sites: `v2.cuet.ac.bd` and the old PHP pages on `www.cuet.ac.bd`
  (`dep_cse.php`, `lab_cse.php` and similar). These are still live and serve
  different-vintage content. Section 6.2 specifies how they are excluded.
- The vendor or staging domain `cuet.thetork.com`. See section 4.11.
- Other subdomains: `alumni`, `course`, `library`, `student`, `app` as a
  browsable site. `app.cuet.ac.bd` is in scope **only** as a file host.
- Any authenticated content.

Adding an out-of-scope section later must be a configuration change and not a
code change. See section 6.1.

### Non-goals

No content cleaning during capture. See section 4.4 for why this is a rule
rather than a preference.

---

## 2. Why a browser is required

**The site is a Next.js App Router application and its data-bearing pages ship
no content in the served HTML.**

VERIFIED by direct fetch, using two different HTML extraction methods to rule
out a parsing artifact. `GET https://cuet.ac.bd/departments` returns HTTP 200
with a complete navigation bar, a complete footer, a correct `<title>`, and a
body containing this and nothing else:

```
|  |  |  |  |
| --- | --- | --- | --- |
|  |  |  |  |
|  |  |  |  |
```

An empty table skeleton. The eighteen department cards a browser displays are
injected by JavaScript after load. The same is true of `/department/cse`.

### Rendering is hybrid, not uniform

VERIFIED, and this is the nuance that matters. Three different behaviours exist
on the same site:

| Page | Behaviour |
|---|---|
| `/` homepage | **Fully rendered** in a plain fetch. News cards, event cards and the organisation carousel all present. |
| `/academic-information/academic-calendars` | **Partially rendered.** Page title, breadcrumb, sidebar navigation and page-specific meta tags are all present. The calendar list itself is the empty table skeleton. |
| `/departments`, `/department/cse` | **Shell only.** Correct title, no body content. |

So you cannot decide per page in advance whether a browser is needed. Two
consequences:

1. Render everything through the browser. It is correct in all three cases.
2. **A failed render is indistinguishable from a successful one by status code
   alone.** All three of the above return HTTP 200. Detecting the difference is
   a required feature, not a nicety. See section 7.2.

The partially-rendered case is the dangerous one, because a naive length check
passes it while the actual content is missing.

VERIFIED negative result: appending `?_rsc=o7jcb` to a URL does **not** return
the React Server Component payload; it returns the ordinary HTML shell.

VERIFIED, 2026-09-08, answering section 13 question 1: sending the header
`RSC: 1` **does** return a real React Flight payload — `/departments` drops from
60,404 bytes of HTML to 9,605 bytes of Flight — but that payload contains only
the component and chunk manifest. **No department data.** So the header does not
remove the need for a browser.

It does, however, turn out to be the most useful diagnostic on the site. See
section 3.0.

### But the browser is mostly avoidable anyway

Everything above remains true and is why a naive `requests` crawl of the HTML
fails. It is no longer the whole picture.

The JavaScript that populates these pages fetches from a public JSON API, and
that API returns the same content the browser would eventually render — in one
request, already structured, with no rendering to wait for and no failed render
to detect. Section 3 is now the primary capture path and this section describes
the fallback.

**Where the browser is still required:** pages whose content has no API
endpoint. As of 2026-09-08 that is a short list — see section 6.9 — and it is
short enough that the whole of section 7.2's failed-render machinery guards tens
of pages rather than hundreds. Keep that machinery. The failure mode it catches
is real, it is silent, and the pages it still guards are exactly the ones nobody
has a second source for.

---

## 3. The API

VERIFIED. The frontend calls a public JSON API. No authentication, no API key,
no cookie required.

```
Base: https://api.cuet.ac.bd/api/v1
```

**This is the primary capture path.** Sections 3.1 to 3.4 describe the four
endpoints found first and in most detail. Section 3.0 lists all sixteen and
explains how to find the seventeenth when someone adds it.

### 3.0 The full endpoint inventory, and how to rediscover it

The original four endpoints were found with Chrome DevTools. That works but is
manual, unrepeatable and cannot be run in CI. There is a better way, and it is
what found the other twelve.

**The method.** A Next.js App Router page will tell you which JavaScript chunks
it loads, and those chunks contain the API paths as string literals:

```bash
# 1. Ask the page for its Flight payload; it lists the page's chunks.
curl -s -H "RSC: 1" https://cuet.ac.bd/departments \
  | grep -o -E "static/chunks/[^\"]+\.js" | sort -u

# 2. Grep each chunk for endpoint strings.
curl -s https://cuet.ac.bd/_next/static/chunks/<chunk>.js \
  | grep -o -E "/api/v1/[a-zA-Z0-9_-]+" | sort -u
```

This is the one useful thing the `RSC: 1` header does, and it is why the
negative result in section 2 is still worth having. Stage 6 (`--stage audit`,
section 6.12) automates it so the inventory below stays honest.

Note that endpoints built by string concatenation need a wider grep. The
department detail route appears in the bundle as
`"/api/v1/administrative-departments/".concat(slug)`, so a pattern anchored on
a closing quote misses it. Grep with surrounding context when a page clearly
fetches something you cannot see.

**VERIFIED inventory, 2026-09-08.** Seventeen endpoints. All return HTTP 200
unauthenticated.

| Endpoint | Size | What it holds |
|---|---|---|
| `/home-parameters?academic_headers=1` | | Structural index — section 3.1 |
| `/administrative-academic-faculties` | | Faculty→department tree — section 3.2 |
| `/general-settings` | | **Eight page bodies** — section 3.3 |
| `/footer-data` | | Directorates, offices, APA — section 3.4 |
| `/administrative-departments` | 229 KB | **63 entities** with body HTML — section 3.5 |
| `/administrative-departments/{slug}` | ~30 KB | One entity, in full — section 3.5 |
| `/notices` | 293 KB | **976 notices, every one with a PDF** — section 3.6 |
| `/notice-types` | 1 KB | The 8 types |
| `/news` | 819 KB | **157 news items, full HTML bodies** |
| `/events` | 3 KB | 3 events, full HTML bodies |
| `/student-organizations` | 25 KB | 15 organisations, full descriptions |
| `/academic-curriculums` | 48 KB | 31 curricula, with PDF links |
| `/app-admin-research-types` | **1.24 MB** | **1,560 publications** — section 3.7 |
| `/apa-sections` | 10 KB | 7 sections, 35 APA types |
| `/download-types` | 184 B | 2 download categories |
| `/home-counters` | 215 B | Site counters. **Stale — see 3.3** |
| `/counters` | 120 B | **Empty**: every field null. Distinct from `home-counters` |
| `/sliders?type=…` | | Homepage and department banners. Images: out of scope |

Seventeen, not the sixteen this section first recorded. `/counters` was found by
`--stage audit` on its first real run rather than by hand — which is the whole
argument for section 6.12 existing, made a day after it was written. It produces
no documents, but an endpoint the config does not know about is exactly the
signal the audit exists to raise, and it cannot distinguish "empty and harmless"
from "an entire content type nobody noticed" without a human looking.

### 3.5 `/administrative-departments` — the single highest-value endpoint

VERIFIED. Returns **63 entities in one request**, each with body HTML in
`about`, `vision`, `mission`, `message_from_head` and `laboratories_intro`:

| `type` | Count | Covers |
|---|---|---|
| `academic` | 18 | The departments |
| `hall` | 9 | Halls of residence |
| `section` | 9 | Administrative sections |
| `faculty` | 5 | The faculties |
| `directorate` | 5 | Directorates |
| `institute` | 4 | The institutes |
| `center`, `cell` | 3, 3 | Centres and cells |
| `administrative_office`, `office` | 3, 2 | VC, Pro-VC, Registrar, Comptroller, Engineering |

`/administrative-departments/{slug}` returns one entity in full. For `cse` that
is a 1,647-character `about`, plus `department_head`, `contacts`, `news`,
`events`, `photoGalleries` and:

```json
"academicFaculty": {"title": "Electrical & Computer Eng.",
                    "slug": "electrical-&-computer-engineering"}
```

Two consequences worth stating plainly:

- **`contacts` is the `/department/<slug>/contact` page.** It does not need a
  separate fetch, browser or otherwise.
- **`academicFaculty.title` is the `section_path` breadcrumb** from section 6.6.
  The join against `/administrative-academic-faculties` is no longer needed,
  though that endpoint remains the better source for the faculty→department
  mapping as a whole.

**This endpoint returns entities that nothing on the site links to.** Compared
against the footer, it adds `ucrl`, `auditcell`, and the `Procurement`,
`academic-section`, `library` and `public-relation` sections — on top of the
`brtc` cell already noted in section 3.4. A link-following crawler reaches none
of them. This is the concrete case behind *prefer API slugs over scraped ones*.

### 3.6 `/notices` — the document pipeline in one request

VERIFIED. 976 notices. **No pagination.** Every record:

```json
{"id": 1024, "title": "Notice regarding …", "publish_date": "2026-09-08",
 "external_link": null, "pdf": "https://app.cuet.ac.bd/storage/Notices/….pdf",
 "administrative_department_title": "…", "notice_type_title": "Offices Orders/NOC"}
```

**All 976 carry a `pdf`; only 2 carry an `external_link`.** By type:

| Type | Count | In scope for this document |
|---|---|---|
| Student Notices | 309 | no — see Part 2 |
| **Offices Orders/NOC** | **265** | **yes** — section 1, top bar |
| General Notices | 191 | no |
| Appointments | 121 | no |
| Tender/E-Tender | 49 | no |
| All Notices | 23 | no |
| **Scholarship & Financial Aids** | **15** | **yes** — section 1, admission |
| **Academic Calender** | **3** | **yes** — this *is* `/academic-information/academic-calendars` |

So the page section 2 singles out as the dangerous partially-rendered case —
title and sidebar present, data grid empty — is three rows of this response.

The four fields above are exactly the metadata a folder of files named
`6a66d4ebbeb68.pdf` needs to be usable. They come free; there is no reason to
scrape a rendered listing for them.

### 3.7 `/app-admin-research-types` — 1,560 publications, no pagination

VERIFIED. 1.24 MB, four research types with their publications nested:

```
journal-paper      1,358 publications
conference-paper     202
partnership            0
mou                    0
```

Publication listings were the most likely place on the site to hide a long
client-side paginated list. They do not paginate; the whole corpus arrives at
once. Out of scope for this document, in scope for Part 2, and recorded here
because the finding is what removes Part 2's largest risk.

### 3.1 `/home-parameters?academic_headers=1`

The structural index. Returns, as flat lists with `id`, `title`, `slug` and
`short_name`:

- `academic_headers.faculties` (5)
- `academic_headers.academic_departments` (18)
- `academic_headers.institutes` (4)
- `academic_headers.centers` (3)
- `notice_types` (8)
- `header_research_types` (4)
- `header_notices` (2, each with a direct PDF URL)

**This is the primary source for building the URL list.** Every academic slug
comes from here in one call.

### 3.2 `/administrative-academic-faculties`

Faculties with their departments nested underneath, plus the dean of each
faculty, department addresses, phone numbers and emails. Use this to build the
faculty-to-department mapping for `section_path` breadcrumbs.

### 3.3 `/general-settings` — read this before designing the capture stage

**This endpoint returns the full HTML body content of several target pages.**
That is a significant finding: the content of these pages can be obtained
without a browser at all.

VERIFIED keys and the page each one populates:

| Key | Page it renders |
|---|---|
| `about_us` | `/about/cuet` |
| `history` | `/about/history` |
| `mission_vision` | `/about/vision-and-mission` |
| `campus_life` | `/about/campus-life` |
| `undergraduate_prospective` | `/academic-information/undergraduate-studies` |
| `postgraduate_prospective` | `/academic-information/graduate-studies` |
| `research_highlight` | `/research/research-highlights` |
| `research_area` | `/research/research-area` |
| `privacy_policy`, `copyright_policy` | footer text |

The content is substantial. `undergraduate_prospective` contains the full
admission rules, eligibility criteria and the departmental seat table.
`postgraduate_prospective` contains degree requirements, credit tables,
committee compositions and the grading scale.

It also returns site-wide values worth capturing: `title`, `phone`, `email`,
`address`, `facebook_link`, `linkedin_link`, `logo`, `favicon`.

**Required behaviour:** save this endpoint's HTML values as documents in their
own right, keyed to the page each belongs to, in addition to capturing those
pages through the browser. The two should agree. If they do not, the API value
is the more reliable one, because it is the source the page renders from.

Two data-quality problems in this endpoint, both VERIFIED:

- `research_highlight` and `research_area` are **double-escaped**. Their values
  contain literal `&lt;p&gt;` sequences rather than real tags, meaning the CMS
  stored already-escaped HTML. Unescaping once gives you HTML; rendering
  without unescaping shows the reader raw tag text. Handle explicitly and log
  when you detect it.
- `about_us` contains a summary table stating **15 departments, 3 institutes
  and 2 research centres**. The API's own structural lists say **18, 4 and 3**.
  The prose is stale. Never derive counts from page text; derive them from
  section 3.1.

VERIFIED addition, 2026-09-08: the stale count is not confined to prose.
`/home-counters` returns `"academic_department_counts": "15"` — as structured
JSON, from the same API whose `/home-parameters` lists 18. So the rule is not
"trust JSON over prose"; it is narrower and worth stating exactly:

> **Counts come from the length of a structural list, never from a field that
> reports a count.** Two endpoints of this API disagree with each other, and the
> one that is right is the one you can count yourself.

`/home-counters` is still worth capturing — its officer, faculty and staff
figures appear nowhere else — but nothing may be derived from it.

### 3.4 `/footer-data`

Returns the structures behind the footer, most of it out of scope but with two
findings that matter:

- **A slug typo in the site's own HTML.** The API gives the directorate slug as
  `research-extension`. The footer on every page links to
  `/directorate/research-extenstion`, with the letters transposed. One of those
  two URLs is wrong and will 404. Out of scope for version one, but exactly the
  class of bug that makes crawling from links unreliable. **Prefer API slugs
  over slugs scraped from HTML wherever both exist.**
- **Bangla titles.** Every directorate and office carries a `bn_title` field in
  Bangla, Unicode-escaped in the JSON. See section 4.12.

It also reveals routes not visible in the footer HTML: an APA type
`citizen_charter`, and a cell with slug `brtc`.

---

## 4. Site facts that will cause bugs if ignored

### 4.1 Slugs are case-mixed and convention-mixed

VERIFIED from the API. There is no consistent rule:

- Uppercase codes: `CE`, `ME`, `EEE`, `BME`, `ETE`, `MME`, `MIE`, `PME`,
  `URP`, `WRE`, `DEM`, `NE`
- Lowercase codes: `cse`, `hum`
- Full words, capitalised: `Architecture`, `Physics`, `Chemistry`, `Mathematics`
- Institutes, all uppercase: `IEER`, `IET`, `IICT`, `IRHES`
- Centers, mixed: `ceser`, `CIPR`, `physical-education-2`

Implications:

- **Never lowercase a URL path.** `/department/cse` and `/department/CE` are
  different pages. Lowercasing the host is correct; lowercasing the path is a
  bug.
- **Never construct a slug from a department code.** Read slugs from the API.
- **Filenames must not rely on case for uniqueness.** The API reports the
  institute slug as `IICT` while the site footer links to `/institutes/iict`.
  On a case-insensitive filesystem (macOS, Windows) those two would overwrite
  each other. Section 6.5 specifies the fix.

### 4.2 Slugs contain ampersands

VERIFIED. Three of the five faculty slugs contain a literal `&`:

```
architecture-&-planning
electrical-&-computer-engineering
science-&-technology
```

Percent-encode when building a URL (`%26`). An unencoded `&` in a path will
truncate or corrupt the request. Use `urllib.parse.quote(slug, safe="")`.

VERIFIED addition, 2026-09-08: this is **not** a faculty-only quirk. The
`Legal & Estate` section has the slug `l&e`. Apply the encoding rule to every
slug from every endpoint, not to a list of known-bad ones — the next one will
not be on the list.

### 4.3 The navigation is emitted twice, and carries legacy routes

VERIFIED. The page emits the full menu a second time for the mobile layout, so
a naive link harvest sees roughly double the hrefs. Deduplicating on the
canonical URL handles this.

The mobile copy additionally carries four routes appearing nowhere else:
`/research-highlights`, `/research-area`, `/research-type/publication`,
`/research-type/others`. These look like an older route family coexisting with
`/research/*`. Out of scope for version one, but note them if scope expands,
because if both families render they produce duplicate documents.

### 4.4 Capture and interpretation must stay separate

The capture stage saves raw HTML and does nothing clever with it. No cleaning,
no navigation stripping, no thin-page filtering, no duplicate detection.

This is a rule, not a style preference. Cleaning rules change repeatedly during
development. If cleaning happens during capture, every change costs another
full crawl of a third-party university server. If it happens afterwards against
saved bytes, the same change costs two seconds offline.

Specifically, do **not** do any of these during capture:

- Drop pages below a length threshold, other than the render check in section
  7.2, which rejects a *failed fetch* rather than a short page
- Collapse `/` and `/index.html`
- Strip nav, header or footer from the saved HTML
- Deduplicate by comparing raw HTML, since identical pages routinely differ by
  a timestamp or a token

Save everything. Filter later.

### 4.5 A 404 page has content — and dynamic routes do not 404 at all

The site returns a styled not-found page. It has text on it and will be
captured as a valid document unless explicitly detected. Treat a 404 as an
error to record, never as a page to save.

VERIFIED, 2026-09-08, and this is worse than originally written. **On a dynamic
route, a nonexistent slug returns HTTP 200.** The Next.js `[slug]` route matches
anything and renders not-found on the client, so the status code carries no
information about whether the page exists.

Twelve URLs were tested. All returned 200, including:

```
/directorate/research-extension      200      ← the API's slug
/directorate/research-extenstion     200      ← the footer's misspelling (section 3.4)
```

One of those two is a real page and the other is a transposition typo, and the
server reports them identically. By contrast `/robots.txt` returns a genuine
404, because no route matches it at all — so the site *can* 404, just never for
the case where it would be useful.

Three consequences:

1. **Never resolve a slug by status code.** Resolve it from the API. This is the
   concrete failure the rule in section 3.4 was written for.
2. **A 404 check must be content-based** — look for the not-found page's own
   markers in the rendered output, not at `response.status`.
3. An HTTP 200 with a 51 KB body is the site's way of saying "no". The
   `/robots.txt` response in section 7.4 is exactly this, and a robots parser
   handed that body would be parsing HTML as rules.

### 4.6 Images are out of scope

**Do not download images.** Nothing downstream consumes them, so fetching them
costs bandwidth, disk and request budget for no gain.

VERIFIED image locations, all of which must be excluded:

```
https://app.cuet.ac.bd/storage/News/<hash>.jpg
https://app.cuet.ac.bd/storage/Student-Organization/<hash>.png
https://app.cuet.ac.bd/storage/Student-Halls/<hash>.jpg
https://app.cuet.ac.bd/storage/Admins/<hash>.jpg
https://app.cuet.ac.bd/storage/General-Settings/<hash>.png
https://app.cuet.ac.bd/storage/Photo-Galleries/<hash>.png
https://app.cuet.ac.bd/assets/images/avatar/<name>.png
https://cuet.ac.bd/assets/images/**
https://cuet.ac.bd/og.jpeg
https://cuet.thetork.com/assets/images/**          see 4.11

VERIFIED 2026-09-08, a fourth host, on the API rather than the app:
https://api.cuet.ac.bd/storage/Administrative-Departments/<hash>.jpg
```

That last one is new and it is the dangerous one, because it arrives inside
JSON rather than inside HTML. Every entity from `/administrative-departments`
carries `mission_banner`, `vision_banner`, `publication_banner` and
`about_banner` fields holding absolute image URLs. Anything that walks the
payload looking for URLs to fetch will find them. The `/apa-sections` payload
carries `image` fields on the same host pattern.

**Exclude by URL, at one chokepoint, before any fetch** — not by remembering
which fields hold images. There are already five field names across two
endpoints and the next endpoint will invent another.

Note that CMS HTML from `/general-settings` also contains **relative** image
paths such as `/assets/images/undergraduate.jpg`. These must be excluded too,
after resolution against the site base.

Concretely:

- Image extensions never appear in `FILE_EXTENSIONS` (section 8)
- The file-URL regex harvest in section 6.9 must not match image extensions
- `_files/` must contain zero image files at the end of a run
- Do not add an `--images` flag. There is no use case, and leaving the door
  open invites someone to open it by accident

One thing that is **not** image scraping and should be kept: `alt` text and
`<figcaption>` are prose sitting in HTML you already have, and they belong in
the extracted markdown. Configure the markdown generator to keep alt text while
not emitting image links, then record what you set.

### 4.7 File hosts and filenames

VERIFIED patterns for documents worth downloading:

```
https://cuet.ac.bd/assets/pdf/<name>.pdf
https://app.cuet.ac.bd/storage/Downloads/<name>.pdf
https://app.cuet.ac.bd/storage/Downloads/<name>.zip
https://app.cuet.ac.bd//storage/Notices/<hash>.pdf        ← note the double slash
https://admissioncuet.ac.bd/file/notices/<name>-<unixtime>-<hash>.pdf
```

Concrete examples seen:

```
/assets/pdf/professor-list-26.07.2026.pdf
/storage/Downloads/Teacher List of CUET-2026 (26.07.2026).pdf
/storage/Downloads/Officers List of CUET-2026 (26.07.2026).pdf
/storage/Downloads/Staff List of CUET-2026 (26.07.2026).pdf
/storage/Downloads/CUET-logo-and-directions.zip
/storage/Notices/6a66d4ebbeb68.pdf
/storage/Notices/68d0d0992efd5.pdf
/file/notices/Department%20Allocation%20-%20KA%20(8.04.2026)-1775648725-69d63fd5beaa2.pdf
```

Three hazards:

- The double slash in `app.cuet.ac.bd//storage/` comes from the site's own
  string concatenation. The URL works. Normalise repeated slashes in the path
  when canonicalising, or the same file is stored twice.
- `Downloads` filenames contain spaces and parentheses.
- `admissioncuet.ac.bd` filenames arrive percent-encoded.

Never let a remote URL determine a local path. Sanitise. See section 6.5.

### 4.8 Broken and non-navigational hrefs

VERIFIED. The page contains hrefs that are not URLs and must be filtered before
anything tries to fetch them:

- `href="#"` on every dropdown toggle. Academic, Facilities, Research, Notices
  and About are toggles, not pages.
- `mailto:registrar@cuet.ac.bd` in the top bar, a real mailto
- `mailto:undefined` and `tel:undefined` in the footer, which are the site's own
  bugs and resolve to nothing

Filter by scheme: keep only `http` and `https`. Discard any URL whose path is
empty after the fragment is removed.

### 4.9 News and event IDs are non-contiguous — and must not be enumerated

VERIFIED news IDs seen from the homepage: 196, 200, 201, 202, 203, 205. Event
detail IDs: 136, 137, 138. The gaps are deleted or unpublished items.

The original plan was to enumerate 1–260 for news and 1–160 for events: 419
requests, roughly ten minutes at a 1.5 second delay, mostly 404s. It also
guessed the upper bound from six observed values.

**RESOLVED, 2026-09-08. Do not enumerate.** Section 13 question 3 is answered:

```
GET /api/v1/news      157 items, 819 KB, full HTML bodies, no pagination
GET /api/v1/events      3 items,   3 KB, full HTML bodies, no pagination
```

Two requests instead of 419, and they return the article bodies rather than
just confirming an ID exists.

The enumeration was worse than slow, it was wrong. Real news IDs run **5 to
206** with large gaps — the true low end is 5, not the 196 the homepage
suggested, and 55 of the 157 items sit below ID 100. A range anchored on six
homepage samples would have looked reasonable, produced hundreds of 404s, and
still missed items outside whatever bound was guessed. There would have been
no signal that anything was missing.

**The general rule, which is the point of this section:** when a listing is
reachable, enumerate the listing. Guessing an ID range is only ever a fallback,
and one that fails silently and asymmetrically — it cannot tell you what it
did not find.

### 4.10 The footer appears on every page

Every page carries the same footer with roughly fifty links to out-of-scope
sections. This is not a problem, but `found_pages.txt` will be full of
out-of-scope URLs. That is correct and useful: it is the record of what exists.
Do not fetch them, and do not treat their presence as a scope error.

### 4.11 Vendor domain leakage in CMS content

VERIFIED. HTML stored in the CMS and returned by `/general-settings` contains
absolute references to a different domain:

```
<img src="https://cuet.thetork.com/assets/images/campus-img-2.png">
<a href="https://cuet.thetork.com/faculty">Click</a>
```

This appears to be the vendor's development or staging domain, left in the
content by whoever authored it. Add `cuet.thetork.com` to the exclusion rules.
The images are excluded by section 4.6 in any case, but the `<a href>` would
otherwise be followed.

The same content also contains links to `https://admissionckruet.ac.bd/`, the
combined CUET, KUET and RUET admission portal, and a relative link to
`/admission/msc/`. Both are worth noting; `/admission/msc/` in particular is a
route not visible anywhere in the navigation.

### 4.12 The site is bilingual

VERIFIED. Bangla appears in two places:

- News headlines on the homepage, for example
  `চুয়েটে স্থাপত্য বিভাগে 'Spatial (IN) Justice' শীর্ষক সেমিনার অনুষ্ঠিত`
- A `bn_title` field on every directorate and office in `/footer-data`

So this is mixed Bangla and English, and it appears in News & Events, which is
one of the target sections.

Encoding rules, which are not optional:

- **Save HTML as bytes, not as decoded text**, so the original is always
  recoverable if decoding turns out to be wrong.
- **Always pass `encoding="utf-8"` explicitly** to every `read_text` and
  `write_text`. Python's default comes from the operating system, and on
  Windows it is often not UTF-8, so the same code produces correct files on one
  machine and mojibake on another.
- Servers can disagree with the document about the charset. The HTTP header and
  the `<meta charset>` are two separate declarations. Prefer the document's own
  declaration when they conflict.

A mis-decoded capture cannot be repaired downstream. The original bytes are
gone and the only fix is a re-crawl. **Verify after the first small run:** open
a saved news page and look for the Bangla. Correct output looks like `চুয়েট`.
Broken output looks like `à¦šà§Ÿà§‡à¦Ÿ`.

---

## 5. Architecture

Five stages, each independently runnable. The boundary between stages is a file
on disk, never a function call, so any stage can re-run without re-running the
one before it.

```
  API (JSON)                    stage 1: discover
       │                        16 endpoints + per-entity detail
       │                        no browser, seconds
       ├──────────────────────► stage 2: content
       │                        THE BULK OF THE CORPUS, from JSON
       ▼                        no browser
  _meta/urls.txt                stage 3: plan
       │                        only what the API does NOT cover
       ▼                        deterministic, reviewable by a human
  <section>/*.html + *.md       stage 4: capture
  _meta/found_files.txt         browser, tens of pages, resumable
       │
       ▼
  _files/*.pdf                  stage 5: fetch files
       │                        no browser, resumable, no images
       ▼
  _meta/endpoints.json          stage 6: audit
                                re-derive the endpoint inventory, diff vs config
```

**Stage 2 is where the work happens**, and this is the structural consequence of
section 3. In the original design it produced eight CMS documents while stage 4
did the heavy lifting; it now produces the great majority of the corpus and
stage 4 handles the remainder.

The ordering is deliberate: **every stage that needs no browser runs before the
one that does.** If the browser stage breaks, or Chromium will not install, or
the render condition turns out to be wrong, stages 1, 2 and 5 have already
produced a usable corpus. That was not true of the original design, where
nothing existed until the browser worked.

Stage 6 is new. See section 6.12.

CLI:

```bash
python -m cuet_scraper --stage discover
python -m cuet_scraper --stage content
python -m cuet_scraper --stage capture
python -m cuet_scraper --stage files
python -m cuet_scraper --stage audit
python -m cuet_scraper --stage all

python -m cuet_scraper --stage capture --limit 5              # smoke test
python -m cuet_scraper --stage capture --section academic     # one section
python -m cuet_scraper --stage capture --force                # ignore resume state
python -m cuet_scraper --stage all --verbose                  # DEBUG logging
```

`--section` filters the planned URL list to one section key from `SECTIONS`
(section 6.1). Repeatable. An unknown name is a fatal error listing the valid
names, never a silent empty run.

`--limit N` takes the first N URLs after all other filters, so the first run of
a new configuration is cheap.

### Why not one script per section

Do not create `scrape_academic.py`, `scrape_admission.py` and so on. That
duplicates the fetch loop, the retry logic, the robots handling and the
download code three times, which triples the surface for bugs and guarantees a
fix lands in one copy and not the others.

Sections are **data**, not code. See section 6.1.

### Module layout

Start as a single file. Split into the layout below only when it becomes
genuinely awkward to navigate, which is unlikely before roughly 500 lines. If
splitting, split by **stage**, never by section.

```
cuet_scraper/
├── __main__.py     argparse, stage dispatch                    ~60 lines
├── config.py       all tunable constants, SECTIONS map        ~110 lines
├── paths.py        canonicalisation, IDs, filesystem paths     ~90 lines
├── api.py          one polite HTTP client, shared by all      ~110 lines
├── discover.py     the 16 endpoints, URL list construction    ~150 lines
├── content.py      JSON payloads -> documents                 ~220 lines
├── capture.py      crawl4ai rendering, link harvesting        ~150 lines
├── files.py        file download                               ~90 lines
└── audit.py        endpoint rediscovery, section 6.12          ~90 lines
```

`content.py` is now the largest module and `capture.py` is no longer the centre
of the system. That inversion is the whole shape of the 2026-09-08 revision.

`api.py` is separated out because stages 1, 2, 5 and 6 all make HTTP requests
and every one of them must honour the same delay, the same per-host budget and
the same User-Agent. Four copies of that logic is four chances to get the
politeness rules wrong, and section 7.4 is the part of this document with real
consequences attached.

All tunable values live at the top of `config.py`.

### Repository placement

This document lives in the Cortex repository, which is a scaffold for three
teams building a general crawl → extract → index → ask pipeline. This scraper is
site-specific and is **not** that scaffold's crawler. It sits alongside:

```
Cortex/
├── CUET_SCRAPER_SPEC.md          this document
├── CUET_SCRAPER_SPEC_PART2.md    full-site coverage
├── engine/                       the scaffold. DO NOT EDIT engine/src/engine/crawler/
└── cuet_scraper/                 this project, its own uv project
    ├── pyproject.toml
    ├── uv.lock
    ├── src/cuet_scraper/
    ├── tests/test_paths.py       pure-function tests, section 10
    └── cuet_data/                output, GITIGNORED
```

`cuet_data/` must be in `.gitignore`. It will reach hundreds of megabytes.

**Why a separate uv project rather than a package inside `engine/`.** Two
reasons, both practical:

- A browser is a heavy dependency. Keeping `crawl4ai` and its bundled Chromium
  out of `engine/uv.lock` means the three teams' `uv sync` stays small, and
  they do not download a browser to work on code that has nothing to do with one.
- `engine/src/engine/crawler/` is Team A's assignment. Filling it in would be
  doing their work for them, and the engine crawler has no browser support in
  any case.

**Reuse the contracts.** Depend on `engine` as an editable path dependency and
import from `engine.contracts`. Note that `make_doc_id` there is already
byte-identical to `page_id` in section 6.4 — sha256 of the canonical URL,
truncated to 16 hex characters. **Import it; do not reimplement it.** Emitting
`CrawledPage` and `CleanDocument` rows means this capture feeds
`engine extract` / `index` / `ask` later with no adapter, which is the whole
point of section 12.

Dependencies:

```bash
cd cuet_scraper
uv sync                 # requests; crawl4ai for stage 4 only
uv run crawl4ai-setup   # installs the browser; needed only before stage 4
uv run crawl4ai-doctor  # verifies the install if anything looks wrong
```

Stages 1, 2, 5 and 6 need no browser. Do not let a failed `crawl4ai-setup` block
them — that ordering is deliberate, see the stage diagram above.

---

## 6. Component specifications

### 6.1 Section configuration

Sections are declared as data. Assignment rules, applied in order:

1. If the URL host is in a section's `hosts` list, that section wins.
2. Otherwise, exact-match entries (`exact`) are checked.
3. Otherwise, the section whose longest `prefixes` entry matches the path wins.
4. No match means `_unsorted`, logged at WARNING.

```python
@dataclass(frozen=True)
class SectionRule:
    subdir: str
    exact: tuple[str, ...] = ()
    prefixes: tuple[str, ...] = ()
    hosts: tuple[str, ...] = ()

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
```

Rule 2 exists for a specific reason. An earlier draft gave `home` the prefix
`/`, which is a prefix of every path on the site. Under longest-prefix matching
that happened to work, but it made `home` a silent catch-all and hid genuinely
unassigned URLs. Splitting `exact` from `prefixes` means an unassigned URL
surfaces as `_unsorted` with a warning, which is what you want.

Adding the Research section later must mean adding one entry here plus its URLs
in `discover.py`. It must not mean touching `capture.py` or `files.py`.

A URL landing in `_unsorted` is still captured, never dropped.

### 6.2 Exclusion rules

Applied to every URL before it is planned or followed.

```python
EXCLUDE_PATTERNS = [
    r"\.php($|\?)",                # legacy PHP site on www.cuet.ac.bd
    r"^/_next/",                   # Next.js build assets
    r"^/assets/(images|js|css)/",  # site chrome, not content
    r"\.(jpg|jpeg|png|gif|webp|svg|ico|woff2?|ttf|eot|css|js|map)($|\?)",
]

EXCLUDE_HOSTS = {
    "cuet.thetork.com",            # vendor/staging domain, see 4.11
    "v2.cuet.ac.bd",
}
```

Notes:

- **`.php`** is what keeps `www.cuet.ac.bd` in `ALLOWED_HOSTS` from pulling in
  the legacy site. `www` stays allowed because it also serves current routes
  such as `/dept/<slug>/postgraduate`, so a blanket host ban would lose real
  pages.
- **Image and font extensions** implement section 4.6.
- **Do not exclude `\.pdf`.** Worth stating because it is the classic mistake
  in a crawl config: a `\.pdf$` exclusion silently switches off the entire
  document pipeline with no error, and the PDFs simply never appear.

### 6.3 Canonicalisation

```python
def canonical(url: str) -> str:
    """Collapse the many URLs that mean one page into one string.

    Required behaviour:
        https://CUET.ac.bd/a/            -> https://cuet.ac.bd/a
        https://cuet.ac.bd/a#section     -> https://cuet.ac.bd/a
        https://cuet.ac.bd//a//b         -> https://cuet.ac.bd/a/b
        https://cuet.ac.bd:443/a         -> https://cuet.ac.bd/a
        https://library.cuet.ac.bd/      -> https://library.cuet.ac.bd
        https://cuet.ac.bd/department/CE    unchanged, case preserved

    Host lowercased, default port dropped.
    Path case PRESERVED (section 4.1).
    Repeated slashes in the path collapsed (section 4.7).
    Fragment always removed.
    Query string preserved as given; the API uses it meaningfully.
    """
```

This function determines document identity for the entire system. Get it wrong
and you get duplicates, or worse, two different pages collapsing into one.

The trailing-slash case is not hypothetical: the page links
`https://library.cuet.ac.bd/` and `https://library.cuet.ac.bd` in different
blocks.

### 6.4 Stable IDs

```python
def page_id(url: str) -> str:
    return hashlib.sha256(canonical(url).encode("utf-8")).hexdigest()[:16]
```

**Use `hashlib`, not Python's built-in `hash()`.** Python randomises string
hashing per process by default, so `hash()` returns different values on every
run. Using it for filenames means every re-run creates duplicates instead of
overwriting, and resumability silently breaks. This is called out because an
earlier draft implementation made exactly this mistake.

IDs must be stable across runs and machines. Derive them from the canonical URL
and nothing else. Never from a counter, a timestamp, or iteration order.

### 6.5 Filesystem paths

```python
def page_path(url: str, extension: str) -> Path:
    """Layout: <OUT>/<section subdir>/<group>/<slug>__<id8>.<extension>"""
```

`<group>` is a second-level folder so a section does not become one flat
directory of ninety files. The mapping is explicit, not inferred:

| URL path starts with | group |
|---|---|
| `/academic-information` | `information` |
| `/faculty` | `faculty` |
| `/departments`, `/department/`, `/dept/` | `departments` |
| `/institutes` | `institutes` |
| `/centers` | `centers` |
| `/news/` | `news` |
| `/event-details/` | `event-details` |
| `/news-events`, `/events`, `/student/events` | `listing` |
| `/student/organization/`, `/student/organizations` | `organizations` |
| host is `admissioncuet.ac.bd` | `admissioncuet` |
| anything else | `""` (directly in the section folder) |

`<slug>` is the last non-empty path segment, sanitised. For
`/department/cse/contact` the slug is `contact`, which would collide across
departments, so for multi-segment paths under `/department/` and `/dept/` join
the last two segments with `__`: `cse__contact`, `cse__postgraduate`. The `id8`
suffix makes this safe regardless, but readable filenames matter when a human is
checking output.

`<id8>` is the first 8 characters of `page_id(url)`. It is what prevents
`/institutes/IICT` and `/institutes/iict` from colliding on a case-insensitive
filesystem (section 4.1).

Sanitisation rules for any name derived from a remote URL:

- Percent-decode first, then sanitise
- Replace anything outside `[A-Za-z0-9._-]` with `_`
- Strip leading and trailing dots, underscores and hyphens
- `..` must not survive
- Cap total length at 120 characters, preserving the extension
- Empty result falls back to `index`

Target layout:

```
cuet_data/
├── _meta/
│   ├── api_dump.json          raw API responses, all four endpoints, verbatim
│   ├── urls.txt               the crawl plan, one URL per line
│   ├── manifest.json          one record per attempted page
│   ├── found_pages.txt        page links the crawler discovered
│   ├── found_files.txt        document links the crawler discovered
│   ├── errors.json            every failure with a reason
│   └── run.json               run summary, section 7.5
│
├── _cms/                      stage 2 output, from /general-settings
│   ├── about_us.html / .md / .json
│   ├── history.html / .md / .json
│   ├── undergraduate_prospective.html / .md / .json
│   └── ...
│
├── home/
├── top-bar/
├── academic/
│   ├── information/
│   ├── faculty/
│   ├── departments/
│   ├── institutes/
│   └── centers/
├── admission/
│   └── admissioncuet/
├── news-events/
│   ├── listing/
│   ├── news/
│   └── event-details/
├── _unsorted/
│
└── _files/                    ALL documents, flat, deduplicated, NO IMAGES
    ├── <id8>__<name>.pdf
    └── index.json
```

Each captured page writes three files sharing a stem: `.html` (raw), `.md`
(rendered text), `.json` (metadata, section 6.6).

**Files are stored flat in `_files/`, not inside section folders.** The same PDF
is linked from many pages; the staff list appears in the footer of every page.
Storing per section would produce several copies with no canonical one. The
page-to-file relationship is recorded in each page's `.json`.

### 6.6 Per-page metadata

```json
{
  "url": "https://cuet.ac.bd/department/cse",
  "canonical_url": "https://cuet.ac.bd/department/cse",
  "page_id": "a3f10b2c9d4e5f61",
  "section": "academic",
  "group": "departments",
  "section_path": ["Academic", "Departments", "Computer Science & Engineering"],
  "title": "Computer Science & Engineering",
  "source": "browser",
  "status": 200,
  "fetched_at": "2026-09-08T14:30:00Z",
  "html_path": "academic/departments/cse__a3f10b2c.html",
  "markdown_path": "academic/departments/cse__a3f10b2c.md",
  "text_chars": 4821,
  "render_ok": true,
  "attempts": 1,
  "links_found": 63,
  "files": [
    {"url": "https://app.cuet.ac.bd/storage/Downloads/x.pdf",
     "local": "_files/9f8e7d6c__x.pdf"}
  ]
}
```

`source` is `"browser"` or `"api"`, so a consumer can tell how a document was
obtained. Stage 2 writes `"api"`.

`section_path` is the human-readable breadcrumb and must be populated at
capture time. Build it from the section name, the group, and the title the API
gave for that slug. For departments, use `/administrative-academic-faculties`
to insert the faculty as a level:
`["Academic", "Departments", "Electrical & Computer Eng.", "Computer Science & Engineering"]`.

The folder tree is for humans browsing with their eyes; `section_path` is what
downstream code reads. Folders get reorganised, JSON fields do not. If this data
later feeds a retrieval system, the breadcrumb is what a citation shows a
reader, and reconstructing it from file paths afterwards is lossy.

### 6.7 Stage 1, discover

1. Fetch all four API endpoints. Save the raw responses verbatim to
   `_meta/api_dump.json` **before parsing anything**. If parsing logic turns out
   to be wrong you want the original bytes, not a second round of requests.
2. A failed endpoint is a warning, not fatal, except `/home-parameters`, which
   is required. If that fails, stop with a clear message.

### 6.8 Stage 2, content

Originally justified by section 3.3 alone. After the 2026-09-08 revision this
stage produces most of the corpus; see section 3.0.

**Every source below writes the same three-file shape** (`.html` bytes, `.md`,
`.json` with `source: "api"`) so that a consumer cannot tell a JSON-derived
document from a browser-captured one except by reading the `source` field. That
uniformity is the point — downstream code should not branch on provenance.

| Source | Documents | Section |
|---|---|---|
| `/general-settings` CMS keys | 8 | 3.3 |
| `/administrative-departments/{slug}` | 30 academic (18 depts, 4 institutes, 3 centers, 5 faculties) | 3.5 |
| `/news` | 157 | 3.0 |
| `/events` | 3 | 3.0 |
| `/student-organizations` | 15 | 3.0 |
| `/academic-curriculums` | 31 | 3.0 |
| `/notices`, filtered to `NOTICE_TYPES_IN_SCOPE` | 283 | 3.6 |

Roughly 530 documents, from about 45 HTTP requests, with no browser.

For a department entity, the body is assembled from its HTML fields in a fixed
order — `about`, `vision`, `mission`, `message_from_head`, `laboratories_intro`
— each under a heading naming its field. Do not concatenate them bare: the field
name is the only thing that tells a reader whether they are looking at the
department's self-description or its head's welcome message, and that
distinction survives into chunking and citation.

A notice becomes a document even though its substance is the linked PDF. The
record carries title, date, type and issuing department; the document body is
that metadata, and the PDF is attached as a file (section 6.11). This is what
makes 265 files named `<hash>.pdf` findable.

For each CMS key in `/general-settings` listed in section 3.3, write a document
into `_cms/` with the same three-file shape as a captured page:

- `.html` is the value verbatim, as bytes
- `.md` is the value converted to text
- `.json` carries `source: "api"`, the page the key corresponds to, and the
  key name

Two required behaviours:

- **Detect double-escaping.** If the value contains `&lt;p&gt;` or similar,
  unescape once before converting, and set a `double_escaped: true` flag in the
  JSON. Log at WARNING. This currently affects `research_highlight` and
  `research_area`.
- **Harvest links from CMS HTML too.** It contains real URLs, including
  `admissionckruet.ac.bd`, `/admission/msc/` and the vendor domain from section
  4.11. Run the same filtering pipeline over them.

### 6.9 Stage 3, plan

**This stage shrank.** It plans only what stage 2 could not already produce from
JSON — everything the API covers is already a document by the time this runs.

Build `_meta/urls.txt` from three sources:

1. The static route list in `config.py` (section 8), minus anything stage 2
   already covered
2. API-derived routes whose *content* is not in the API — currently
   `/dept/<slug>/postgraduate`
3. Links discovered in CMS HTML during stage 2 that fall in scope

VERIFIED as of 2026-09-08, the residual list is roughly thirty URLs:

```
/admission, /admission/msc/, /fsc
/student/undergraduate-student, /student/postgraduate-student
/academic-information, /academic-information/international-students
/dept/<slug>/postgraduate                         18 of these
/news-events, /events, /student/events            listing pages; items already captured
https://admissioncuet.ac.bd/, /about-us           see section 13 Q9
```

Everything else in section 9's tree is API-covered. **Write down why each
survivor is on the list**, next to the entry — "no endpoint found" and "listing
page, items already captured" are different reasons with different fixes, and a
bare URL list six months from now cannot tell them apart.

The old third source, ID enumeration, is deleted. See section 4.9.

Apply `EXCLUDE_PATTERNS` and `EXCLUDE_HOSTS`, deduplicate by canonical URL,
preserve insertion order, write one URL per line.

This file is a deliberate human checkpoint. It must be readable and reviewable
before anything expensive runs. A wrong URL caught here costs seconds; the same
error caught after a full crawl costs an hour and several hundred requests
against someone else's server.

### 6.10 Stage 4, capture

Uses `crawl4ai`. Starting configuration, to be tuned:

```python
browser = BrowserConfig(
    headless=True,
    user_agent=USER_AGENT,
    viewport_width=1920,
    viewport_height=1080,
)

md_generator = DefaultMarkdownGenerator(
    options={"ignore_images": True, "image_alt_text": True},   # section 4.6
)

run = CrawlerRunConfig(
    page_timeout=PAGE_TIMEOUT_MS,
    cache_mode=CacheMode.ENABLED,
    wait_for="js:document.querySelectorAll('a').length > 40",
    markdown_generator=md_generator,
    remove_overlay_elements=True,
    exclude_external_links=False,
)
```

`cache_mode=ENABLED` is deliberate during development so repeated tuning runs do
not re-hit the server. Consider `BYPASS` for a final production run, and record
which you used in `run.json`.

The `wait_for` condition is **UNVERIFIED**. Validate it against one department
page before the full run. Alternatives if unreliable: `wait_for="css:table"`, or
a longer `page_timeout` with no wait condition.

Per page:

1. Skip if already captured and `--force` was not passed (section 7.1)
2. Render, check for a 404 (section 4.5) and a failed render (section 7.2)
3. Write `.html` as bytes, then `.md`, then `.json`, atomically (sections 4.12
   and 7.3)
4. Harvest links from `result.links`, plus a regex over the raw HTML to catch
   document URLs not inside an `<a>` tag
5. Filter by scheme, keeping only `http` and `https` (section 4.8)
6. Resolve relative links against the page URL, canonicalise, apply
   `EXCLUDE_PATTERNS` and `EXCLUDE_HOSTS`, split into pages and documents, keep
   only in-scope hosts
7. Append to the manifest

Concurrency is bounded by `MAX_CONCURRENT`. Sleep `DELAY * batch_size` between
batches so the effective per-host rate stays polite regardless of concurrency.

### 6.11 Stage 5, files

No browser. Plain `requests` with `stream=True`.

- Read `_meta/found_files.txt`
- Re-apply the image exclusion as a second line of defence. An image reaching
  this stage is a bug in stage 4, so log at WARNING rather than skipping quietly.
- Skip files already on disk unless `--force`
- Cap at `MAX_FILE_BYTES`, aborting mid-stream if exceeded, so an unexpectedly
  large file cannot exhaust memory
- Write to a `.part` file and rename on success, so an interrupted download is
  never mistaken for a complete one
- Record every download in `_files/index.json` with URL, local name, byte size
  and content type

### 6.12 Stage 6, audit

New stage. No browser, no writes outside `_meta/`.

Automates the discovery method in section 3.0: for each page in a configured
sample, request the Flight payload with `RSC: 1`, collect the JavaScript chunk
names, fetch each chunk once, and grep out `/api/v1/...` strings. Write the
union to `_meta/endpoints.json` and **diff it against the endpoint list in
`config.py`**, reporting three sets:

- endpoints the site uses that the config does not know about
- endpoints the config expects that no page references any more
- endpoints that returned a non-200 on their last discover run

**Why this is a stage and not a one-off script.** Every finding in the
2026-09-08 revision came from running it by hand. Twelve endpoints existed for
an unknown length of time while this document confidently said there were four,
and nothing in the pipeline would ever have noticed — the crawl would have
succeeded, produced plausible output, and silently missed most of the site.

A capture pipeline can only detect the failures it was told to look for. This
stage is the one that looks for the failure of *not knowing what exists*, which
is otherwise invisible by construction. Run it before any full re-crawl, and
whenever the output looks smaller than last time.

Cache the chunk fetches. A chunk name contains a content hash, so a cached
response for `5250-30ac4c21835b7adb.js` can never be stale — if the file
changed, its name changed. Without caching this stage re-downloads roughly forty
identical files on every run, which is exactly the impoliteness section 7.4
forbids.

---

## 7. Required behaviours

Each addresses a failure mode that will occur on a run of this size.

### 7.1 Resumability

A full run is several hundred pages at 1.5 seconds each, so fifteen minutes
minimum and longer with documents. A crash at page 300 must not cost 300 pages
of work.

```python
def already_captured(url: str) -> bool:
    return page_path(url, "json").exists()
```

Filter the URL list before starting. `--force` bypasses it.

The `.json` file is the completion marker because it is written last. If HTML
exists but JSON does not, the page was interrupted and will be retried, which is
correct.

### 7.2 Failed-render detection

The defining failure mode of this site. A page whose JavaScript did not run
returns HTTP 200 with a valid HTML shell and no content.

**Scope note, 2026-09-08.** This now guards stage 4 only — tens of pages rather
than hundreds, since the rest arrive as JSON. **Keep all of it.** The pages it
still guards are precisely the ones with no API second source, which makes a
silent empty capture there unrecoverable rather than merely annoying. A cheaper
check for a smaller surface would be a false economy.

Note also that the empty-table case is now *harder* to hit in the wild, which
means it is harder to test against. Calibrate `EMPTY_RENDER_THRESHOLD` while a
known-empty page still exists, and keep a saved copy of one in the test fixtures
rather than relying on the live site to keep serving you a broken render.

A plain length threshold is **not sufficient**, because of the hybrid rendering
described in section 2. `/academic-information/academic-calendars` returns its
title, breadcrumb and sidebar navigation while the actual calendar list is
missing, so it will comfortably exceed any threshold set for the fully-empty
case. Use two checks together:

```python
def render_failed(markdown: str, html: str) -> bool:
    if len(markdown.strip()) < EMPTY_RENDER_THRESHOLD:
        return True
    # The empty data grid: a table whose cells are all blank.
    if EMPTY_TABLE_RE.search(html):
        return True
    return False
```

`EMPTY_TABLE_RE` matches the empty four-column skeleton documented in section 2.
Its presence means the data component mounted but received nothing, which is a
failure even on an otherwise well-populated page.

Calibrate `EMPTY_RENDER_THRESHOLD` by measuring three pages known to be full and
three known to be empty. Put the measured numbers in a comment next to the
constant so the next person does not treat it as a magic number.

A failed render is retried up to `MAX_RETRIES`, then recorded in `errors.json`.
It is **never** saved as a valid page. Note the distinction from section 4.4:
this rejects a failed fetch, not a legitimately short page.

### 7.3 Atomic writes

```python
tmp = dest.with_suffix(dest.suffix + ".part")
tmp.write_bytes(payload)          # bytes for HTML, see 4.12
tmp.replace(dest)
```

Without this, an interrupt during a write leaves a truncated file that
`already_captured()` counts as complete, and the corruption stays invisible
until something downstream fails.

Write order per page: `.html`, then `.md`, then `.json`. The marker goes last.

### 7.4 Politeness

Non-negotiable. `cuet.ac.bd` is a third-party university site. Being blocked is
not quickly recoverable and would stop the project.

- **robots.txt**, parsed with `urllib.robotparser` from the standard library.
  Fetch once per host and cache; fetching before every request is itself
  abusive. Do not write a parser, since the wildcard cases are subtler than they
  look. A missing or unreachable robots.txt means allow, per the standard, but
  log it.

  **VERIFIED 2026-09-08, answering section 13 question 5:
  `https://cuet.ac.bd/robots.txt` returns HTTP 404. There is no robots.txt.**

  Three things follow, and the third is the one that matters:

  1. Per the standard, 404 means allow-all. `urllib.robotparser` gets this right
     on its own: `RobotFileParser.read()` treats 4xx other than 401/403 as
     allow-all. Keep using it rather than special-casing the status.
  2. **The 404 body is 51 KB of styled HTML** — the site's app shell, as
     described in section 4.5. Never feed a response body to the robots parser
     without checking the status first; HTML parsed as robots rules produces
     confident nonsense rather than an error.
  3. **No robots.txt makes everything else here more important, not less.** A
     robots.txt is where a site states its limits. Without one there is no
     stated limit, which is not permission — it means the only thing standing
     between this crawler and an annoyed administrator is the delay, the
     concurrency cap and the User-Agent below. Do not read "allow-all" as
     "go faster".

  **VERIFIED 2026-09-08, and better than the above suggests.** The other hosts
  were checked too, and the two we actually hammer *do* publish a robots.txt:

  | Host | robots.txt | Meaning |
  |---|---|---|
  | `cuet.ac.bd` | **404** | absent; allow-all by default |
  | `app.cuet.ac.bd` | **200**, `User-agent: *` / `Disallow:` | **explicit allow-all** |
  | `api.cuet.ac.bd` | **200**, `User-agent: *` / `Disallow:` | **explicit allow-all** |
  | `www.cuet.ac.bd` | 301 redirect | follow it; resolves to the apex |
  | `admissioncuet.ac.bd` | does not resolve | see 7.4.1 |

  An **empty `Disallow:` is not the same as a missing file.** A missing file is
  an absence of any statement; `Disallow:` with nothing after it is the site
  explicitly granting access to everything. So the two hosts this crawler leans
  on hardest — the API it reads and the file host it downloads 283 PDFs from —
  have both said yes in writing. That is a materially better position than the
  cuet.ac.bd 404 alone implied, and it is worth having checked.

  It does not change the delay. Permission to fetch is not permission to fetch
  quickly.

### 7.4.1 `admissioncuet.ac.bd` does not resolve

**VERIFIED 2026-09-08. The admission portal's domain has no DNS record.**
Confirmed against a public resolver (8.8.8.8), not just a local one, with
`cuet.ac.bd` resolving normally in the same check. `admissionckruet.ac.bd`, the
combined CUET/KUET/RUET portal, fails identically.

This host appears throughout this document as in scope: section 1, section 9's
tree, `ALLOWED_HOSTS`, `EXTERNAL_ENTRY_POINTS`, and its own `admissioncuet`
group in section 6.5. None of that was ever confirmed by a fetch — Appendix B
says so plainly: *"Only `/` and `/about-us` known, both from a search index."*

**A search-index hit is not evidence a host is live.** It is evidence the host
was live when the index was built. Everything in this document marked as coming
from a search index rather than a direct fetch carries the same caveat, which is
exactly why the distinction was worth recording in Appendix B.

Handling: keep the routes configured and let them fail as recorded errors rather
than deleting them. If the domain returns, the configuration is already right.
The admission PDFs it was expected to host are simply not obtainable, and no
amount of crawler engineering changes that.
- **`DELAY >= 1.5` seconds, per host.** Do not lower it. Rate limiting is per
  host, so crawling `app.cuet.ac.bd` must not consume the `cuet.ac.bd` budget.
- **A real User-Agent** naming the project and a working contact address. That
  string lands in CUET's logs on every request, and it is the difference between
  an administrator emailing you and an administrator blocking you.
- **Retry `429, 502, 503, 504`** with exponential backoff, honouring
  `Retry-After` when present, capped at 60 seconds.
- **Never retry `404` or `403`.**
- **Cap response sizes.** Stream binaries and stop before exhausting memory.

If the site starts refusing requests, stop and escalate. Do not work around it.

### 7.5 Error handling and run records

One bad page must never end a run. Catch per page, record, continue.

```json
{
  "url": "...", "stage": "capture", "error": "TimeoutError",
  "message": "...", "attempt": 3, "when": "2026-09-08T14:31:02Z"
}
```

Write `_meta/errors.json` at the end of every run, even a fully successful one,
so an empty array is an explicit statement rather than a missing file.

Also write `_meta/run.json`:

```json
{
  "run_id": "20260908T143000Z",
  "started_at": "...", "finished_at": "...",
  "urls_planned": 0, "pages_captured": 0,
  "cms_documents": 0,
  "failed_renders": 0, "not_found": 0, "errors": 0,
  "files_downloaded": 0, "files_bytes": 0,
  "images_skipped": 0,
  "config": {"delay": 1.5, "max_concurrent": 3,
             "cache_mode": "ENABLED", "user_agent": "..."}
}
```

When next week's numbers differ, this is the only way to tell whether the site
changed or the configuration did.

### 7.6 Logging

Standard library `logging`. INFO for per-page progress, WARNING for skips and
retries, ERROR for failures. `--verbose` switches to DEBUG.

One line per page at INFO showing URL and character count. That number makes a
failed render visible while the run is still going, rather than at the end.

---

## 8. Configuration reference

```python
SITE = "https://cuet.ac.bd"
API  = "https://api.cuet.ac.bd/api/v1"

OUT   = Path("cuet_data")
FILES = OUT / "_files"
META  = OUT / "_meta"
CMS   = OUT / "_cms"

DELAY           = 1.5          # seconds per host. Do not lower.
MAX_CONCURRENT  = 3
PAGE_TIMEOUT_MS = 60_000
MAX_RETRIES     = 3
MAX_FILE_BYTES  = 100 * 1024 * 1024

# Calibrate against real pages; see section 7.2
EMPTY_RENDER_THRESHOLD = 4500
EMPTY_TABLE_RE = re.compile(
    r"<table[^>]*>(?:\s|<t[rdh][^>]*>|</t[rdh]>|<tbody[^>]*>|</tbody>)*</table>",
    re.I,
)

# SET 2026-09-08. A CUET address is the best case: it identifies the crawler as
# belonging to one of the university's own students rather than an anonymous
# scraper. With no robots.txt on cuet.ac.bd (7.4), this is the site's only
# channel to reach whoever is running it.
#
# It is a contact address and nothing more — not a credential, and it grants no
# access. Part 2 §9.1 still stands in full: nothing behind a login is in scope.
USER_AGENT = "CUET-Research-Crawler/1.0 (+contact: u2104038@student.cuet.ac.bd)"

ALLOWED_HOSTS = {
    "cuet.ac.bd",
    "www.cuet.ac.bd",          # current routes only; .php excluded, see 6.2
    "app.cuet.ac.bd",          # file host only
    "api.cuet.ac.bd",          # the JSON API: primary source, see 3.0.
                               # ALSO an image host, see 4.6 — data source,
                               # never a crawl target.
    "admissioncuet.ac.bd",     # admission notices
}

# Documents only. Images deliberately absent; see section 4.6.
FILE_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx",
                   ".ppt", ".pptx", ".zip", ".csv")

# NEWS_ID_RANGE and EVENT_ID_RANGE are DELETED. See 4.9.
# /news and /events return complete listings with full bodies; enumerating IDs
# was 419 requests that would still have missed items. Do not reintroduce them.

# Notice types captured by THIS document. The other five are Part 2's.
# Matched against `notice_type_title`, which is what /notices actually returns
# — /notice-types carries the slugs, and the two are not the same string.
NOTICE_TYPES_IN_SCOPE = {
    "Offices Orders/NOC":           "top-bar",     # 265, section 1 top bar
    "Scholarship & Financial Aids": "admission",   #  15
    "Academic Calender":            "academic",    #   3, their spelling. See 3.6.
}                                                  # 283 of 976

# /general-settings keys that hold page bodies -> the page each renders
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
```

### Static routes

```python
STATIC_ROUTES = [
    # home
    "/", "/about/cuet", "/about/campus-life", "/student/organizations",
    # top bar
    "/notices/noc",
    # academic
    "/academic-information",
    "/academic-information/academic-calendars",
    "/academic-information/undergraduate-studies",
    "/academic-information/graduate-studies",
    "/academic-information/international-students",
    "/faculty", "/departments", "/institutes", "/centers",
    # admission
    "/admission",
    "/admission/msc/",                  # found in CMS content, see 4.11
    "/student/undergraduate-student",
    "/student/postgraduate-student",
    "/fsc",
    "/student/scholarship-financial-aids",
    # news and events
    "/news-events", "/events", "/student/events",
]

STUDENT_ORG_SLUGS = [
    "wrro", "ieee-cuet-student", "asce", "ASHRAE-CUET-Student-Branch",
    "rma", "cuet-aci", "cuet-photographic-society", "asrro", "cuetja",
    "joyoddhoney", "cuet-career-club", "green-for-peace",
    "debating-society", "computer-club", "Central-Students-Union",
]
# -> /student/organization/<slug>

EXTERNAL_ENTRY_POINTS = [
    "https://admissioncuet.ac.bd/",
    "https://admissioncuet.ac.bd/about-us",
]
# Noted but NOT crawled by default; combined CKRUET portal:
#   https://admissionckruet.ac.bd/
```

---

## 9. Reference: the site tree

VERIFIED against the API on 2026-09-08. Counts: 5 faculties, 18 departments,
4 institutes, 3 centers.

```
https://cuet.ac.bd/
│
├── TOP BAR
│   ├── mailto:registrar@cuet.ac.bd          filtered by scheme
│   ├── https://alumni.cuet.ac.bd/           out of scope
│   └── /notices/noc                         Offices Orders / NOC
│
├── ACADEMIC  (dropdown, href="#", not itself a page)
│   │
│   ├── /academic-information
│   │   ├── /academic-information/academic-calendars     partially SSR
│   │   ├── /academic-information/undergraduate-studies  also in CMS API
│   │   ├── /academic-information/graduate-studies       also in CMS API
│   │   └── /academic-information/international-students
│   │
│   ├── /faculty                                            [5]
│   │   ├── /faculty/architecture-%26-planning
│   │   ├── /faculty/civil-and-environment-eng
│   │   ├── /faculty/electrical-%26-computer-engineering
│   │   ├── /faculty/mechanical-and-manufacturing-eng
│   │   └── /faculty/science-%26-technology
│   │
│   ├── /departments                                       [18]
│   │   ├── Faculty: Civil and Environment Eng.
│   │   │   ├── /department/CE            Civil Engineering
│   │   │   ├── /department/DEM           Disaster Engineering And Management
│   │   │   └── /department/WRE           Water Resources Engineering
│   │   ├── Faculty: Mechanical and Manufacturing Eng.
│   │   │   ├── /department/ME            Mechanical Engineering
│   │   │   ├── /department/PME           Petroleum And Mining Engineering
│   │   │   ├── /department/MIE           Mechatronics & Industrial Engineering
│   │   │   └── /department/MME           Materials and Metallurgical Engineering
│   │   ├── Faculty: Electrical & Computer Eng.
│   │   │   ├── /department/EEE           Electrical and Electronic Engineering
│   │   │   ├── /department/cse           Computer Science & Engineering
│   │   │   ├── /department/ETE           Electronics & Telecommunication Engineering
│   │   │   └── /department/BME           Biomedical Engineering
│   │   ├── Faculty: Architecture & Planning
│   │   │   ├── /department/Architecture  Architecture
│   │   │   └── /department/URP           Urban and Regional Planning
│   │   └── Faculty: Science & Technology
│   │       ├── /department/Physics       Physics
│   │       ├── /department/Chemistry     Department of Chemistry
│   │       ├── /department/Mathematics   Mathematics
│   │       ├── /department/NE            Nuclear Engineering
│   │       └── /department/hum           Humanities
│   │
│   │   Per department, two known sub-routes. See Appendix B: these came
│   │   from a search index, NOT from a direct fetch, and the real
│   │   sub-navigation of a department page is UNKNOWN.
│   │       /department/<slug>/contact          from search index
│   │       /dept/<slug>/postgraduate           from search index, note /dept/
│   │
│   ├── /institutes                                         [4]
│   │   ├── /institutes/IEER    Institute of Earthquake Engineering Research
│   │   ├── /institutes/IET     Institute of Energy Technology
│   │   ├── /institutes/IICT    Institute of Information and Communication Technology
│   │   └── /institutes/IRHES   Institute of River, Harbor and Environmental Science
│   │
│   └── /centers                                            [3]
│       ├── /centers/ceser                Center for Environmental Science
│       │                                 & Engineering Research
│       ├── /centers/CIPR                 Center for Industrial Problems Research
│       └── /centers/physical-education-2 Physical Education
│
├── ADMISSION
│   ├── /admission
│   ├── /admission/msc/                   found only in CMS content
│   ├── /student/undergraduate-student
│   ├── /student/postgraduate-student
│   ├── /fsc                              Admission of Foreign Students
│   ├── /student/scholarship-financial-aids
│   ├── https://admissioncuet.ac.bd/      separate host, in scope
│   │   ├── /about-us
│   │   └── /file/notices/<name>-<unixtime>-<hash>.pdf
│   └── https://admissionckruet.ac.bd/    combined portal, noted not crawled
│
├── NEWS & EVENTS
│   ├── /news-events                      main listing
│   ├── /events                           event listing
│   ├── /student/events                   student events
│   ├── /news/<id>                        observed 196, 200-203, 205
│   └── /event-details/<id>               observed 136, 137, 138
│
└── HOMEPAGE BODY                         fully server-rendered
    ├── /about/cuet                       linked 6 times; also in CMS API
    ├── /about/campus-life                also in CMS API
    ├── /student/organizations
    │   └── /student/organization/<slug>  15 slugs, see section 8
    └── news and event cards, as above
```

### Estimated planned URL count

| Group | Pages |
|---|---|
| Academic | 75 |
| Admission | 6 plus 2 on the external portal |
| News & Events | 3 listings plus enumerated IDs |
| Homepage body and top bar | 19 |
| CMS documents (stage 2, no HTTP cost) | 8 |

Academic breakdown: 5 academic-information, 1 + 5 faculty, 1 + 54 departments
(18 x 3), 1 + 4 institutes, 1 + 3 centers.

**Superseded 2026-09-08.** The estimate above assumed every page went through a
browser. Actual cost:

| | Requests | Time | Produces |
|---|---|---|---|
| Stage 1, discover | ~45 | ~1 min | the raw API dump |
| Stage 2, content | 0 | seconds | **~530 documents** |
| Stage 4, capture | ~30 | ~1 min | the residual pages |
| Stage 5, files | 283 | ~7 min | the in-scope PDFs |
| **Total** | **~360** | **~10 min** | |

Against the original ~525 browser renders at fifteen minutes, of which roughly
400 were expected to be 404s. The saving is real but it is not the point. **The
point is that the 419 enumerated requests would have produced fewer documents
than two API calls do**, and would have missed items without saying so (4.9).

Most of the remaining time is stage 5, downloading PDFs — which is genuine work
that no API call can avoid, and the one place the 1.5 second delay is actually
the binding constraint.

---

## 9.1 First full run, 2026-09-08

Recorded because the estimates above were predictions and these are
measurements. Stages 1, 2, 5 and 6; stage 4 not yet run.

| Stage | Requests | Time | Result |
|---|---|---|---|
| discover | 47 | 133 s | 17 endpoints + 30 entity details, 0 errors |
| content | 0 | 1.2 s | **234 documents** |
| files | 286 | 457 s | **282 downloaded**, 448 MB, 2 errors |
| audit | 62 | 92 s | found `/counters`, a 17th endpoint |

**234 documents, not the ~530 estimated.** The difference is entirely the
notices, and it is a deliberate design change made after the estimate: 976
notices became 22 index documents rather than 976 near-identical stubs. See
6.8.1. Nothing was lost — every notice's title, date, type and department is in
`_files/index.json`, and the raw payload is in `api_dump.json`.

Verified on the output: `doc_id`s unique, every `content_path` resolves, every
`content_hash` matches its text, every citation URL resolves on cuet.ac.bd,
zero images in `_files/`, zero leftover `.part` files, Bangla correct in 29
documents with no mojibake anywhere.

The 2 file errors are two dead `www.cuet.ac.bd/downloads/*.pdf` links found in
CMS content — the site's own broken links, correctly recorded rather than
retried.

### 6.8.1 Why notices are index documents

Worth stating in the spec rather than only in code, because it is the one place
this implementation deliberately does not produce one document per thing.

A notice record has no prose: it is a title, a date, a type and a PDF link.
Emitting one document each would have produced 265 texts under Offices
Orders/NOC differing only in a title and a date, every one repeating the same
boilerplate. Embedded, those become hundreds of near-identical vectors that
crowd out real content in every retrieval — and most would then be dropped
anyway by the 200-character `--min-text-chars` default (12.2).

Each notice type instead becomes a few index documents holding a table of its
notices, split at 60 rows. Chunking splits those into runs of titles, each chunk
genuinely distinct, and the citation points at the real listing page.

**This is a presentation decision, not a capture decision, and it is reversible
offline.** Everything needed to produce per-notice documents is in
`_meta/api_dump.json`. That is precisely the separation section 4.4 demands, and
the test of it is that changing your mind costs a re-parse rather than a
re-crawl.

---

## 10. Definition of done

**Correctness**

- [ ] `--stage discover` writes `api_dump.json` with **all sixteen** endpoints
      (section 3.0) and a `urls.txt` that a human has read and approved
- [ ] `--stage content` writes eight documents into `_cms/`, and roughly 530
      documents in total across all sources in section 6.8
- [ ] `--stage audit` reports **no** endpoints the config does not know about.
      If it does, the inventory in section 3.0 is stale — update it before
      trusting the run
- [ ] Counts are derived from list lengths, never from a count field (3.3):
      18 departments, not the 15 `/home-counters` reports
- [ ] No slug was resolved by HTTP status code (4.5)
- [ ] Double-escaped CMS values are detected, unescaped once, and flagged
- [ ] Every URL in `urls.txt` is canonical, deduplicated, and passes
      `EXCLUDE_PATTERNS` and `EXCLUDE_HOSTS`
- [ ] Faculty slugs containing `&` are correctly encoded and return 200
- [ ] `/department/cse` and `/department/CE` produce two distinct files on a
      case-insensitive filesystem
- [ ] No URL is assigned to `_unsorted`, or every one that is has been reviewed
      and the section map updated
- [ ] No file path derived from a remote URL contains `..` or exceeds 120
      characters
- [ ] No request is made to `cuet.thetork.com`

**Encoding**

- [ ] A captured news page containing Bangla renders correctly when opened.
      Correct looks like `চুয়েট`; broken looks like `à¦šà§Ÿà§‡à¦Ÿ`
- [ ] Every `read_text` and `write_text` call passes `encoding="utf-8"`
- [ ] Raw HTML is written as bytes

**Images**

- [ ] `_files/` contains zero image files
- [ ] No request is made to any `/storage/News/`, `/storage/Student-*/`,
      `/storage/Admins/`, `/storage/General-Settings/` or `/assets/images/` URL
- [ ] Alt text still appears in the captured markdown

**Robustness**

- [ ] Killing the process mid-run and restarting resumes rather than restarting
- [ ] `--force` re-fetches
- [ ] A page that fails to render is retried, then recorded as an error, and is
      never saved as a valid page
- [ ] `/academic-information/academic-calendars` is correctly detected as a
      failed render if its data grid is empty, despite passing the length check
- [ ] A 404 is recorded as an error and never saved as a page
- [ ] A single failing page does not end the run
- [ ] `errors.json` and `run.json` are written even on a fully successful run

**Politeness**

- [ ] robots.txt has been read by a human and its rules are honoured in code
- [ ] robots.txt is fetched once per host, not per request
- [ ] Measured request rate is at or below one per 1.5 seconds per host
- [x] User-Agent contains a real contact address, not the placeholder —
      `u2104038@student.cuet.ac.bd`, set 2026-09-08 and asserted by a test
- [ ] 429 responses back off and honour `Retry-After`
- [ ] 404 and 403 are never retried

**Human verification, not automatable**

- [ ] Open three captured `.md` files from different sections and read them.
      Confirm they contain what the live pages contain.
- [ ] Open one downloaded PDF and confirm it is not corrupt.
- [ ] Compare a `_cms/` document against its browser-captured counterpart.
      They should agree; if not, investigate before trusting either.
- [ ] Diff `found_pages.txt` against `urls.txt`. Anything in-scope that the
      crawler discovered but was not planned indicates a gap in section 9.
- [ ] Confirm `_files/` contains no duplicate copies of the same document.

**Tests**

Pure functions only. No network, no fixtures.

```python
def test_canonical_removes_fragment_and_trailing_slash(): ...
def test_canonical_collapses_double_slash(): ...
def test_canonical_drops_default_port(): ...
def test_canonical_lowercases_host_but_not_path(): ...
def test_canonical_distinguishes_cse_from_CE(): ...
def test_canonical_preserves_query_string(): ...
def test_page_id_is_stable_across_processes(): ...   # run in a subprocess
def test_safe_name_strips_traversal(): ...
def test_safe_name_caps_length_and_keeps_extension(): ...
def test_encode_slug_handles_ampersand(): ...
def test_section_for_url_exact_before_prefix(): ...
def test_section_for_url_host_rule_wins(): ...
def test_unmatched_url_goes_to_unsorted(): ...
def test_exclude_patterns_reject_php_and_images(): ...
def test_exclude_patterns_do_not_reject_pdf(): ...
def test_empty_table_regex_matches_the_skeleton(): ...
def test_double_escape_detection(): ...

# Added 2026-09-08
def test_page_id_matches_engine_contracts_make_doc_id(): ...
def test_encode_slug_handles_ampersand_in_section_slug(): ...   # l&e, see 4.2
def test_all_four_image_hosts_excluded(): ...                   # incl. api.cuet.ac.bd, 4.6
def test_notice_type_filter_admits_283_of_976(): ...            # see 3.6
def test_notice_filter_matches_title_not_slug(): ...            # "Academic Calender"
def test_department_body_preserves_field_order(): ...           # see 6.8
```

The stability test matters: run `page_id` in a fresh subprocess and assert it
matches, which is what catches an accidental use of `hash()`.

---

## 11. Recommended build order

Revised 2026-09-08. Step 2 is gone: robots.txt has been read and there is none
(7.4). The browser moved from third to last.

1. `config.py` and `paths.py`, with their tests. Pure functions, no network,
   fastest to get right and most expensive to get wrong.
2. `api.py`, the shared polite client. Everything else depends on it behaving.
3. `discover.py` and `content.py`. API-only, fast, and they produce **~530 real
   documents before any browser exists**. Verify `urls.txt` by eye.
4. `files.py`. Still no browser, and the largest concrete payoff — 283 PDFs.
5. `audit.py`. Cheap, and it confirms the endpoint list the previous two stages
   were built on is still complete.
6. `capture.py` last, with `--limit 5`. It is now the smallest stage.
7. Full run, then work through the human verification checklist in section 10.

**Why the browser moved to last.** In the original ordering nothing worked until
Chromium worked. Now four of the six stages produce a usable corpus without it,
so a browser problem is an incomplete run rather than an empty one. Order the
work so the fragile dependency is the last thing you need, not the first.

Resist running the full crawl before step 6 is verified. A full run against a
bad `wait_for` condition produces empty files and pointless requests against
someone else's server. This matters less than it did — thirty pages rather than
five hundred — but the rule is unchanged.

---

## 12. Downstream compatibility note

If this capture feeds a retrieval or RAG pipeline later, four decisions above
exist to make that handoff clean, and changing them costs a re-crawl rather than
a re-parse:

- **Capture and interpretation are separate** (section 4.4), so extraction can
  be re-run offline as often as needed.
- **`page_id` is a stable hash of the canonical URL** (section 6.4), so document
  IDs survive re-runs. Anything referencing those IDs, such as an evaluation
  dataset, breaks if canonicalisation changes.
- **`section_path` is written at capture time** (section 6.6), because it is
  what a citation shows a reader and cannot be reliably reconstructed from file
  paths afterwards.
- **HTML is saved as bytes** (section 4.12), so a decoding mistake is
  recoverable without re-crawling.

Treat canonicalisation and ID generation as frozen once anything downstream
starts referencing them.

Team C's README makes the same point from the other end: `relevant_doc_ids` in
their golden dataset are these hashes, and *"if Team A changes `canonicalize()`
or the seeds, every id shifts and your `relevant_doc_ids` all break."* Once a
dataset exists, section 6.3 is not refactorable.

### 12.1 The concrete handoff shape

The Cortex engine's interface between capture and extraction is **a run
directory**, not a file. From `engine/src/engine/knowledge/README.md`:

```
data/sites/<site>/<run>/
├── pages.jsonl     one CrawledPage per URL. NO TEXT.
├── manifest.json   counts, errors, what was captured
├── raw/            the bytes, exactly as fetched
└── docs/           PDFs and other linked files
```

`engine extract --run <that directory>` is the whole interface. So emitting
"CrawledPage JSONL" is not sufficient — the directory shape is the contract, and
`content_path` in every record must resolve to a file that actually exists
inside it.

**A deliberate deviation, stated rather than slipped in.** `CrawledPage` carries
no text, because extraction is Team B's job and HTML needs cleaning. Content
from the JSON API needs no cleaning: it arrives as prose, with no navigation,
no cookie banner and no footer to strip. So this scraper writes **both**:

- `pages.jsonl` + `raw/` + `docs/` — the standard shape, so `engine extract` can
  run over it normally
- `documents.jsonl` — `CleanDocument` rows for the API-derived documents, where
  the extraction step would have nothing to do

Anything captured through the browser in stage 4 goes into `pages.jsonl` only,
and is extracted normally. Provenance stays visible in `source`.

### 12.2 A short document is not navigation

`engine extract` drops documents below `--min-text-chars`, **default 200**, on
the reasoning that a very short page is usually chrome. That default is wrong
for this corpus and will fail silently.

A notice document is a title, a date, a type and a department — roughly **150
characters**. At the default, most of the 283 notice documents from section 3.6
would be discarded as navigation, with no error and no count to notice it by.
The PDFs would still be on disk, orphaned from the metadata that makes them
findable.

Two things follow:

- Pass `--min-text-chars 50` when extracting this corpus, exactly as the
  bundled fixture site requires and for the same reason.
- **Check the count, do not assume.** `documents.jsonl` should hold roughly 530
  rows. If it holds ~250, this is why.

This is the class of bug section 4.4 exists to prevent: a capture-time decision
that looks like tidiness and is actually data loss.

---

## 13. Open questions

**All six of the original questions are now answered.** The answers are folded
into the sections above; the summary is here so nobody re-investigates something
already settled. Three new questions took their place, and all three are
smaller than the ones they replaced.

### Answered

**Q2. What do `/general-settings` and `/footer-data` contain?**
ANSWERED, and the answer changed the design. `/general-settings` returns the
full HTML body of eight target pages, which is why stage 2 exists (section 3.3).
`/footer-data` returns directorate, office and APA structures, exposed a slug
typo in the site's own footer HTML, and confirmed the site stores Bangla titles
(sections 3.4 and 4.12).

**Q4. Do the `/academic-information/*` pages render server-side?**
ANSWERED: partially. `/academic-information/academic-calendars` returns its
title, breadcrumb, sidebar and page-specific meta tags, but its data grid is
the empty skeleton. Rendering across the site is hybrid, and this is why the
failed-render check needs two conditions rather than one (sections 2 and 7.2).

**Q6. Does the site serve Bangla?**
ANSWERED: yes. News headlines on the homepage are in Bangla, and every
directorate and office in `/footer-data` carries a `bn_title`. Encoding rules
are now mandatory, not advisory (section 4.12).

**Bonus, not originally asked.** The CMS content leaks a vendor domain
(`cuet.thetork.com`), two CMS values are double-escaped, and the `about_us`
prose states department counts that contradict the API. All three are handled in
sections 4.11, 6.8 and 3.3.

**Q1. Does sending the header `RSC: 1` return usable content?**
ANSWERED 2026-09-08: **no, but it is useful anyway.** The header returns a real
React Flight payload — `/departments` drops from 60,404 bytes to 9,605 — but it
holds only the component and chunk manifest. No department data. The browser is
still required for HTML.

What it *is* good for is finding endpoints. The payload lists the page's
JavaScript chunks, and those chunks contain the API paths as string literals.
That two-step is how the twelve undocumented endpoints in section 3.0 were
found, and `--stage audit` now runs it on demand.

**Q3. Is there an API endpoint for news and notices?**
ANSWERED 2026-09-08: **yes, and for almost everything else.** Seventeen endpoints,
not four. `/news` returns 157 items with full bodies, `/notices` returns 976
with a PDF URL on every one, `/administrative-departments` returns 63 entities
with their page bodies, and `/app-admin-research-types` returns 1,560
publications. None paginate.

This is the finding that restructured the document. ID enumeration is deleted
(4.9), the browser drops to a residual stage (2), and the hardest
failed-render case turns out to be three rows of JSON (3.6).

**Q5. What does `cuet.ac.bd/robots.txt` disallow?**
ANSWERED 2026-09-08: **there is no robots.txt.** HTTP 404, with 51 KB of styled
HTML as the body. Allow-all per the standard, which is not the same as
permission — see 7.4 for what follows, and 4.5 for why the HTML body is a trap.

### Still open

**Q7. What is the route pattern for halls, and for APA types?**
`/administrative-departments` returns 9 halls with slugs
(`abu-sayed-hall`, `sufia-kamal-hall`, …), 7 of them with `about` bodies, and
`/apa-sections` returns 7 sections with 35 types. **The content is in hand; only
the URLs are not.** Since a slug cannot be probed by status code (4.5), find the
route by rendering `/student/halls` and `/apa` once and reading the links out of
`found_pages.txt`.

Note this is a smaller question than it looks. A missing route pattern costs the
canonical URL for citation, not the content.

**Q8. `citizen_charter` or `citizen-charter`?**
`/footer-data` gives the underscore, `/apa-sections` gives the hyphen. Two
endpoints of the same API disagree, so the "prefer the API" rule does not settle
it on its own. Record both and resolve when the APA route pattern is known
(Q7). Do not normalise either into the other in the meantime.

**Q9. Does `admissioncuet.ac.bd` have an API of its own?**
It is a separate host and was not scanned. Run the section 3.0 method against it
before crawling it — it is the last in-scope area still assumed to need a
browser, and one `curl` settles whether that is true.

---

## Appendix A: complete homepage link inventory

Every href present in the served HTML of `https://cuet.ac.bd/`, VERIFIED by
direct fetch on 2026-09-08. Recorded here in full, including out-of-scope
entries, so that widening scope later does not require rediscovering them.

97 unique `cuet.ac.bd` page URLs, 5 downloadable files, 6 external hosts.

**IN** means covered by the current scope. **OUT** means deliberately excluded
per section 1 and available for a future version.

### Academic Information (IN)

```
/academic-information
/academic-information/academic-calendars
/academic-information/undergraduate-studies
/academic-information/graduate-studies
/academic-information/international-students
```

### Faculties, departments, institutes, centers (IN)

```
/faculty          /departments          /institutes          /centers
```
Children enumerated from the API; see section 9.

### Admission (IN)

```
/admission
/student/undergraduate-student
/student/postgraduate-student
/fsc
/student/scholarship-financial-aids
/admission/msc/                      (from CMS content, not the nav)
```

### News and events (IN)

```
/news-events    /events    /student/events
/news/<id>      /event-details/<id>
```

### Homepage body and top bar (IN)

```
/                                    (logo, 3 occurrences)
/about/cuet                          (hero x4, at-a-glance, admission card)
/about/campus-life
/notices/noc
/student/organizations
/student/organization/wrro
/student/organization/ieee-cuet-student
/student/organization/asce
/student/organization/ASHRAE-CUET-Student-Branch
/student/organization/rma
/student/organization/cuet-aci
/student/organization/cuet-photographic-society
/student/organization/asrro
/student/organization/cuetja
/student/organization/joyoddhoney
/student/organization/cuet-career-club
/student/organization/green-for-peace
/student/organization/debating-society
/student/organization/computer-club
/student/organization/Central-Students-Union
```

### Research (OUT)

Two coexisting route families. Confirm which redirects before enabling either.

```
current family:
/research/research-highlights
/research/research-area
/research/journal-paper
/research/conference-paper
/research/others
/research/partnership
/research/mou

legacy family, present only in the mobile nav block:
/research-highlights
/research-area
/research-type/publication
/research-type/others
```

Note: `research_highlight` and `research_area` bodies are already available
from `/general-settings` and are captured by stage 2, so two of these seven are
effectively covered already.

### Notices (OUT, except /notices/noc)

```
/notices/all-notice
/notices/student-notices
/notices/general
/notices/appointments
/notices/scholarship-financial-aids
/notices/academic-calender          (misspelled in their code, not a typo here)
/notices/tender
```

All eight notice types, including `noc`, come from
`/home-parameters?academic_headers=1` as `notice_types`, so enabling the rest is
a config change only.

### About (OUT, except /about/cuet and /about/campus-life)

```
/about/history                       body available from /general-settings
/about/vision-and-mission            body available from /general-settings
/about/previous-vc
/about/campus-map
/about/photo-gallery
/about/contact
```

### Administration (OUT)

```
/administration
/office/vc-office
/office/pro-vc-office
/office/registrar-office
/section/comptroller-of-accounts
/section/controller-of-examinations
/section/engineering-office
/section/medical-center
/section/security
/section/transport-section
/directorate/DSW
/directorate/research-extenstion     ← footer spelling; API says research-extension
/directorate/ITBI
/directorate/iqac
/directorate/planning-development
```

`/footer-data` additionally exposes a `brtc` cell not linked in the footer.

### APA (OUT)

```
/apa
/apa/focal-point
/apa/implementation-committee
/apa/evaluation-report
/apa/annual-performance-agreement
```

`/footer-data` additionally exposes `citizen_charter`, not linked in the footer.

### Student and facilities (OUT, except those listed IN above)

```
/student/dsw
/student/halls
/student/notices
```

### Resources (OUT)

```
/downloads
/e-resources
/directories
/institutes/iict                     (lowercase; API slug is IICT, see 4.1)
```

### Documents linked from the homepage (IN as files)

```
https://cuet.ac.bd/assets/pdf/professor-list-26.07.2026.pdf
https://app.cuet.ac.bd/storage/Downloads/Teacher List of CUET-2026 (26.07.2026).pdf
https://app.cuet.ac.bd/storage/Downloads/Officers List of CUET-2026 (26.07.2026).pdf
https://app.cuet.ac.bd/storage/Downloads/Staff List of CUET-2026 (26.07.2026).pdf
https://app.cuet.ac.bd/storage/Downloads/CUET-logo-and-directions.zip
```

### External hosts (OUT except admissioncuet)

```
https://alumni.cuet.ac.bd/           OUT
https://course.cuet.ac.bd            OUT  (student portal, login)
https://library.cuet.ac.bd           OUT  (also appears with trailing slash)
https://student.cuet.ac.bd/          OUT
https://app.cuet.ac.bd               file host only, see 4.7
https://www.youtube.com/@-cuet/videos OUT
https://admissioncuet.ac.bd/         IN
https://admissionckruet.ac.bd/       OUT  (from CMS content; combined portal)
https://www.facebook.com/cuetofficial/          OUT (from /general-settings)
https://bd.linkedin.com/school/chittagong-university-of-engineering-&-technology/  OUT
```

### Non-navigational hrefs

```
#                                    dropdown toggles, 5 occurrences
mailto:registrar@cuet.ac.bd          real
mailto:undefined                     their bug
tel:undefined                        their bug
```

---

## Appendix B: known coverage gaps

**This section exists because the tree in section 9 is complete at the top level
and incomplete at the leaf level.** State of knowledge as of 2026-09-08. Read
this before claiming the crawl is exhaustive.

### What is exhaustively known

Everything sourced from `/home-parameters?academic_headers=1` and
`/administrative-academic-faculties` is complete, because those endpoints return
full lists rather than a page of results:

- 5 faculties, 18 departments, 4 institutes, 3 centers, 8 notice types
- Their slugs, titles, short names and faculty groupings

Everything in Appendix A is complete for the homepage specifically, because it
came from a direct fetch of the served HTML.

### What is NOT known, and why

Every gap below has the same root cause: the page renders its body with
JavaScript, so a plain fetch shows nothing and the sub-navigation could not be
read.

| Unknown | Why it matters |
|---|---|
| **Department sub-pages.** Only `/contact` and `/postgraduate` are known, and both came from a search engine index rather than a direct fetch. A department page may also have people, courses, labs, research, notices or alumni sections. | 18 departments times an unknown number of sub-pages. This is the largest gap by volume. |
| **Faculty sub-pages.** No internal navigation observed. | 5 faculties. |
| **Institute and centre sub-pages.** No internal navigation observed. | 7 pages. |
| **`/admission` content.** Never rendered. Its links, forms and PDFs are unknown. | Whole in-scope section. |
| **`admissioncuet.ac.bd` structure.** Only `/` and `/about-us` known, both from a search index. Its notice listing is unexplored. | The admission PDFs live here. |
| **News and event totals.** `/news-events` pagination behaviour unknown. The ID ranges in section 8 are a guess anchored on six observed news IDs and three event IDs. | May over-request or under-collect. |
| **Academic calendar PDFs.** `/academic-information/academic-calendars` renders its grid empty, so the calendar files themselves were never seen. | In-scope PDFs, count unknown. |
| **NOC notice count.** `/notices/noc` is paginated; only two notices are visible via `header_notices` in the API. | In-scope PDFs, count unknown. |
| **Student organisation count.** 15 slugs came from the homepage carousel. Whether `/student/organizations` lists more is unverified. | Possibly more than 15. |

### How the design compensates

The gaps are expected, and the pipeline is built to close them at runtime rather
than requiring them to be known in advance:

1. **The crawler harvests every link from every rendered page** (section 6.10,
   step 4). Once a department page renders in the browser, its real
   sub-navigation appears in `found_pages.txt`.
2. **`found_pages.txt` is diffed against `urls.txt`** as a required step in the
   definition of done. Anything in scope that was discovered but not planned is
   a gap in section 9 and gets added.
3. **This is a two-pass process, not one.** Run the crawl, diff, extend
   `urls.txt`, run again. Expect the second pass to find pages the first did
   not.

### Required action

After the first full capture, before declaring the scrape complete:

```bash
comm -13 <(sort cuet_data/_meta/urls.txt) \
         <(sort cuet_data/_meta/found_pages.txt) > new_urls.txt
```

Review `new_urls.txt` by hand, add the in-scope entries to section 9 and to
`STATIC_ROUTES` or the relevant builder, and re-run. Update this appendix with
what you found, so the next person inherits a smaller gap than you did.
