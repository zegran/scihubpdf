# Retrieval Playbook

Concrete, hard-won notes behind the cascade in `SKILL.md`. Load this when a fetch
underperforms or an item looks "missing but shouldn't be".

## Source coverage map

| Source | API / pattern | Strengths | Blind spots |
|---|---|---|---|
| Unpaywall | `api.unpaywall.org/v2/{doi}?email=` | Gold/hybrid/green status, direct `url_for_pdf` | `url_for_pdf` often `null` for MDPI/Preprints even when OA |
| Semantic Scholar | `api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=openAccessPdf` | Catches repository/author copies Unpaywall misses | Rate-limited without key (~1 req/s) |
| Crossref | `api.crossref.org/works?query.bibliographic=…&mailto=` | DOI resolution by title+author; finds published version of a preprint | Returns confident false positives — must verify |
| Sci-Hub | this repo's `scihub2pdf` (multi-mirror) | Strong for **≤2021** across most publishers | No new uploads after ~2021; misses 2022+ |

## Sci-Hub freeze (the single most important fact)

Sci-Hub paused adding new papers around 2021 (pending litigation). Empirically in this
project: a 2017 and 2019–2021 papers were found; **every 2022–2025 Elsevier/Springer DOI
was absent.** So:

- Old paper (≤2021) not on the first mirror → keep trying mirrors, it's likely there.
- New paper (2022+) → one quick check, then fall through to OA / institutional. Do not
  burn time walking mirrors for items that cannot be present.

## Preprint → published-version recovery (high value)

A DOI list item may carry a **preprint** DOI that is paywalled/awkward, while the
**published** version is gold OA under a different DOI.

Recipe:
1. Crossref bibliographic search: `query.bibliographic = "<title words> <first author>"`.
2. Look for a later, gold-OA container (MDPI journals, Frontiers, RSC Advances, etc.).
3. **Verify**: fetch the candidate DOI's metadata and confirm title + author family names match.
4. Use the published DOI for download and update the tracker.

Worked examples from this project:
- `martinezv2026`: preprint `10.20944/preprints202602.1460.v1` → published `10.3390/hydrogen7020055`.
- `buryakov2024`: preprint `10.20944/preprints202401.0928.v1` → published `10.3390/molecules29020530`
  (verified exact title + author list).

## Cloudflare / IP-flag handling

After dozens of automated requests in a session, these hosts begin returning **403 with a
~0.4 KB HTML body** (a challenge page), even from a real (headless) browser whose UA reads
`HeadlessChrome`:

- `www.mdpi.com` (gold OA) — PDF at `…/pdf`
- `www.cell.com` / Cell Press `xcrp`, `crsus` (gold OA) — `action/showPdf?pii=…`
- `www.preprints.org` (green) — PDF at `…/download`
- some institutional repos (`iris.unimore.it`, METU DSpace) — hotlink-protected

These are **genuinely open access**. Do not mark them "not found". Emit the direct link so
the user (clean IP, real browser) downloads in one click. Retrying from a flagged IP wastes
time and looks abusive.

## Publisher PDF URL patterns (when you have the landing URL)

- **MDPI**: `https://www.mdpi.com/{ISSN}/{vol}/{issue}/{article}/pdf`
- **Preprints.org**: `https://www.preprints.org/manuscript/{id}/{version}/download`
- **Springer**: `https://link.springer.com/content/pdf/{doi}.pdf` (often works via requests)
- **RSC Advances**: gold OA; Unpaywall usually gives a working `url_for_pdf`
- **De Gruyter / SciELO / E3S(EDP) / Frontiers**: usually requests-downloadable directly

## Verification & hygiene

- A real PDF starts with `%PDF` and is > 1 KB. Check magic bytes, not just HTTP 200.
- Content-type checks should be lenient: `content-type.split(';')[0] == 'application/pdf'`.
- One timestamped `downloads/<ts>/` per run; never overwrite. Name files by `citekey` when
  available, else `doi.replace('/', '_')`.
- Windows: `/` in DOIs → `_`; `:` (arxiv ids) is an illegal filename char.

## Honest reporting buckets

Always classify each item as exactly one of:
1. **downloaded** (method: open-access | sci-hub)
2. **OA link found — manual** (Cloudflare/repo blocked; link provided)
3. **paywalled — institutional access needed** (no free copy across all sources)
4. **unresolved** (no DOI; Crossref candidate failed verification)

Counts must add up to the input size. Never let bucket 2 or 3 silently read as "covered".
