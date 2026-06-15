# -*- coding: utf-8 -*-
"""Batch academic-paper retriever: Unpaywall -> Semantic Scholar -> Sci-Hub.

Usage:
    uv run python skills/academic-paper-retrieval/scripts/fetch_papers.py \
        --input dois.csv --email you@example.com

Input is either a ``citekey,doi`` CSV (header optional) or a plain text file with
one DOI per line. PDFs land in a fresh ``downloads/<timestamp>/`` folder, named by
citekey when available. A ``_report.csv`` summarises every item. Console output is
the intended user-facing progress log, so ``print`` is used deliberately here.
"""
from __future__ import annotations

import argparse
import csv
import os
import time
from datetime import datetime
from typing import Optional

import requests

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
S2_URL = ("https://api.semanticscholar.org/graph/v1/paper/DOI:%s"
          "?fields=openAccessPdf")


def load_items(path: str) -> list[tuple[str, str]]:
    """Return [(citekey, doi)]. Accepts a citekey,doi CSV or a one-DOI-per-line list."""
    items: list[tuple[str, str]] = []
    with open(path, "r", encoding="utf-8") as fh:
        rows = [ln.strip() for ln in fh if ln.strip()]
    for row in rows:
        if row.lower().startswith(("citekey", "#")):
            continue
        if "," in row:
            parts = [p.strip() for p in row.split(",")]
            citekey, doi = parts[0], parts[1]
        else:
            doi = row
            citekey = doi.replace("/", "_")
        if doi:
            items.append((citekey, doi))
    return items


def unpaywall(doi: str, email: str) -> tuple[Optional[str], list[str]]:
    """Return (oa_status, [pdf_urls]) from Unpaywall."""
    try:
        data = requests.get("https://api.unpaywall.org/v2/%s?email=%s" % (doi, email),
                            timeout=25).json()
    except (requests.RequestException, ValueError):
        return None, []
    urls = [loc["url_for_pdf"] for loc in (data.get("oa_locations") or [])
            if loc.get("url_for_pdf")]
    return data.get("oa_status"), urls


def semantic_scholar(doi: str) -> Optional[str]:
    """Return an open-access PDF URL from Semantic Scholar, if any."""
    try:
        data = requests.get(S2_URL % doi, timeout=25).json()
    except (requests.RequestException, ValueError):
        return None
    return (data.get("openAccessPdf") or {}).get("url")


def crossref_resolve(query: str, email: str) -> Optional[dict]:
    """Resolve a title/author query to the top Crossref work. VERIFY before trusting."""
    try:
        items = requests.get("https://api.crossref.org/works",
                             params={"query.bibliographic": query, "rows": 3,
                                     "mailto": email}, timeout=25).json()["message"]["items"]
    except (requests.RequestException, ValueError, KeyError):
        return None
    if not items:
        return None
    top = items[0]
    return {"doi": top.get("DOI"),
            "title": (top.get("title") or [""])[0],
            "container": (top.get("container-title") or [""])[0],
            "year": top.get("issued", {}).get("date-parts", [[None]])[0][0]}


def verify_pdf(path: str) -> bool:
    if not (os.path.exists(path) and os.path.getsize(path) > 1024):
        return False
    with open(path, "rb") as fh:
        return fh.read(4) == b"%PDF"


def http_download(urls: list[str], dest: str, ua: str) -> bool:
    """Try each URL; save the first genuine PDF response. Returns success."""
    for url in urls:
        if not url:
            continue
        if url.startswith("//"):
            url = "https:" + url
        try:
            resp = requests.get(url, timeout=70, allow_redirects=True,
                                headers={"User-Agent": ua,
                                         "Accept": "application/pdf,*/*",
                                         "Referer": url.rsplit("/", 1)[0] + "/"})
        except requests.RequestException:
            continue
        if resp.status_code == 200 and resp.content[:4] == b"%PDF":
            with open(dest, "wb") as fh:
                fh.write(resp.content)
            return True
    return False


class SciHubBackend:
    """Lazy wrapper around this repo's scihub2pdf package (headless Chrome)."""

    def __init__(self) -> None:
        self._started = False
        self._mod = None

    def fetch(self, doi: str, outdir: str) -> Optional[str]:
        try:
            from scihub2pdf import download as dl
        except ImportError:
            print("   [sci-hub] scihub2pdf not importable; run from the repo / install it")
            return None
        self._mod = dl
        if not self._started:
            print("   [sci-hub] starting headless Chrome ...")
            dl.start_scihub()
            dl.ScrapSci.driver.set_page_load_timeout(45)
            self._started = True
        try:
            dl.download_from_doi(doi, outdir, use_libgen=False)
        except Exception as exc:  # noqa: BLE001 - keep the batch alive on any backend error
            print("   [sci-hub] error:", type(exc).__name__)
            return None
        produced = os.path.join(outdir, doi.replace("/", "_") + ".pdf")
        return produced if verify_pdf(produced) else None

    def quit(self) -> None:
        if self._started and self._mod is not None:
            try:
                self._mod.ScrapSci.quit()
            except Exception:  # noqa: BLE001
                pass


def fetch_one(citekey: str, doi: str, outdir: str, email: str, ua: str,
              scihub: Optional[SciHubBackend]) -> dict:
    """Run the cascade for one DOI. Returns a result record."""
    dest = os.path.join(outdir, citekey + ".pdf")
    oa_status, urls = unpaywall(doi, email)
    s2 = semantic_scholar(doi)
    candidates = list(dict.fromkeys(urls + ([s2] if s2 else [])))

    if candidates and http_download(candidates, dest, ua) and verify_pdf(dest):
        method = "open-access"
    elif scihub is not None:
        produced = scihub.fetch(doi, outdir)
        if produced:
            if os.path.abspath(produced) != os.path.abspath(dest):
                os.replace(produced, dest)
            method = "sci-hub"
        else:
            method = "oa-link" if candidates else "paywalled"
    else:
        method = "oa-link" if candidates else "paywalled"

    size = os.path.getsize(dest) if verify_pdf(dest) else 0
    if size == 0 and method in ("open-access", "sci-hub"):
        method = "oa-link" if candidates else "paywalled"
    return {"citekey": citekey, "doi": doi, "method": method,
            "oa_status": oa_status, "bytes": size,
            "oa_link": candidates[0] if candidates else ""}


def main() -> None:
    ap = argparse.ArgumentParser(description="Batch DOI -> PDF retriever (OA + Sci-Hub).")
    ap.add_argument("--input", "-i", required=True, help="citekey,doi CSV or DOI-per-line file")
    ap.add_argument("--out", "-o", default=None, help="output folder (default downloads/<ts>)")
    ap.add_argument("--email", default="anonymous@example.com", help="Unpaywall contact email")
    ap.add_argument("--no-scihub", action="store_true", help="open access only; skip Sci-Hub")
    ap.add_argument("--user-agent", default=DEFAULT_UA)
    args = ap.parse_args()

    items = load_items(args.input)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    outdir = args.out or os.path.join("downloads", stamp)
    os.makedirs(outdir, exist_ok=True)
    print("Items: %d  ->  %s" % (len(items), os.path.abspath(outdir)))

    scihub = None if args.no_scihub else SciHubBackend()
    results = []
    for i, (citekey, doi) in enumerate(items, 1):
        print("\n[%d/%d] %s  %s" % (i, len(items), citekey, doi))
        rec = fetch_one(citekey, doi, outdir, args.email, args.user_agent, scihub)
        print("  -> %s  (%d B)  oa=%s" % (rec["method"], rec["bytes"], rec["oa_status"]))
        results.append(rec)
        time.sleep(0.4)
    if scihub is not None:
        scihub.quit()

    for name in list(os.listdir(outdir)):
        if not name.lower().endswith((".pdf", ".csv")):
            try:
                os.remove(os.path.join(outdir, name))
            except OSError:
                pass

    report = os.path.join(outdir, "_report.csv")
    with open(report, "w", encoding="utf-8", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=["citekey", "doi", "method", "oa_status",
                                            "bytes", "oa_link"])
        wr.writeheader()
        wr.writerows(results)

    got = [r for r in results if r["method"] in ("open-access", "sci-hub")]
    links = [r for r in results if r["method"] == "oa-link"]
    pay = [r for r in results if r["method"] == "paywalled"]
    print("\n==== SUMMARY ====")
    print("downloaded: %d | oa-link (manual): %d | paywalled: %d | total: %d"
          % (len(got), len(links), len(pay), len(items)))
    print("report:", os.path.abspath(report))
    for r in links:
        print("  manual:", r["citekey"], r["oa_link"])


if __name__ == "__main__":
    main()
