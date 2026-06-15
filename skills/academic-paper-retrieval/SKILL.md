---
name: academic-paper-retrieval
description: This skill should be used when the user asks to "download papers from this DOI list", "fetch full-text PDFs", "fill a literature-review gap", "batch download papers", "find an open-access copy for a DOI", or "resolve missing papers". It runs a multi-source cascade (Unpaywall and Semantic Scholar open access, then Sci-Hub via this repo's scihub2pdf) into a timestamped session folder, verifies each PDF, and writes a report.
---

# Academic Paper Retrieval

Retrieve full-text PDFs for a list of DOIs at scale, preferring legal open access
and falling back to Sci-Hub, with honest reporting of what could not be obtained.

## When to use

- A DOI list (or `citekey,doi` CSV) needs to be turned into PDFs.
- A literature-review corpus has gaps to fill ("still missing", "OA candidates").
- One DOI needs its best available copy located.

## When NOT to use

- Bypassing paywalls beyond what Sci-Hub / open access already provide.
- Solving captchas or defeating bot protection (Cloudflare). Those items are
  reported as "open access — download in a browser", with the direct link.
- Non-academic file downloads.

## The retrieval cascade (per DOI)

Try in this order; stop at the first real PDF (`%PDF` header, > 1 KB):

1. **Unpaywall** — `api.unpaywall.org/v2/{doi}?email=` → every `oa_locations[].url_for_pdf`.
2. **Semantic Scholar** — `…/graph/v1/paper/DOI:{doi}?fields=openAccessPdf` → `openAccessPdf.url`
   (catches green/repository copies Unpaywall misses).
3. **Sci-Hub** — this repo's `scihub2pdf` (multi-mirror headless Chrome).
   Reliable only for **papers up to ~2021** (Sci-Hub paused new uploads).
4. **Manual / browser** — for OA items blocked by Cloudflare (MDPI, Cell Press,
   Preprints.org) or rate-limited IPs. Report the direct link instead of failing silently.

Run it: `uv run python skills/academic-paper-retrieval/scripts/fetch_papers.py --input dois.csv`
(`--no-scihub` for OA-only; `--email you@example.com` for Unpaywall).

## Hard-won rules (see references/retrieval-playbook.md for detail)

- **Sci-Hub coverage stops ~2021.** 2022+ Elsevier/Springer are almost never there;
  do not keep retrying — fall through to OA / institutional access.
- **Preprint ≠ dead end.** A "missing" preprint DOI (Preprints.org `10.20944/…`, SSRN)
  often has a **published gold-OA version** under a different DOI. Resolve it via a
  Crossref title+author search, then **verify** the title/authors before trusting it.
- **Cloudflare / IP flag.** After many automated requests, MDPI / Cell Press / Preprints
  start returning 403 to scripts. The papers are still OA — hand the user the direct link
  (`mdpi.com/.../pdf`, `preprints.org/.../download`) rather than declaring them missing.
- **Always verify.** Check the `%PDF` magic bytes and size; a 403 HTML page is ~0.4 KB.
- **Report honestly.** Separate "downloaded", "OA link found (manual)", and "paywalled —
  needs institutional access". Never imply coverage that was not achieved.

## Boundaries

- Output goes to a fresh `downloads/<timestamp>/` folder; existing files are never overwritten.
- Sci-Hub usage is the user's decision; this skill only automates a tool they installed.
- Legality of Sci-Hub/LibGen access varies by jurisdiction — surface this, don't assume.

## Additional resources

- `scripts/fetch_papers.py` — the executable cascade (Unpaywall → S2 → Sci-Hub) with
  session folders, `%PDF` verification, Crossref resolution, and a CSV report.
- `references/retrieval-playbook.md` — per-source coverage notes, publisher URL patterns,
  Cloudflare handling, and the preprint→published recovery recipe.
