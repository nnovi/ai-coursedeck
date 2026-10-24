"""Page text layers and page images sized to the smallest text on the page.

Image tokens grow with pixels (Claude: about width*height/750 tokens per image), so each page
is rendered just large enough for its smallest body text to be legible instead of at a fixed
DPI. Pages without a text layer (scans) get the full pixel budget.
"""

from dataclasses import dataclass
from pathlib import Path

import pymupdf

TARGET_FONT_PX = 14.0  # rendered height of the smallest body text
MIN_FONT_PT = 4.0  # ignore stray tiny glyphs (rules, dots, superscripts)
MIN_ZOOM = 0.75  # never shrink pages below 54 DPI
MAX_LONG_EDGE_PX = 1568  # Claude downsizes larger images; extra pixels only cost upload time


@dataclass
class Page:
    number: int  # 1-based
    text: str
    image: bytes | None = None  # PNG
    zoom: float | None = None
    width_px: int = 0
    height_px: int = 0


def smallest_font_pt(page: pymupdf.Page) -> float | None:
    """Font size at the 5th percentile of characters, or None for pages without text."""
    sizes: list[tuple[float, int]] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                n = len(span["text"].strip())
                if n >= 3 and span["size"] >= MIN_FONT_PT:
                    sizes.append((span["size"], n))
    if not sizes:
        return None
    sizes.sort()
    total, seen = sum(n for _, n in sizes), 0
    for size, n in sizes:
        seen += n
        if seen >= 0.05 * total:
            return size
    return sizes[-1][0]


def page_zoom(page: pymupdf.Page) -> float:
    max_zoom = MAX_LONG_EDGE_PX / max(page.rect.width, page.rect.height)
    font = smallest_font_pt(page)
    if font is None:
        return max_zoom
    return min(max(TARGET_FONT_PX / font, MIN_ZOOM), max_zoom)


def load_pages(path: Path, with_images: bool) -> list[Page]:
    pages = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, 1):
            p = Page(number=i, text=page.get_text().strip())
            if with_images:
                p.zoom = page_zoom(page)
                pix = page.get_pixmap(matrix=pymupdf.Matrix(p.zoom, p.zoom))
                p.image, p.width_px, p.height_px = pix.tobytes("png"), pix.width, pix.height
            pages.append(p)
    return pages
