"""Dataset manifest: one CSV row per lecture document.

A row points to a source PDF (`pdf_url`) and the pages taken from it (`pages`, 1-based
inclusive ranges). A lecture cut out of a course book keeps the book's title pages in front,
e.g. "1-3,30-37", so the document still shows its course, authors, institution and year.
`source_sha256` is the hash of the downloaded source file, so fetching is verifiable.
"""

import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from coursedeck.dataset.pdf import PageRanges, parse_pages

PDF_DIR = Path("data/pdfs")  # committed core set
EXTRA_PDF_DIR = Path("data/pdfs_extra")  # fetched by manifest, not committed


@dataclass
class ManifestRow:
    doc_id: str
    lang: str  # en | uk
    source: str  # ocw | zenodo
    license: str
    course_id: str
    course_title: str
    department: str
    lecture_title: str
    source_url: str  # human-readable landing page (attribution)
    pdf_url: str
    source_sha256: str
    pages: str  # page ranges taken from the source PDF, e.g. "1-3,30-37"
    n_pages: int  # pages in the resulting document
    text_layer: str  # full | partial | none
    layout: str  # notes | slides
    math_heavy: bool
    in_repo: bool  # True -> stored in data/pdfs, else fetched into data/pdfs_extra
    golden: bool
    tier: int  # smallest manifest size the row belongs to: 50 | 100 | 200 | 500

    @property
    def path(self) -> Path:
        return (PDF_DIR if self.in_repo else EXTRA_PDF_DIR) / f"{self.doc_id}.pdf"

    @property
    def page_ranges(self) -> PageRanges:
        return parse_pages(self.pages)


FIELDS = [f.name for f in fields(ManifestRow)]
_INT = {"n_pages", "tier"}
_BOOL = {"math_heavy", "in_repo", "golden"}


def _parse(raw: dict[str, str]) -> ManifestRow:
    kw: dict = dict(raw)
    for k in _INT:
        kw[k] = int(raw[k])
    for k in _BOOL:
        kw[k] = raw[k].strip().lower() == "true"
    return ManifestRow(**kw)


def read_manifest(path: Path) -> list[ManifestRow]:
    with path.open(encoding="utf-8", newline="") as f:
        return [_parse(r) for r in csv.DictReader(f)]


def write_manifest(path: Path, rows: list[ManifestRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))
