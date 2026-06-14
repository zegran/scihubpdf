# -*- coding: utf-8 -*-
"""Importable console entry point for scihub2pdf.

This mirrors the logic of ``scihub2pdf/bin/scihub2pdf`` but lives in an
importable module so a ``console_scripts`` entry point can generate a proper
``scihub2pdf`` executable (including ``scihub2pdf.exe`` on Windows).
"""
from __future__ import unicode_literals, print_function, absolute_import
import os
import sys
import re
import io
import textwrap
import argparse
from datetime import datetime

import bibtexparser
from unidecode import unidecode  # noqa: F401  (kept for parity with original script)

from scihub2pdf.download import (download_from_doi,
                                 download_from_title, download_from_arxiv,
                                 start_scihub, start_libgen, start_arxiv,
                                 download_pdf_from_bibs)

pyversion = sys.version_info[0]


def make_session_location(base, no_session_dir=False):
    """Return the download-location prefix for this run.

    By default every run gets its own timestamped subfolder under ``base``
    (the current directory when ``base`` is empty), so PDFs from different
    sessions stay separated. The returned value ends with a path separator so
    it can be concatenated with a file name. Pass ``no_session_dir=True`` to
    write straight into ``base`` (the legacy behaviour).
    """
    base = base or ""
    if no_session_dir:
        return base
    session = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    location = os.path.join(base if base else ".", session) + os.sep
    os.makedirs(location, exist_ok=True)
    print("\tSaving PDFs to:", location)
    return location


def main():
    parser = argparse.ArgumentParser(
        prog="scihub2pdf",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent('''\
        SciHub to PDF
        ----------------------------------------------------
        Downloads pdfs via a DOI number, article title
        or a bibtex file, using the database of libgen(sci-hub).

        Given a bibtex file

        $ scihub2pdf -i input.bib

        Given a DOI number...

        $ scihub2pdf 10.1038/s41524-017-0032-0

        Given a title...

        $ scihub2pdf --title An useful paper

        Arxiv...

        $ scihub2pdf arxiv:0901.2686

        $ scihub2pdf --title arxiv:Periodic table for topological insulators
        ''')
    )
    parser.add_argument("--input", "-i", dest="inputfile",
                        help="bibtex input file")
    parser.add_argument("--title", "-t", dest="title", action="store_true",
                        help="download from title")
    parser.add_argument("--uselibgen", dest="uselibgen", action="store_true",
                        help="Use libgen.io instead sci-hub.")
    parser.add_argument("--location", "-l", help="base folder, ex: -l 'folder/'")
    parser.add_argument("--txt", action="store_true",
                        help="Just create a file with DOI's or titles")
    parser.add_argument("--no-session-dir", dest="no_session_dir",
                        action="store_true",
                        help="Do not create a per-run timestamped subfolder")

    parser.set_defaults(title=False)
    parser.set_defaults(uselibgen=False)
    parser.set_defaults(txt=False)
    parser.set_defaults(no_session_dir=False)
    parser.set_defaults(location="")

    args = parser.parse_known_args()
    title_search = args[0].title
    is_txt = args[0].txt
    use_libgen = args[0].uselibgen
    inline_search = len(args[1]) > 0
    location = make_session_location(args[0].location, args[0].no_session_dir)

    if use_libgen:
        start_libgen()
        print("\n\t Using Libgen.\n")
    else:
        start_scihub()
        print("\n\t Using Sci-Hub.\n")

    start_arxiv()

    if inline_search:
        values = [c if pyversion == 3 else c.decode(sys.stdout.encoding)
                  for c in args[1]]
        value = " ".join(values)
        is_arxiv = bool(re.match("arxiv:", value, re.I))
        if is_arxiv:
            field = "ti" if title_search else "id"
            download_from_arxiv(value, location, field)
        elif title_search:
            download_from_title(value, location, use_libgen)
        else:
            download_from_doi(value, location, use_libgen)
    else:
        if is_txt:
            with io.open(args[0].inputfile, "r", encoding="utf-8") as inputfile:
                file_values = inputfile.read()

            for value in file_values.split("\n"):
                is_arxiv = bool(re.match("arxiv:", value, re.I))
                if value != "":
                    if is_arxiv:
                        field = "ti" if title_search else "id"
                        download_from_arxiv(value, field, location)
                    elif title_search:
                        download_from_title(value, location, use_libgen)
                    else:
                        download_from_doi(value, location, use_libgen)
        else:
            dict_parser = {
                'keywords': 'keyword',
                'keyw': 'keyword',
                'subjects': 'subject',
                'urls': 'url',
                'link': 'url',
                'links': 'url',
                'editors': 'editor',
                'authors': 'author'}
            parser = bibtexparser.bparser.BibTexParser()
            parser.alt_dict = dict_parser
            with io.open(args[0].inputfile, "r", encoding="utf-8") as inputfile:
                refs_string = inputfile.read()

            bibtex = bibtexparser.loads(refs_string, parser=parser)
            bibs = bibtex.entries
            if len(bibs) == 0:
                print("Input File is empty or corrupted.")
                sys.exit(1)

            download_pdf_from_bibs(bibs, location, use_libgen)


if __name__ == "__main__":
    main()
