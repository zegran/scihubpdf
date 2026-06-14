# SciHub to PDF

Downloads PDFs by DOI, article title, arXiv id, or a BibTeX file, using
**Sci-Hub**, **Libgen**, and **arXiv**.

> Modernized fork of [bibcure/scihub2pdf](https://github.com/bibcure/scihub2pdf),
> updated to run on a current Python / Selenium stack:
>
> - The Sci-Hub backend now drives **headless Google Chrome via Selenium 4**.
>   The original `PhantomJS` backend no longer works (PhantomJS was removed
>   from Selenium 4).
> - **Multiple Sci-Hub mirrors** are tried in order, skipping unreachable ones.
> - Installs cleanly on Windows with a real `scihub2pdf` command.

## Requirements

- Python 3.8+
- Google Chrome — only for the Sci-Hub backend. Selenium Manager downloads a
  matching driver automatically, so you do **not** need PhantomJS or a manual
  `chromedriver`.

## Install

Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
git clone https://github.com/zegran/scihubpdf.git
cd scihubpdf
uv venv
uv pip install -e .
```

Or with pip:

```bash
git clone https://github.com/zegran/scihubpdf.git
cd scihubpdf
pip install -e .
```

## Usage

Inside an activated virtualenv use `scihub2pdf ...`; with uv you can also run
`uv run scihub2pdf ...`.

Given a BibTeX file:
```bash
scihub2pdf -i input.bib
```

Given a DOI:
```bash
scihub2pdf 10.1038/s41524-017-0032-0
```

Given a title:
```bash
scihub2pdf --title An useful paper
```

arXiv:
```bash
scihub2pdf arxiv:0901.2686
scihub2pdf --title arxiv:Periodic table for topological insulators
```

Output folder (note: `-l` is a folder **prefix**, not a file path):
```bash
scihub2pdf -i input.bib -l somefolder/
```

Use Libgen instead of Sci-Hub:
```bash
scihub2pdf -i input.bib --uselibgen
```

## Sci-Hub mirrors

The Sci-Hub backend tries these mirrors in order, skips any that are
unreachable, and stops at the first one that actually serves the PDF:

`sci-hub.st` → `sci-hub.ist` → `sci-hub.ru` → `sci-hub.se`

Override the list (a single mirror or a comma-separated list) with the
`SCIHUB_MIRROR` environment variable:

```powershell
# Windows PowerShell
$env:SCIHUB_MIRROR="https://sci-hub.ist/,https://sci-hub.st/"
scihub2pdf 10.1016/j.cell.2017.05.016 -l papers/
```

```bash
# Linux / macOS
SCIHUB_MIRROR="https://sci-hub.ist/" scihub2pdf 10.1016/j.cell.2017.05.016 -l papers/
```

## Download from a list of items

DOIs (`dois.txt`):
```
10.1038/s41524-017-0032-0
10.1063/1.3149495
```
```bash
scihub2pdf -i dois.txt --txt
```

Titles (`titles.txt`):
```
Some Title 1
Some Title 2
```
```bash
scihub2pdf -i titles.txt --txt --title
```

arXiv ids (`arxiv_ids.txt`):
```
arXiv:1708.06891
arXiv:1708.06071
```
```bash
scihub2pdf -i arxiv_ids.txt --txt
```

## Backend comparison

| Backend | Browser needed   | Notes                                          |
|---------|------------------|------------------------------------------------|
| Sci-Hub | Headless Chrome  | Tries multiple mirrors; best coverage          |
| Libgen  | No               | `--uselibgen`; depends on Libgen availability   |
| arXiv   | No               | Open access; always works for arXiv ids        |

## Windows note

If printing a non-ASCII title/DOI triggers a `cp1252` encoding error, set
UTF-8 output first:

```powershell
$env:PYTHONIOENCODING="utf-8"
```

## License

AGPLv3, inherited from the upstream project. See [LICENSE](LICENSE).
