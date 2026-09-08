# CUET scrape — inventory of everything fetched

Generated from the live run output (`cuet_data/`), not from notes.
Run date **2026-09-08** · User-Agent `CUET-Research-Crawler/1.0 (+contact: u2104038@student.cuet.ac.bd)`

> **Read this first.** Almost nothing here was scraped from HTML pages. The site is a
> Next.js app whose pages ship no content, but its public JSON API returns that content
> directly. So the API was read instead, and the **browser stage has never run**.

> **On 16 vs 17 endpoints.** 16 were fetched in this run. The audit stage then
> discovered a 17th, `/counters`, which is now in the config but postdates the run
> — it returns every field null, so it would produce nothing. The tables below
> report what was *actually fetched*, not what the config now lists.

## Summary

| | Count |
|---|---|
| API endpoints fetched | 16 + per-entity detail |
| Entity detail calls | 30 |
| Documents produced | 234 (across 215 distinct URLs) |
| Files downloaded | 284 (448 MB) |
| Files recorded, deliberately not downloaded | 690 |
| Links discovered, not followed | 20 |
| Pages planned for the browser stage (not yet run) | 36 |
| **HTML pages actually rendered** | **0** |

## 1. Hosts

| Host | Role | Requests | robots.txt |
|---|---|---|---|
| `api.cuet.ac.bd` | JSON API — the primary source | 46 | 200, `Disallow:` (explicit allow-all) |
| `app.cuet.ac.bd` | File host — PDFs only | 286 | 200, `Disallow:` (explicit allow-all) |
| `cuet.ac.bd` | Audit only (RSC payloads + JS chunks) | 62 | **404 — none exists** |
| `www.cuet.ac.bd` | 2 dead CMS links | 2 | 301 redirect |

**Never contacted:** `alumni.cuet.ac.bd`, `course.cuet.ac.bd`, `student.cuet.ac.bd`,
`library.cuet.ac.bd`, `v2.cuet.ac.bd`, `cuet.thetork.com`, `admissionckruet.ac.bd`.
`admissioncuet.ac.bd` is in scope but **has no DNS record** (verified against 8.8.8.8).

## 2. API endpoints fetched

All returned HTTP 200, unauthenticated.

```
https://api.cuet.ac.bd/api/v1/home-parameters?academic_headers=1
https://api.cuet.ac.bd/api/v1/administrative-departments
https://api.cuet.ac.bd/api/v1/general-settings
https://api.cuet.ac.bd/api/v1/administrative-academic-faculties
https://api.cuet.ac.bd/api/v1/footer-data
https://api.cuet.ac.bd/api/v1/notices
https://api.cuet.ac.bd/api/v1/notice-types
https://api.cuet.ac.bd/api/v1/news
https://api.cuet.ac.bd/api/v1/events
https://api.cuet.ac.bd/api/v1/student-organizations
https://api.cuet.ac.bd/api/v1/academic-curriculums
https://api.cuet.ac.bd/api/v1/app-admin-research-types
https://api.cuet.ac.bd/api/v1/apa-sections
https://api.cuet.ac.bd/api/v1/download-types
https://api.cuet.ac.bd/api/v1/home-counters
https://api.cuet.ac.bd/api/v1/sliders?type=department
https://api.cuet.ac.bd/api/v1/administrative-departments/{slug}   x30
```

The 30 entity slugs:

```
  Architecture                    BME                             CE                              CIPR
  Chemistry                       DEM                             EEE                             ETE
  IEER                            IET                             IICT                            IRHES
  ME                              MIE                             MME                             Mathematics
  NE                              PME                             Physics                         URP
  WRE                             architecture-&-planning         ceser                           civil-and-environment-eng
  cse                             electrical-&-computer-engineering  hum                             mechanical-and-manufacturing-eng
  physical-education-2            science-&-technology
```

Note `architecture-&-planning`, `science-&-technology` and
`electrical-&-computer-engineering` — literal ampersands, percent-encoded per request.

## 3. Documents produced — 215 distinct URLs

Every URL below resolves on cuet.ac.bd. Where several documents share one URL, a long
listing was split into index documents that all cite the same real page.

### `/news` — 155 URLs

News articles with full HTML bodies. IDs 5–206, non-contiguous.

```
  10  101  102  103  104  105  106  107  108  109  11  110
  111  112  113  114  115  116  117  118  119  12  120  121
  ... and 131 more
```

### `/department` — 18 URLs

```
  /department/Architecture
  /department/BME
  /department/CE
  /department/Chemistry
  /department/DEM
  /department/EEE
  /department/ETE
  /department/ME
  /department/MIE
  /department/MME
  /department/Mathematics
  /department/NE
  /department/PME
  /department/Physics
  /department/URP
  /department/WRE
  /department/cse
  /department/hum
```

### `/student` — 15 URLs

```
  /student/organization/ASHRAE-CUET-Student-Branch
  /student/organization/Central-Students-Union
  /student/organization/asce
  /student/organization/asrro
  /student/organization/computer-club
  /student/organization/cuet-aci
  /student/organization/cuet-career-club
  /student/organization/cuet-photographic-society
  /student/organization/cuetja
  /student/organization/debating-society
  /student/organization/green-for-peace
  /student/organization/ieee-cuet-student
  /student/organization/joyoddhoney
  /student/organization/rma
  /student/organization/wrro
```

### `/faculty` — 5 URLs

```
  /faculty/architecture-&-planning
  /faculty/civil-and-environment-eng
  /faculty/electrical-&-computer-engineering
  /faculty/mechanical-and-manufacturing-eng
  /faculty/science-&-technology
```

### `/about` — 4 URLs

```
  /about/campus-life
  /about/cuet
  /about/history
  /about/vision-and-mission
```

### `/institutes` — 4 URLs

```
  /institutes/IEER
  /institutes/IET
  /institutes/IICT
  /institutes/IRHES
```

### `/notices` — 4 URLs

```
  /notices/academic-calender
  /notices/all-notice
  /notices/noc
  /notices/scholarship-financial-aids
```

### `/academic-information` — 3 URLs

```
  /academic-information
  /academic-information/graduate-studies
  /academic-information/undergraduate-studies
```

### `/centers` — 3 URLs

```
  /centers/CIPR
  /centers/ceser
  /centers/physical-education-2
```

### `/event-details` — 2 URLs

```
  /event-details/136
  /event-details/138
```

### `/research` — 2 URLs

```
  /research/research-area
  /research/research-highlights
```

## 4. Files downloaded — 284

| Category | Count |
|---|---|
| Offices Orders/NOC | 265 |
| Scholarship & Financial Aids | 15 |
| Academic Calender | 3 |
| Undergraduate | 1 |

All on `app.cuet.ac.bd` — 283 under `/storage/Notices/`, 1 under `/storage/Downloads/`.
281 `.pdf` + 3 `.docx`, 448 MB total. **Zero images.**

Two failures, both the site's own dead links:

```
  https://www.cuet.ac.bd/downloads/post-graduate.pdf
  https://www.cuet.ac.bd/downloads/Guideline%20for%20Masters%20student.pdf
```

## 5. Recorded but deliberately NOT downloaded — 690

Out-of-scope notice PDFs. Their metadata arrived in the same response so keeping it
cost nothing; fetching the files would have been ~690 more requests. Part 2's scope.

| Category | Count |
|---|---|
| Student Notices | 306 |
| General Notices | 191 |
| Appointments | 121 |
| Tender/E-Tender | 49 |
| All Notices | 23 |

## 6. Discovered, logged, not followed — 20

```
  http://ieeecuetsb.org
  http://www.ascecuet.info
  https://admissionckruet.ac.bd
  https://cuet.ac.bd/admission/msc
  https://cuet.ac.bd/profile/faculty-member/dr-fowzia-gulshana-rashid-lopa
  https://cuet.ac.bd/profile/faculty-member/dr-md-jahedul-islam
  https://cuet.ac.bd/profile/faculty-member/dr-md-reaz-akter-mullick
  https://cuet.ac.bd/profile/faculty-member/dr-pranab-kumar-dhar
  https://cuet.ac.bd/profile/faculty-member/nur-mohammad
  https://cuetcc.org
  https://drive.google.com/file/d/1KpjMGsUCgGzt59EnsjEbYvByOoqPhQnQ/view?usp=sharing
  https://drive.google.com/file/d/1R_Aq8d0rmVnSCNcbu3UhR3yqE6xB7P76/view?usp=sharing
  https://icace.cuet.ac.bd
  https://www.facebook.com/asce.sc.cuet
  https://www.facebook.com/events/2815067138674843
  https://www.facebook.com/share/1BdkLktiKG
  https://www.facebook.com/wrro.cuet
  https://www.linkedin.com/company/ieeecuetsb?lipi=urn%3Ali%3Apage%3Ad_flagship3_search_srp_all%3Be5JaCd0XR0im3bVvj%2FZyew%3D%3D
  https://www.linkedin.com/company/wrro-cuet
  https://www.wrrocuet.org
```

**`/profile/faculty-member/<slug>` is worth attention.** It appears in no navigation,
no sitemap, and in neither spec. With ~398 faculty members it is potentially the
largest uncaptured area on the site — and it is personal data (names, emails, phones),
so Part 2 §8.2 applies. Flagged, not followed.

## 7. Planned for the browser stage — 36, NOT YET FETCHED

Stage 4 has never run. These are the URLs the API does not cover.

```
  https://cuet.ac.bd
  https://cuet.ac.bd/academic-information
  https://cuet.ac.bd/academic-information/international-students
  https://cuet.ac.bd/admission
  https://cuet.ac.bd/admission/msc
  https://cuet.ac.bd/fsc
  https://cuet.ac.bd/student/undergraduate-student
  https://cuet.ac.bd/student/postgraduate-student
  https://cuet.ac.bd/news-events
  https://cuet.ac.bd/events
  https://cuet.ac.bd/student/events
  https://cuet.ac.bd/notices/noc
  https://cuet.ac.bd/departments
  https://cuet.ac.bd/faculty
  https://cuet.ac.bd/institutes
  https://cuet.ac.bd/centers
  https://cuet.ac.bd/dept/NE/postgraduate
  https://cuet.ac.bd/dept/MME/postgraduate
  https://cuet.ac.bd/dept/Mathematics/postgraduate
  https://cuet.ac.bd/dept/Chemistry/postgraduate
  https://cuet.ac.bd/dept/Physics/postgraduate
  https://cuet.ac.bd/dept/hum/postgraduate
  https://cuet.ac.bd/dept/URP/postgraduate
  https://cuet.ac.bd/dept/Architecture/postgraduate
  https://cuet.ac.bd/dept/MIE/postgraduate
  https://cuet.ac.bd/dept/PME/postgraduate
  https://cuet.ac.bd/dept/ME/postgraduate
  https://cuet.ac.bd/dept/WRE/postgraduate
  https://cuet.ac.bd/dept/DEM/postgraduate
  https://cuet.ac.bd/dept/CE/postgraduate
  https://cuet.ac.bd/dept/BME/postgraduate
  https://cuet.ac.bd/dept/EEE/postgraduate
  https://cuet.ac.bd/dept/cse/postgraduate
  https://cuet.ac.bd/dept/ETE/postgraduate
  https://admissioncuet.ac.bd
  https://admissioncuet.ac.bd/about-us
```

## 8. Explicitly out of scope

| Area | Why |
|---|---|
| `alumni.cuet.ac.bd` | Separate application; serves `<meta name="robots" content="noindex">` |
| `course.` / `student.cuet.ac.bd` | Login required |
| `library.cuet.ac.bd` | Separate application |
| `v2.cuet.ac.bd`, `*.php` | Legacy site, undated content |
| `cuet.thetork.com` | Vendor/staging domain leaked into CMS content |
| All images | Nothing downstream can embed a PNG |
| 693 out-of-scope notices | Part 2 |
| Research, Administration, APA, Downloads | Part 2 (raw payloads already captured) |

