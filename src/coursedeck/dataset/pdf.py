"""PDF inspection and page-range extraction (PyMuPDF)."""

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import pymupdf

# MIT OCW marks third-party material with this notice; such documents are dropped.
THIRD_PARTY_RE = re.compile(r"excluded from our\s+creative\s+commons\s+license", re.IGNORECASE)

MATH_RE = re.compile(r"[∑∫∂√≤≥≠≈∞±×÷∈∀∃→⇒αβγδεθλμπσφωΔΣΩ]|\\(?:frac|sum|int)\b")
UK_RE = re.compile(r"[іїєґ]", re.IGNORECASE)
RU_RE = re.compile(r"[ыэъё]", re.IGNORECASE)
LATIN_RE = re.compile(r"[a-z]", re.IGNORECASE)
CYR_RE = re.compile(r"[а-яіїєґ]", re.IGNORECASE)

MIN_CHARS_PER_PAGE = 50  # below this a page is treated as having no usable text layer


@dataclass
class PdfInfo:
    n_pages: int
    text_layer: str  # full | partial | none (none = most pages have no text, i.e. a scan)
    chars_per_page: float
    pages_without_text: int
    landscape_ratio: float  # share of landscape pages; high -> slides
    math_symbols: int
    lang_guess: str  # en | uk | ru | unknown
    third_party: bool
    encrypted: bool
    fingerprint: str  # hash of the normalized leading text, used to drop duplicates

    def to_dict(self) -> dict:
        return asdict(self)


def guess_lang(text: str) -> str:
    latin, cyr = len(LATIN_RE.findall(text)), len(CYR_RE.findall(text))
    if latin + cyr < 200:
        return "unknown"
    if latin > cyr:
        return "en"
    return "uk" if len(UK_RE.findall(text)) >= len(RU_RE.findall(text)) else "ru"


def page_texts(doc: pymupdf.Document, start: int = 1, end: int | None = None) -> list[str]:
    end = end or doc.page_count
    return [doc[i].get_text() for i in range(start - 1, end)]


def inspect_pdf(path: Path, start: int = 1, end: int | None = None) -> PdfInfo:
    """Inspect pages [start, end] (1-based, inclusive) of a PDF."""
    with pymupdf.open(path) as doc:
        end = end or doc.page_count
        texts = page_texts(doc, start, end)
        pages = [doc[i] for i in range(start - 1, end)]
        landscape = sum(p.rect.width > p.rect.height for p in pages)
        full = "\n".join(texts)
        empty = sum(len(t.strip()) < MIN_CHARS_PER_PAGE for t in texts)
        n = len(texts)
        return PdfInfo(
            n_pages=n,
            text_layer="none" if empty > n / 2 else ("partial" if empty else "full"),
            chars_per_page=round(len(full) / max(n, 1), 1),
            pages_without_text=empty,
            landscape_ratio=round(landscape / max(n, 1), 2),
            math_symbols=len(MATH_RE.findall(full)),
            lang_guess=guess_lang(full),
            third_party=bool(THIRD_PARTY_RE.search(full)),
            encrypted=doc.is_encrypted,
            fingerprint=fingerprint(full),
        )


def fingerprint(text: str, n_chars: int = 2000) -> str:
    norm = re.sub(r"\W+", "", text.lower())[:n_chars]
    return hashlib.sha1(norm.encode()).hexdigest() if norm else ""


PageRanges = list[tuple[int, int]]  # 1-based, inclusive


def parse_pages(spec: str) -> PageRanges:
    """'1-3,6-29' -> [(1, 3), (6, 29)]; '5' -> [(5, 5)]."""
    ranges = []
    for part in spec.split(","):
        start, _, end = part.strip().partition("-")
        ranges.append((int(start), int(end or start)))
    return ranges


def format_pages(ranges: PageRanges) -> str:
    return ",".join(f"{s}-{e}" if e != s else str(s) for s, e in ranges)


def to_ranges(pages: list[int]) -> PageRanges:
    """[1, 2, 3, 7] -> [(1, 3), (7, 7)]."""
    ranges: PageRanges = []
    for p in sorted(pages):
        if ranges and p == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], p)
        else:
            ranges.append((p, p))
    return ranges


def extract_pages(src: Path, dst: Path, ranges: PageRanges) -> None:
    """Write the given page ranges of `src`, in order, into a new PDF `dst`."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(src) as doc, pymupdf.open() as out:
        for start, end in ranges:
            out.insert_pdf(doc, from_page=start - 1, to_page=end - 1)
        out.save(dst, garbage=4, deflate=True)
