# CUET Website Scraper, Part 2: Full-Site Coverage

**Companion to:** `CUET_SCRAPER_SPEC.md` (referred to below as **Part 1**)
**Target site:** `https://cuet.ac.bd` and its subdomains
**Status:** specification, not yet implemented
**Site facts verified:** 2026-09-08

---

## 0. What this document is

Part 1 scopes the crawler to four areas: Homepage, Top bar, Academic, Admission,
News & Events. This document specifies **everything else**, so that Part 1 plus
Part 2 together cover the entire CUET web estate.

**Part 2 does not replace Part 1.** Every rule in Part 1 still applies without
modification:

| Concern | Where it is specified |
|---|---|
| Why a browser is required, hybrid rendering | Part 1, section 2 |
| The API, and CMS bodies in `/general-settings` | Part 1, section 3 |
| Canonicalisation, stable IDs, filesystem paths | Part 1, sections 6.3 to 6.5 |
| Resumability, failed-render detection, atomic writes | Part 1, section 7 |
| Politeness, robots.txt, delay, retries | Part 1, section 7.4 |
| No images, ever | Part 1, section 4.6 |
| Encoding and Bangla handling | Part 1, section 4.12 |

Part 2 adds **new sections, new hosts, new route families and new risks**. It
does not add a second codebase. Everything here is a configuration extension of
the same crawler, as Part 1 section 6.1 requires.

**Note on versions.** If your copy of Part 1 is 1464 lines it predates
Appendices A and B. Get the current version, which also carries the 2026-09-08
revision described below.

---

## 0.1 The 2026-09-08 revision, and what it does to this document

**Section 15 question 1 — "is there an API endpoint for notices, news and
publications?" — is answered. Yes.** It was correctly identified here as "the
single highest-value unknown in this document", and answering it removes most of
this document's risk and roughly all of its unpredictability.

Seventeen endpoints exist, not four. Part 1 section 3.0 lists them and explains
the method that found them. What it means for Part 2:

| This document said | Now |
|---|---|
| §3.4 Notice pagination is "the open risk"; a notice archive "can easily run to several hundred entries" | **976 notices, one request, no pagination.** Every one carries its PDF URL |
| §3.3 Notices "render worse than anything in Part 1" — no title, no breadcrumb, empty table | True of the HTML, and now irrelevant. The data does not come from the HTML |
| §2.4 Publication listings are "the most likely place on the whole site to contain a long paginated list, so budget for it" | **1,560 publications** (1,358 journal, 202 conference), one request, no pagination |
| §15 Q3 Do per-hall pages exist? | **9 halls**, slugs known, 7 with `about` bodies. Only the *route* is unknown |
| §6 APA structure from `/footer-data` | `/apa-sections` gives 7 sections and 35 types directly |
| §13 "past 1400 pages… over half an hour of continuous requests" | Part 1 and Part 2 together are ~17 API calls plus a few dozen browser pages |
| §5.1 Administration structure from `/footer-data` | `/administrative-departments` returns all of it, **plus six entities the footer never links** |

### Three corrections, in order of how much damage they would have done

**1. Section 14's route-resolution checks cannot work, and section 5.2's method
is wrong.** This document makes four `curl` status checks a do-these-first
blocker, and §5.2 says "use whichever returns 200". All twelve URLs were tested.
**Every one returned 200**, including `/directorate/research-extenstion` — the
transposition typo §5.2 predicts will 404.

The cause is in Part 1 section 4.5: a Next.js `[slug]` route matches any slug
and renders not-found on the client, so the status code carries no information.
The API settles it instead — the slug is `research-extension`. Treat §14's four
checks as **attempted and inconclusive by design**, not as unfinished work.

**2. Section 12.2's administration list is incomplete**, and for the reason this
document already identifies in §5.2 — it was built from the footer.
`/administrative-departments` returns six entities that appear nowhere in it:

```
ucrl                 directorate   University Central Research Laboratory
auditcell            cell          Pre Audit Cell
Procurement          section       Procurement Section       ← note the capital P
academic-section     section       Academic Section
library              section       Library                   ← not the subdomain
public-relation      section       Public Relation Section
```

That is on top of the `brtc` and `citizen_charter` gaps §5.2 and §6 already
flag. Same root cause, four more instances than expected. Build the list from
`/administrative-departments`, and treat §12.2 as a review checklist.

**3. Section 6's `citizen_charter` claim is contested by the API itself.** This
document insists the underscore is real and must not be normalised.
`/footer-data` agrees. **`/apa-sections` returns `citizen-charter`, with a
hyphen.** Two endpoints of the same API disagree, so "prefer the API over
scraped HTML" does not settle it. Record both, normalise neither, resolve when
the APA route pattern is known.

### What did not change

Everything in this document about **judgement** stands unaltered, and it is the
part worth keeping:

- §8.2 on `/directories` and personal data. The API gives a `department_head`
  per entity but no bulk directory, so the decision is still live and still
  ought to be made deliberately.
- §9.1 on authenticated hosts. Nothing found here changes it.
- §10 on legacy sites and undated content — the argument that mixing 2019 and
  2026 content silently is worse than missing it.
- §4.2 on `/about/photo-gallery` and the `image_only_page` error reason.

The API made the crawl cheaper. It did not make any of those decisions for us.

---

## 1. Coverage map

| Area | Part 1 | Part 2 |
|---|---|---|
| Homepage, top bar | ✅ | |
| Academic (faculty, departments, institutes, centers) | ✅ | |
| Admission, admissioncuet.ac.bd | ✅ | |
| News & Events | ✅ | |
| **Research** (both route families) | | ✅ §2 |
| **Notices** (7 remaining types) | | ✅ §3 |
| **About** (6 remaining pages) | | ✅ §4 |
| **Administration** (offices, sections, directorates) | | ✅ §5 |
| **APA** | | ✅ §6 |
| **Student and facilities** | | ✅ §7 |
| **Downloads, E-Resources, Directories** | | ✅ §8 |
| **Subdomains** (library, course, student, alumni, app) | | ✅ §9 |
| **Legacy sites** (www PHP, v2) | | ✅ §10 |
| **External** (YouTube, Facebook, LinkedIn, CKRUET) | | ✅ §11 |

After both parts, the only URLs left uncovered are those behind
authentication, which are covered by §9 as a deliberate exclusion rather than an
oversight.

---

## 2. Research

### 2.1 The duplicate route problem

VERIFIED. Two route families coexist, both present on every page, in different
navigation blocks. The desktop nav emits one, the mobile nav emits the other.

```
CURRENT FAMILY (desktop nav, footer)
/research/research-highlights
/research/research-area
/research/journal-paper
/research/conference-paper
/research/others
/research/partnership
/research/mou

LEGACY FAMILY (mobile nav block only)
/research-highlights
/research-area
/research-type/publication
/research-type/others
```

**Required first task.** Before crawling either family, determine what the
legacy routes do:

```bash
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" \
  https://cuet.ac.bd/research-highlights
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" \
  https://cuet.ac.bd/research-type/publication
```

Three possible outcomes and the correct response to each:

| Result | Action |
|---|---|
| 301/302 to the `/research/*` equivalent | Add the legacy family to `EXCLUDE_PATTERNS`. Following a redirect to a page you already have is wasted requests and a duplicate document. |
| 200 with identical content | Same action. Record in this document that they are aliases. |
| 200 with **different** content | Both families are in scope. `/research-type/publication` and `/research-type/others` in particular have no `/research/*` counterpart, so they may be genuinely distinct. |

Do not skip this check. Guessing produces either duplicates or silent data loss,
and one `curl` settles it.

### 2.2 Two of these are already covered

Part 1 stage 2 already captures `research_highlight` and `research_area` from
`/general-settings` as CMS documents. So the browser capture of
`/research/research-highlights` and `/research/research-area` is a
cross-check, not the primary source.

Reminder from Part 1 section 3.3: both of those CMS values are **double-escaped**
and must be unescaped once before conversion.

### 2.3 Research types come from the API

VERIFIED. `/home-parameters?academic_headers=1` returns `header_research_types`,
and `/footer-data` returns `footer_research_types` with `journal-paper` and
`conference-paper`. Build the research route list from the API rather than from
scraped links, per the rule in Part 1 section 3.4.

### 2.4 Expected content shape

`/research/journal-paper` and `/research/conference-paper` are publication
listings. UNVERIFIED whether they paginate. If they do, the pagination is
client-side and you will need either the API endpoint behind them (see §12
question 1) or a scroll or click interaction in `crawl4ai`.

Publication listings are the most likely place on the whole site to contain a
long paginated list, so budget for it.

---

## 3. Notices

### 3.1 All eight types come from the API

VERIFIED. `/home-parameters?academic_headers=1` returns `notice_types` as a
complete list. Part 1 already crawls `noc`. The remaining seven:

```
/notices/all-notice
/notices/student-notices
/notices/general
/notices/appointments
/notices/scholarship-financial-aids
/notices/academic-calender          ← misspelled in their routing, not a typo here
/notices/tender
```

Build these from `notice_types` in the API, not from the nav, so a ninth type
added later appears automatically.

`/notices/all-notice` is almost certainly a superset of the other seven. Crawl
all eight anyway: the per-type pages carry the category, which is metadata you
would otherwise have to infer.

### 3.2 Notices are the most PDF-dense area of the site

This section is the main reason to do Part 2 at all. Every notice is a PDF.

VERIFIED URL pattern, from `header_notices` in the API:

```
https://app.cuet.ac.bd//storage/Notices/<hash>.pdf
```

Note the double slash, which is the site's own bug and is handled by
canonicalisation (Part 1 section 4.7). Concrete examples seen:

```
https://app.cuet.ac.bd//storage/Notices/6a66d4ebbeb68.pdf
https://app.cuet.ac.bd//storage/Notices/68d0d0992efd5.pdf
```

The filenames are opaque hashes with no human-readable component. **This makes
metadata mandatory rather than optional.** A folder of two hundred files named
`6a66d4ebbeb68.pdf` is unusable. Every downloaded notice must record, in
`_files/index.json`:

- the notice title as shown in the listing
- the notice date
- the notice type it appeared under
- the page URL it was linked from

Extend the file index accordingly. Without this, the notices are captured but
not findable.

### 3.3 Notices render worse than anything in Part 1

VERIFIED by direct fetch of `/notices/all-notice`. Its served HTML has:

- no page-specific `<title>`; it falls back to the site default
  `Chittagong University of Engineering and Technology.`
- no page-specific meta description
- no breadcrumb
- the empty four-column table skeleton documented in Part 1 section 2

So it is *worse* than the partially-rendered case. There is nothing in the HTML
that identifies which notice type the page is.

Two consequences:

1. The failed-render detection from Part 1 section 7.2 catches this correctly,
   since both the length check and the empty-table check fire.
2. **You cannot derive `section_path` from the page content.** Build it from the
   API's `notice_types` entry for that slug, keyed on the URL. Add this mapping
   explicitly rather than parsing the rendered page for it.

### 3.4 Pagination — RESOLVED, 2026-09-08

This section listed three approaches and said *"do not implement 2 or 3 before
checking 1"*. Option 1 was checked, and it is the outcome:

```
GET https://api.cuet.ac.bd/api/v1/notices     976 notices, 293 KB, no pagination
```

**All 976 in one response.** No page parameter, no browser interaction, no
`js_code`, no `session_id`. The estimate of "several hundred entries" was low by
roughly half, which is the right direction to be wrong in but does show the
scale the browser approach would have faced — 976 detail renders at 1.5 seconds
is over twenty minutes for content that arrives in one call.

Every record carries `title`, `publish_date`, `notice_type_title`,
`administrative_department_title` and `pdf`. **That is exactly the metadata
§12.3 requires**, which this document assumed would have to be scraped off a
rendered listing page and married to the file afterwards. It comes free.

Type breakdown, and the scope split against Part 1:

| Type | Count | Whose |
|---|---|---|
| Student Notices | 309 | Part 2 |
| Offices Orders/NOC | 265 | Part 1 |
| General Notices | 191 | Part 2 |
| Appointments | 121 | Part 2 |
| Tender/E-Tender | 49 | Part 2 |
| All Notices | 23 | Part 2 |
| Scholarship & Financial Aids | 15 | Part 1 |
| Academic Calender | 3 | Part 1 |

Note the filter key. `/notices` returns `notice_type_title` — the display
string, `"Offices Orders/NOC"` — while `/notice-types` carries slugs such as
`noc`. **They are not the same string and neither is derivable from the other.**
Filter on the title as returned, and keep the mapping explicit.

**One scope decision this creates.** All 976 records are already in hand after a
single request, so capturing the *metadata* for the 693 out-of-scope notices
costs nothing. Downloading their 693 PDFs does not. Those are separate
decisions and should be made separately — the metadata is worth keeping even
when the file is not.

---

## 4. About

Six pages remain. Part 1 already covers `/about/cuet` and `/about/campus-life`.

```
/about/history                  body ALSO available from /general-settings
/about/vision-and-mission       body ALSO available from /general-settings
/about/previous-vc
/about/campus-map
/about/photo-gallery
/about/contact
```

### 4.1 Two are already captured

`history` and `mission_vision` are CMS keys already handled by Part 1 stage 2.
Add them to `CMS_CONTENT_KEYS` if they are not there; Part 1 section 8 already
lists both. The browser capture is a cross-check.

### 4.2 Photo gallery needs an explicit rule

`/about/photo-gallery` is, by definition, a page of images, and Part 1 section
4.6 forbids downloading images.

**The rule does not change.** Capture the page's text, captions and structure.
Download none of the images. If the gallery has no text at all, the page will
trip the failed-render check and land in `errors.json`, which is the correct
outcome: an image-only page is genuinely empty for this project's purposes.

Record it in `errors.json` with a distinct reason, `image_only_page`, so nobody
later mistakes it for a rendering bug and spends an afternoon debugging it.

### 4.3 Contact page

`/about/contact` may contain a form. Do not submit it. Capture the page text and
any contact details, and note that `/general-settings` already gives you the
canonical `phone`, `email` and `address` values, which are more reliable than
scraped ones.

---

## 5. Administration

### 5.1 Structure comes from `/footer-data`

VERIFIED. `/footer-data` returns three lists that together define this whole
section, with `id`, `title`, `bn_title`, `short_name`, `slug` and `type`:

**`administrative_offices`**
```
/office/vc-office            Vice Chancellor
/office/pro-vc-office        Pro Vice Chancellor
/office/registrar-office     Registrar
```

**`office_section`**
```
/section/comptroller-of-accounts       The Comptroller           type: office
/section/controller-of-examinations    Controller of Examinations type: section
/section/engineering-office            Engineering Office         type: office
/section/medical-center                Medical Center             type: section
/section/security                      Security Section           type: section
/section/transport-section             Transport                  type: section
```

**`directorates`**
```
/directorate/DSW                       Directorate of Student's Welfare
/directorate/research-extension        Directorate of Research and Extension
/directorate/ITBI                      IT Business Incubator          type: cell
/directorate/iqac                      Institutional Quality Assurance Cell
/directorate/planning-development      Planning and Development
/directorate/brtc                      BRTC                           type: cell
```

Plus the landing page `/administration`.

### 5.2 Two findings that matter

**A slug typo in the site's own footer.** VERIFIED. The API gives
`research-extension`. Every page's footer links to
`/directorate/research-extenstion`, with the letters transposed. One of the two
404s.

Required action:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://cuet.ac.bd/directorate/research-extension
curl -s -o /dev/null -w "%{http_code}\n" https://cuet.ac.bd/directorate/research-extenstion
```

Use whichever returns 200 and add the other to `EXCLUDE_PATTERNS` so the crawler
does not keep retrying a link that every page emits. Record the answer here.

This is the concrete case behind the Part 1 rule: **prefer API slugs over slugs
scraped from HTML**.

**`brtc` is not in the footer.** The API lists it; no page links to it. A
link-following crawler would never reach it. This is the concrete case behind
building URL lists from the API rather than from discovered links.

### 5.3 Bangla titles

Every entry here carries a `bn_title` in Bangla. Store both `title` and
`bn_title` in the page metadata. This is a bilingual site, and for
administration pages the Bangla name is frequently the one people search for.

Part 1 section 4.12 encoding rules apply. This section is where they matter
most, because Bangla is present in structured data rather than only in prose.

---

## 6. APA

Annual Performance Agreement. Government-mandated reporting, so this section is
almost entirely PDFs.

VERIFIED from `/footer-data` as `footer_apa_types`, each with `english_title`,
`bangla_title` and `slug`:

```
/apa                                  landing page
/apa/annual-performance-agreement
/apa/evaluation-report
/apa/implementation-committee
/apa/focal-point
/apa/citizen_charter                  ← NOT linked in the footer
```

Note two things. `citizen_charter` uses an **underscore** while every other slug
on the site uses hyphens, so do not normalise it. And it appears in the API but
not in the footer, so like `brtc` it is unreachable by link-following.

Expect these pages to be thin wrappers around PDF links. Apply the §3.2 metadata
rule: capture the document title and date alongside the file, because APA
filenames are unlikely to be self-describing.

---

## 7. Student and facilities

Part 1 covers `/student/organizations`, the 15 organisation pages,
`/student/events`, `/student/scholarship-financial-aids`,
`/student/undergraduate-student`, `/student/postgraduate-student` and `/fsc`.

Remaining:

```
/student/dsw            Directorate of Student's Welfare
/student/halls          Halls of Residence
/student/notices        Student Notices
```

### 7.1 Two routes for the same thing

`/student/dsw` and `/directorate/DSW` both refer to the Directorate of Student's
Welfare. `/student/notices` and `/notices/student-notices` both refer to student
notices. UNVERIFIED whether each pair is the same page, a redirect, or two
different views.

Check with `curl` as in §2.1. If they are aliases, keep one and exclude the
other; if they differ, keep both. Left unchecked, this is a guaranteed source of
duplicate documents.

### 7.2 Halls

`/student/halls` is worth calling out because `/general-settings` states there
are **9 halls, 6 male and 3 female**, and the homepage links three hall images
on `app.cuet.ac.bd/storage/Student-Halls/`. So individual hall pages probably
exist at some route like `/student/hall/<slug>`.

UNVERIFIED. The route pattern is unknown and cannot be guessed reliably, given
the slug inconsistency documented in Part 1 section 4.1. Render
`/student/halls` in the browser and read the links out of `found_pages.txt`.

---

## 8. Downloads, E-Resources, Directories

```
/downloads          downloadable forms
/e-resources        electronic resources
/directories        staff and faculty directory
```

### 8.1 `/downloads` is a priority target

This page is the site's own file index. VERIFIED files already reachable from
the footer, all on `app.cuet.ac.bd/storage/Downloads/`:

```
Teacher List of CUET-2026 (26.07.2026).pdf
Officers List of CUET-2026 (26.07.2026).pdf
Staff List of CUET-2026 (26.07.2026).pdf
CUET-logo-and-directions.zip
```

Plus `cuet.ac.bd/assets/pdf/professor-list-26.07.2026.pdf`, which is on a
different host and in a different directory from the other three, so do not
assume one location.

The rendered `/downloads` page will contain many more. Expect forms in `.pdf`,
`.doc` and `.docx`, which is why Part 1's `FILE_EXTENSIONS` includes the Office
formats.

### 8.2 `/directories`

A staff or faculty directory. Two cautions:

**Volume.** A directory of 200+ faculty and 350+ staff may be paginated or may
link to per-person pages. Check before crawling; this could be the largest page
count on the site.

**Personal data.** Directory pages contain names, phone numbers and email
addresses of individuals. That is published data on a public site, but it is
still personal data. Do not redistribute the scraped directory, do not use it to
build a contact list, and consider whether you need this page at all for your
actual purpose. If the answer is no, exclude it. That is a judgement call that
should be made deliberately rather than by default.

### 8.3 `/e-resources`

Likely a link page to external library and database subscriptions. Most links
will point off-site to publishers, which are out of scope. Capture the page,
record the links in `found_pages.txt`, follow none of them.

---

## 9. Subdomains

This is where "scrape everything" needs a firm boundary, because several of
these are applications rather than content sites.

| Host | What it is | Recommendation |
|---|---|---|
| `app.cuet.ac.bd` | Admin portal and file store | **File host only.** Already in Part 1's `ALLOWED_HOSTS` for that purpose. Do not crawl it as a site; it is a login-protected CMS backend. |
| `library.cuet.ac.bd` | Library system | Probably crawlable. Separate application with its own structure, so treat as a separate project rather than folding into this crawler. |
| `course.cuet.ac.bd` | Student portal | **Login required. Exclude.** |
| `student.cuet.ac.bd` | Student portal | **Login required. Exclude.** |
| `alumni.cuet.ac.bd` | Alumni site | Probably crawlable, probably a separate application. Check whether it requires registration before deciding. |
| `admissioncuet.ac.bd` | Admission portal | Already in Part 1. |
| `api.cuet.ac.bd` | The JSON API | Not a site. Used as a data source per Part 1 section 3. |

### 9.1 The rule for login-protected hosts

Do not attempt to access anything behind authentication, even if you personally
have an account. Two reasons, and the first is sufficient on its own:

1. **Credentials are personal, not institutional.** Using your student login to
   bulk-download content is a different act from crawling public pages, and it
   is very likely a violation of the acceptable use terms you agreed to.
2. Authenticated pages contain other people's data.

If content behind a login is genuinely needed, the correct route is to ask CUET
IT for it. That is not a workaround, it is the actual solution, and universities
often say yes to a clearly-explained academic request.

### 9.2 If you do crawl library or alumni

Treat each as a separate run with its own output directory, its own robots.txt
check and its own delay budget. Do not fold them into `cuet_data/`, because they
are different sites with different structures and mixing them makes both harder
to reason about.

---

## 10. Legacy sites

VERIFIED to exist via search index, not yet fetched:

```
https://www.cuet.ac.bd/dep_cse.php
https://www.cuet.ac.bd/lab_cse.php
https://www.cuet.ac.bd/faculties
https://www.cuet.ac.bd/ncwre/contact.php
https://v2.cuet.ac.bd/
```

Part 1 excludes these via the `\.php` pattern and the `EXCLUDE_HOSTS` entry for
`v2.cuet.ac.bd`.

### 10.1 Should you include them?

**Argument for.** They are probably server-rendered PHP, which means no browser
and no failed-render risk. They may contain department detail, lab listings and
course information that the new site has not migrated. For a department like
CSE, `lab_cse.php` could hold lab equipment and research group information that
exists nowhere else.

**Argument against.** They are stale by an unknown margin. Mixing 2019 content
with 2026 content in one corpus, with no date marking, produces a dataset where
a retrieval system confidently returns an obsolete answer. That failure is worse
than missing the content entirely.

### 10.2 If you include them

Three conditions, all of them:

1. **Separate output directory.** `cuet_data_legacy/`, never mixed in.
2. **Mark every document.** `"vintage": "legacy"` in the metadata, and a
   `section_path` beginning with `["Legacy site"]`.
3. **Establish the date first.** Find a datestamp on the legacy pages, or check
   `Last-Modified` headers, and record what you find. Content with no
   determinable date should not be merged into a live corpus.

Default recommendation: **exclude them from version one.** Revisit only if a
specific gap in the new site's coverage turns out to be filled by the old one.

---

## 11. External links

Present on the site, not part of it. Record them in `found_pages.txt`, follow
none of them.

```
https://www.youtube.com/@-cuet/videos                official channel
https://www.facebook.com/cuetofficial/               from /general-settings
https://bd.linkedin.com/school/chittagong-university-of-engineering-&-technology/
https://admissionckruet.ac.bd/                       combined CUET/KUET/RUET portal
https://cuet.thetork.com/                            vendor/staging, see Part 1 §4.11
```

`admissionckruet.ac.bd` is the only genuinely arguable one, since it hosts the
actual combined admission process for three universities. If admission content
is a priority, it is a separate project with its own spec, not an extension of
this crawler.

The YouTube channel is referenced by an `<oembed>` tag inside the `about_us` CMS
value. Do not attempt to download video.

---

## 12. Configuration deltas

Everything below extends Part 1 section 8. No existing value changes.

### 12.1 New sections

```python
SECTIONS |= {
    "research": SectionRule(
        subdir="research",
        prefixes=("/research/", "/research-type/",
                  "/research-highlights", "/research-area"),
    ),
    "notices": SectionRule(
        subdir="notices",
        prefixes=("/notices/",),          # /notices/noc stays in top-bar via `exact`
    ),
    "about": SectionRule(
        subdir="about",
        prefixes=("/about/",),            # /about/cuet, /about/campus-life stay in home
    ),
    "administration": SectionRule(
        subdir="administration",
        exact=("/administration",),
        prefixes=("/office/", "/section/", "/directorate/"),
    ),
    "apa": SectionRule(
        subdir="apa",
        exact=("/apa",),
        prefixes=("/apa/",),
    ),
    "student": SectionRule(
        subdir="student",
        prefixes=("/student/dsw", "/student/halls", "/student/notices",
                  "/student/hall/"),
    ),
    "resources": SectionRule(
        subdir="resources",
        exact=("/downloads", "/e-resources", "/directories"),
    ),
}
```

The `exact`-before-`prefixes` rule from Part 1 section 6.1 is what makes this
work. `/notices/noc` stays in `top-bar` because it is an `exact` entry there,
even though `notices` has the broader prefix. Same for `/about/cuet` and
`/about/campus-life` in `home`. **Verify this with a test**; it is the kind of
ordering bug that produces silently misfiled documents.

### 12.2 New static routes

```python
STATIC_ROUTES_PART2 = [
    # research (build from API notice/research types where possible)
    "/research/research-highlights", "/research/research-area",
    "/research/journal-paper", "/research/conference-paper",
    "/research/others", "/research/partnership", "/research/mou",
    # legacy research family, pending the §2.1 check
    "/research-highlights", "/research-area",
    "/research-type/publication", "/research-type/others",
    # notices (build from notice_types in the API)
    "/notices/all-notice", "/notices/student-notices", "/notices/general",
    "/notices/appointments", "/notices/scholarship-financial-aids",
    "/notices/academic-calender", "/notices/tender",
    # about
    "/about/history", "/about/vision-and-mission", "/about/previous-vc",
    "/about/campus-map", "/about/photo-gallery", "/about/contact",
    # administration
    "/administration",
    "/office/vc-office", "/office/pro-vc-office", "/office/registrar-office",
    "/section/comptroller-of-accounts", "/section/controller-of-examinations",
    "/section/engineering-office", "/section/medical-center",
    "/section/security", "/section/transport-section",
    "/directorate/DSW", "/directorate/research-extension",   # see §5.2
    "/directorate/ITBI", "/directorate/iqac",
    "/directorate/planning-development", "/directorate/brtc",
    # apa
    "/apa", "/apa/annual-performance-agreement", "/apa/evaluation-report",
    "/apa/implementation-committee", "/apa/focal-point", "/apa/citizen_charter",
    # student
    "/student/dsw", "/student/halls", "/student/notices",
    # resources
    "/downloads", "/e-resources", "/directories",
]
```

Where the API provides a list, build from the API instead of from this literal.
This list is the fallback and the review checklist, not the source of truth.

### 12.3 Extended file metadata

Required by §3.2 and §6, since notice and APA filenames are opaque hashes.

```json
{
  "url": "https://app.cuet.ac.bd//storage/Notices/6a66d4ebbeb68.pdf",
  "local": "_files/1a2b3c4d__6a66d4ebbeb68.pdf",
  "bytes": 284119,
  "content_type": "application/pdf",
  "title": "Notice regarding ...",
  "published_date": "2026-08-14",
  "document_type": "notice",
  "category": "general",
  "linked_from": ["https://cuet.ac.bd/notices/general"]
}
```

`linked_from` is a list because the same file appears on multiple pages. Append
rather than overwrite when a file is rediscovered.

### 12.4 Unchanged

`DELAY`, `MAX_CONCURRENT`, `USER_AGENT`, `EXCLUDE_PATTERNS`, `EXCLUDE_HOSTS`,
`FILE_EXTENSIONS`, the no-images rule and every function in Part 1 section 6
stay exactly as they are. Part 2 adds no new mechanism.

---

## 13. Scale and politeness

Part 1 plans roughly 525 URLs. Part 2 adds:

| Area | Pages | Notes |
|---|---|---|
| Research | 11 | plus publication listings, count unknown |
| Notices | 7 | plus every notice detail page, count unknown |
| About | 6 | |
| Administration | 16 | |
| APA | 6 | |
| Student | 3 | plus per-hall pages, count unknown |
| Resources | 3 | plus directory entries, count unknown |
| **Known subtotal** | **52** | |

The four "count unknown" rows are the risk. A notice archive of 500 entries plus
a staff directory of 350 people would take the total past 1400 pages, which at
1.5 seconds is over half an hour of continuous requests.

**Required:**

- Run Part 2 as a **separate invocation** from Part 1, not one long job. Part 1
  covers the pages most people actually want; getting it done and verified first
  protects it from a Part 2 problem.
- **Do not raise `MAX_CONCURRENT`** to compensate for the larger volume. The
  delay is per host and the host does not care how you have parallelised.
- Check §12 question 1 before crawling notices. An API endpoint turns 500 page
  renders into 5 JSON calls.
- If the total looks like it will exceed roughly 1000 pages, split the run
  across days rather than raising the rate.

---

## 14. Definition of done, Part 2

In addition to every item in Part 1 section 10.

**Route resolution, do these first**

> **Revised 2026-09-08.** All four were attempted by `curl`. **All twelve URLs
> returned HTTP 200**, so the status-code method these items describe cannot
> resolve any of them — see §0.1 correction 1. They are not unfinished work;
> the method was wrong. Resolve by comparing *content* after capture, or from
> the API where it has an opinion.

- [x] The legacy research family's behaviour is determined (§2.1) — both
      families return 200; they must be compared by content, not status
- [x] `research-extension` versus `research-extenstion` is resolved (§5.2) —
      **the API says `research-extension`**; both URLs return 200, so exclude
      the footer's spelling on the API's authority, not on a status code
- [ ] `/student/dsw` versus `/directorate/DSW` — both 200; compare captured
      content
- [ ] `/student/notices` versus `/notices/student-notices` — both 200; compare
      captured content

**Take the general lesson, not just the four fixes.** Four separate checklist
items shared one hidden assumption — that this server distinguishes a real page
from a missing one by status code. It does not, and no amount of care applied to
the individual items would have surfaced that. When several checks rest on one
untested premise, test the premise first.

**Coverage**

- [ ] All 8 notice types crawled, built from the API's `notice_types`
- [ ] `/directorate/brtc` and `/apa/citizen_charter` are crawled despite not
      being linked anywhere
- [ ] `bn_title` is stored alongside `title` for every administration entity
- [ ] `citizen_charter` retains its underscore and was not normalised to a hyphen

**Documents**

- [ ] Every downloaded notice and APA file has a title, date, type and category
      in `_files/index.json`
- [ ] `linked_from` is a list and accumulates rather than overwrites
- [ ] `_files/` still contains zero images, including after `/about/photo-gallery`

**Boundaries**

- [ ] No request was made to `course.cuet.ac.bd` or `student.cuet.ac.bd`
- [ ] No authenticated request was made anywhere
- [ ] Legacy sites are either excluded, or in a separate directory and marked
      with a vintage
- [ ] A deliberate decision was recorded about `/directories` and personal data

**Human verification**

- [ ] Open three notice PDFs and confirm the recorded title matches the content
- [ ] Confirm `/notices/all-notice` captured more than the first page
- [ ] Confirm the section map filed `/notices/noc` under `top-bar` and not
      `notices`, and `/about/cuet` under `home` and not `about`

---

## 15. Open questions for Part 2

### Answered 2026-09-08

**Q1. Is there an API endpoint for notices, news and publications?**
**ANSWERED: yes, for all three, and for most of the rest of the site.** Sixteen
endpoints; see Part 1 section 3.0. `/notices` 976, `/news` 157,
`/app-admin-research-types` 1,560 publications. None paginate.

The prediction in the original wording was right — *"given that faculties,
departments, footer structures and site settings all have endpoints, it is very
likely one exists"* — and under-stated. The method was not DevTools: the Flight
payload lists a page's JS chunks and the chunks contain the endpoint strings, so
the whole inventory is greppable and now runs as `--stage audit`.

**Q2. How does the notice listing paginate?**
**ANSWERED: it does not.** All 976 arrive in one response. See §3.4.

**Q3. Do per-hall pages exist, and at what route?**
**PARTLY ANSWERED.** `/administrative-departments` returns 9 halls as
first-class entities, 7 with `about` bodies:

```
abu-sayed-hall              dr-qudrate-khuda-hall     kazi-nazrul-hall
muktijoddah-hall            shaheed-mohammad-shah-hall
shaheed-tareeq-huda-hall    shamsennahar-khan-hall
sufia-kamal-hall            tapashi-rabeya-hall
```

This confirms the count `/general-settings` gives and supplies the content. The
**route** is still unknown, and since a slug cannot be probed by status code
(Part 1 §4.5), the way to find it is to render `/student/halls` once and read
the links out of `found_pages.txt` — which is what §7.2 already prescribes.

Worth being precise about what remains missing: the canonical URL for citation,
not the content.

### Still open

**Q4. Does `/directories` paginate or link to per-person pages?**
Determines whether it is 1 page or 500. See §8.2.

**Q5. Are the legacy PHP pages datable?**
Needed before any decision to include them. See §10.2.

**Q6. Is `library.cuet.ac.bd` crawlable, and does it have its own robots.txt?**
Determines whether §9 becomes a third document.

---

## 16. Recommended order

1. **Finish Part 1 completely first**, including its human verification
   checklist. Do not start Part 2 with Part 1 unverified.
2. Answer §15 Q1. Ten minutes, and it may restructure §3 entirely.
3. Run the four route-resolution `curl` checks in §14. Five minutes, and they
   prevent duplicate documents across the whole run.
4. Add the sections in §12.1 and the routes in §12.2.
5. Crawl the small, well-understood areas first: About, APA, Administration.
   Roughly 28 pages, no pagination risk, good confidence check.
6. Crawl Research and Student.
7. Crawl Notices last. It is the largest, least predictable area, and by then
   everything else is safely captured.
8. Decide on `/directories` and the legacy sites deliberately, and record the
   decision in this document rather than leaving it implicit in the code.
