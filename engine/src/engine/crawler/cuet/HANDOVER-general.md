# Handover: portion `general`

Scope: `builders/general.py`, `builders/about.py`, `builders/facilities.py`, and
the `general` entry in the portion registry. Written while wiring
`build_administration` and `build_downloads` into the registry, 2026-09-10.

## Known inconsistency: the CMS pages are filed twice, differently

`build_cms` hardcodes `section="_cms"` (`builders/general.py`), so its eight
documents land in `_cms/`. Routing disagrees: `section_for_url` now sends
`/about/history` and `/about/vision-and-mission` to `about`, and
`/academic-information/*` to `academic`. Both are reachable, because the two
stages use different sources for the folder — `write_document` uses
`doc.section`, `capture.py` uses `section_for_url(url)`. A browser capture of
`/about/history` therefore writes `about/history__<id>.html` while stage 2 has
already written `_cms/history__<id>.html`: the same page, two folders, two ids.

This is NOT the same class of problem as a missing `GROUPS` line, and no
`GROUPS` line fixes it. A missing entry is nobody having chosen; this is two
places actively choosing differently. It needs a rule picked:

* keep `_cms` as a provenance folder and accept that routing disagrees, or
* have `build_cms` set the section from `section_for_url(url)` and let `_cms`
  hold only the pages with no route of their own.

Not decided here because it moves already-committed files and changes what
`handover.py`'s `_cms` description promises Team B.

## Open questions left for whoever picks this up

* **`build_administration` produces 15 documents, not the 21 its docstring
  claims.** `_ENTITY_GROUPS` walks `directorates` (6), `administrative_offices`
  (3) and `office_section` (6) from `/footer-data`. APA is not in that table.
  The two APA sources disagree: `/footer-data.footer_apa_types` has 5 rows with
  `title: None` and ids 1-6 that collide with academic-department ids in
  `/administrative-departments` (so an id join there pulls the wrong bodies),
  while `/apa-sections` has 7 rows with real `english_title`/`bangla_title`
  (note: not `title`/`bn_title`) and a nested `apa_types` list of link items and
  no prose field. Neither sums to 21. The `/apa` prefix and group are already in
  `SECTIONS`/`GROUPS`, so the routing is ready whenever this is settled.
* **Four root-level research routes are still unclaimed.**
  `/research-area`, `/research-highlights` and `/research-type/publication` are
  linked from the footer and route to `_unsorted`; `/research/research-area`
  and `/research/research-highlights` are the CMS pages above and route there
  too. The four publication routes (`/research/journal-paper`,
  `/research/conference-paper`, `/research/partnership`, `/research/mou`) are
  settled — they route to `research/publications`, agreeing with what
  `build_research` sets.

  Do NOT close the gap with a bare `"/research"` prefix. `section_for_url`
  matches with plain `str.startswith`, not by path segment, so that prefix
  claims `/research-area`, `/research-highlights` and
  `/research-type/publication` as well — routes that are not under `/research/`
  at all — and it would also route the two CMS research pages away from `_cms`,
  deepening the undecided disagreement above. The same trap applies to any
  future rule here.
* **`--stage verify` fails until `--stage discover` is re-run.** `verify.py`
  compares `{e.path for e in config.ENDPOINTS}` against the dump keys without
  stripping query params, and the newly declared
  `/downloads?search=&download_type_slug=&administrative_department_id=` is not
  in the committed `api_dump.json` yet. `audit.py` already strips params and is
  unaffected. Any builder reading that dump entry must use the full key,
  params included.
* **`README.md`'s portion table still says `UNASSIGNED` for all four portions**,
  including `general`, which the registry has owned by Dipika Nath.
