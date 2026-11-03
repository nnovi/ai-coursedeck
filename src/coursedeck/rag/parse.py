"""Parsers: PDF, HTML, DOCX, PPTX -> ParsedDoc (headings, paragraphs, list items, tables).

Every parser keeps the document structure the chunker needs and applies the cleaning rules
from coursedeck.rag.clean; what it removes is counted in ParsedDoc.dropped.
"""

import re
from collections import Counter
from pathlib import Path

import pymupdf
from bs4 import BeautifulSoup, NavigableString, Tag
from docx import Document as DocxDocument
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER

from coursedeck.rag.blocks import Block, ParsedDoc, md_table
from coursedeck.rag.clean import (
    BULLET_RE,
    LICENSE_PAGE_MAX_CHARS,
    LICENSE_PAGE_RE,
    NUMBERED_RE,
    PAGE_NUMBER_RE,
    is_boilerplate,
    join_lines,
    margin_key,
    normalize,
    repeated,
    squash,
)

# Lines that open a lecture/topic/section regardless of font: "Лекція 3", "ТЕМА 1.", "Lecture 12"
HEADING_RE = re.compile(
    r"^(?:лекція|тема|розділ|частина|lecture|chapter|section|part|unit|topic)\s*(?:№\s*)?"
    r"(?:\d+|[IVXLC]+)\b", re.IGNORECASE)
MAX_HEADING_CHARS = 120


def parse(path: Path, fmt: str) -> ParsedDoc:
    return {"pdf": parse_pdf, "html": parse_html, "docx": parse_docx, "pptx": parse_pptx}[fmt](path)


# --------------------------------------------------------------------------------------- PDF

MARGIN = 0.08  # top/bottom share of the page where running headers and footers live


def _pdf_lines(page: pymupdf.Page, skip: list[pymupdf.Rect]) -> list[list[dict]]:
    """Text blocks of a page as lists of lines {text, size, bold, y0, y1}, minus table areas."""
    out = []
    for b in page.get_text("dict", sort=True)["blocks"]:
        if b["type"] != 0 or any(pymupdf.Rect(b["bbox"]).intersects(r) for r in skip):
            continue
        lines = []
        for ln in b["lines"]:
            spans = [s for s in ln["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = normalize("".join(s["text"] for s in ln["spans"]))
            chars = sum(len(s["text"].strip()) for s in spans)
            lines.append({
                "text": text,
                "size": round(max(s["size"] for s in spans) * 2) / 2,
                "bold": sum(len(s["text"].strip()) for s in spans if s["flags"] & 16
                            or "bold" in s["font"].lower()) >= 0.8 * chars,
                "y0": ln["bbox"][1], "y1": ln["bbox"][3],
            })
        if lines:
            out.append(lines)
    return out


def _pdf_tables(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, str, str]]:
    try:
        found = page.find_tables().tables
    except Exception:  # noqa: BLE001 - table detection is best effort
        return []
    tables = []
    for t in found:
        rows = [[normalize(c or "") for c in r] for r in t.extract()]
        if len(rows) < 2 or max(len(r) for r in rows) < 2:
            continue
        md, header = md_table(rows)
        if md:
            tables.append((pymupdf.Rect(t.bbox), md, header))
    return tables


def _is_heading(line: dict, n_lines: int, body: float) -> bool:
    text = squash(line["text"])
    if not re.search(r"\w", text) or len(text) > MAX_HEADING_CHARS:
        return False
    if HEADING_RE.match(text):
        return True
    if line["size"] >= body * 1.15:
        return True
    # bold body-size line standing alone (or a short bold first line) that is not a sentence
    return line["bold"] and n_lines <= 3 and not text.endswith((".", ",", ";")) and len(text) > 2


def parse_pdf(path: Path) -> ParsedDoc:
    dropped: Counter = Counter()
    with pymupdf.open(path) as doc:
        pages = []
        for page in doc:
            text = page.get_text()
            if LICENSE_PAGE_RE.search(text) and len(text) < LICENSE_PAGE_MAX_CHARS:
                dropped["license_page"] += 1
                continue
            tables = _pdf_tables(page)
            pages.append((page.number + 1, page.rect.height, tables,
                          _pdf_lines(page, [r for r, _, _ in tables])))
        title = normalize(doc.metadata.get("title") or "")
        meta = {"n_pages": doc.page_count, "created": doc.metadata.get("creationDate", "")}

    # running headers/footers: lines in the page margins that repeat across pages
    def margin_keys(height, blocks):
        return {margin_key(ln["text"]) for lines in blocks for ln in lines
                if ln["y1"] < height * MARGIN or ln["y0"] > height * (1 - MARGIN)}

    running = repeated([margin_keys(h, bl) for _, h, _, bl in pages])
    sizes = Counter()
    for *_, blocks in pages:
        for lines in blocks:
            for ln in lines:
                sizes[ln["size"]] += len(ln["text"])
    body = sizes.most_common(1)[0][0] if sizes else 10.0
    big = sorted({s for s in sizes if s >= body * 1.15}, reverse=True)
    level_of = {s: min(i + 1, 3) for i, s in enumerate(big)}

    out: list[Block] = []
    for page_no, height, tables, blocks in pages:
        items: list[tuple[float, Block]] = [(r.y0, Block("table", md, page=page_no, header=hd))
                                            for r, md, hd in tables]
        for lines in blocks:
            kept = []
            for ln in lines:
                in_margin = ln["y1"] < height * MARGIN or ln["y0"] > height * (1 - MARGIN)
                if in_margin and margin_key(ln["text"]) in running:
                    dropped["running_header_footer"] += 1
                elif in_margin and PAGE_NUMBER_RE.match(ln["text"]):
                    dropped["page_number"] += 1
                elif is_boilerplate(ln["text"]):
                    dropped["boilerplate"] += 1
                else:
                    kept.append(ln)
            items += [(ln_y, b) for ln_y, b in _pdf_block(kept, page_no, body, level_of)]
        out += [b for _, b in sorted(items, key=lambda x: x[0])]
    return ParsedDoc(_join_page_breaks(_merge_headings(out)), title=title, meta=meta,
                     dropped=dict(dropped))


def _pdf_block(lines: list[dict], page_no: int, body: float, level_of: dict) -> list:
    """One PyMuPDF text block -> headings, list items and paragraphs (with their y position)."""
    out, buf, kind, y = [], [], "paragraph", 0.0

    def flush():
        nonlocal buf
        text = join_lines(buf)
        if text:
            out.append((y, Block(kind, text, page=page_no)))
        buf = []

    for ln in lines:
        text = squash(ln["text"])
        if _is_heading(ln, len(lines), body):
            flush()
            level = 1 if HEADING_RE.match(text) else level_of.get(ln["size"], len(level_of) + 1)
            out.append((ln["y0"], Block("heading", text, level=min(level, 4), page=page_no)))
            kind = "paragraph"
            continue
        bullet = BULLET_RE.match(text) or NUMBERED_RE.match(text)
        if bullet:
            flush()
            kind, y = "list_item", ln["y0"]
            buf = [text[bullet.end():] if BULLET_RE.match(text) else text]
            continue
        if not buf:
            y = ln["y0"]
        buf.append(text)
    flush()
    return out


def _merge_headings(blocks: list[Block]) -> list[Block]:
    """A heading wrapped over two lines arrives as two headings of the same level: join them."""
    out: list[Block] = []
    for b in blocks:
        prev = out[-1] if out else None
        if (b.kind == "heading" and prev and prev.kind == "heading" and prev.level == b.level
                and prev.page == b.page and not HEADING_RE.match(b.text)
                and (len(prev.text) + len(b.text) <= MAX_HEADING_CHARS or b.text[0].islower())):
            prev.text = join_lines([prev.text, b.text])
        else:
            out.append(b)
    return out


def _join_page_breaks(blocks: list[Block]) -> list[Block]:
    """A paragraph cut by a page break continues on the next page with a lowercase letter:
    glue it back (undoing the hyphen of a word split across pages)."""
    out: list[Block] = []
    for b in blocks:
        prev = out[-1] if out else None
        if (prev and b.kind == "paragraph" and prev.kind in {"paragraph", "list_item"}
                and prev.page != b.page and b.text[:1].islower()
                and not prev.text.endswith((".", "!", "?", ":"))):
            prev.text = join_lines([prev.text, b.text])
        else:
            out.append(b)
    return out


# -------------------------------------------------------------------------------------- HTML

# Tags that never hold page content, and class/id fragments of navigation chrome.
HTML_DROP_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form",
                  "button", "svg", "iframe", "template"]
HTML_CHROME_RE = re.compile(r"nav|menu|breadcrumb|footer|header|cookie|banner|sidebar|modal|"
                            r"social|share|skip|toolbar|drawer|icon", re.IGNORECASE)
HTML_BLOCK_TAGS = {"p", "li", "table", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote",
                   "dd", "dt"}


def html_content_root(soup: BeautifulSoup) -> Tag:
    """Main content element. OCW pages keep it in <main id="course-content-section">; elsewhere
    <main>/<article>, or the <body> without navigation chrome."""
    for sel in ["main#course-content-section", "main", "article", "[role=main]", "body"]:
        node = soup.select_one(sel)
        if node and node.get_text(strip=True):
            return node
    return soup


def _cell_text(cell: Tag) -> str:
    parts = [squash(normalize(p.get_text(" "))) for p in cell.find_all(["p", "li"])]
    return " / ".join(p for p in parts if p) or squash(normalize(cell.get_text(" ")))


def _html_table(table: Tag) -> Block | None:
    rows, n_header = [], 0
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        rows.append([_cell_text(c) for c in cells])
        if all(c.name == "th" for c in cells) and len(rows) == n_header + 1:
            n_header += 1
    md, header = md_table(rows, n_header or 1)
    return Block("table", md, header=header) if md else None


def parse_html(path: Path) -> ParsedDoc:
    soup = BeautifulSoup(path.read_bytes(), "lxml")  # encoding from <meta charset> or sniffed
    title = squash(normalize(soup.title.get_text())) if soup.title else ""
    meta = {m.get("name") or m.get("property"): m.get("content") for m in soup.find_all("meta")
            if (m.get("name") or m.get("property")) and m.get("content")}
    root = html_content_root(soup)
    dropped: Counter = Counter()
    for tag in root.find_all(HTML_DROP_TAGS):
        dropped["html_chrome_tag"] += 1
        tag.decompose()
    for tag in root.find_all(True):
        if tag.decomposed:
            continue
        marker = " ".join(tag.get("class") or []) + " " + (tag.get("id") or "")
        if tag.name not in {"main", "body", "table", "tr", "td", "th"} and HTML_CHROME_RE.search(marker):
            dropped["html_chrome_class"] += 1
            tag.decompose()

    blocks: list[Block] = []

    def walk(node: Tag, depth: int) -> None:
        loose: list[str] = []  # inline text directly inside a container (div with text, etc.)

        def flush_loose():
            text = squash(normalize(" ".join(loose)))
            if text and not is_boilerplate(text):
                blocks.append(Block("paragraph", text))
            loose.clear()

        for child in node.children:
            if isinstance(child, NavigableString):
                if child.strip() and child.__class__ is NavigableString:
                    loose.append(str(child))
                continue
            if not isinstance(child, Tag):
                continue
            name = child.name
            if name not in HTML_BLOCK_TAGS and not child.find(list(HTML_BLOCK_TAGS) + ["ul", "ol"]):
                loose.append(child.get_text(" "))  # inline element: a, em, strong, span ...
                continue
            flush_loose()
            if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                text = squash(normalize(child.get_text(" ")))
                if text:
                    blocks.append(Block("heading", text, level=int(name[1])))
            elif name == "table":
                if (b := _html_table(child)) is not None:
                    blocks.append(b)
            elif name in {"ul", "ol"}:
                walk(child, depth + 1)
            elif name == "li":
                nested = child.find_all(["ul", "ol"], recursive=False)
                for n in nested:
                    n.extract()
                text = squash(normalize(child.get_text(" ")))
                if text:
                    blocks.append(Block("list_item", text, level=max(depth - 1, 0)))
                for n in nested:
                    walk(n, depth + 1)
            elif name in {"p", "pre", "blockquote", "dd", "dt"}:
                text = squash(normalize(child.get_text(" ")))
                if text and not is_boilerplate(text):
                    blocks.append(Block("paragraph", text))
            else:
                walk(child, depth)
        flush_loose()

    walk(root, 0)
    blocks, n = _drop_repeated_sections(blocks)
    if n:
        dropped["repeated_section"] = n
    return ParsedDoc(blocks, title=title, meta=meta, dropped=dict(dropped))


def _drop_repeated_sections(blocks: list[Block]) -> tuple[list[Block], int]:
    """Page templates often render a block twice (mobile and desktop variants of "Course
    Info"). A section whose heading was seen before and whose blocks are mostly repeats of
    earlier blocks is dropped."""
    sections: list[list[Block]] = [[]]
    for b in blocks:
        if b.kind == "heading":
            sections.append([])
        sections[-1].append(b)
    seen_heads, seen_texts, out, n = set(), set(), [], 0
    for sec in sections:
        head = (sec[0].level, sec[0].text) if sec and sec[0].kind == "heading" else None
        body = [b.text for b in sec[1:]] if head else [b.text for b in sec]
        if head in seen_heads and sum(t in seen_texts for t in body) >= 0.7 * len(body):
            n += 1
            continue
        if head:
            seen_heads.add(head)
        seen_texts.update(body)
        out += sec
    return out, n


# -------------------------------------------------------------------------------------- DOCX

DOCX_HEADING_RE = re.compile(r"^(?:heading|заголовок)\s*(\d)$", re.IGNORECASE)


def _docx_items(doc):
    """Paragraphs and tables of the body in document order."""
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield DocxParagraph(child, doc)
        elif tag == "tbl":
            yield DocxTable(child, doc)


def parse_docx(path: Path) -> ParsedDoc:
    doc = DocxDocument(str(path))
    blocks: list[Block] = []
    dropped: Counter = Counter()
    for item in _docx_items(doc):
        if isinstance(item, DocxTable):
            rows = [[normalize(c.text) for c in r.cells] for r in item.rows]
            md, header = md_table(rows)
            if md:
                blocks.append(Block("table", md, header=header))
            continue
        text = squash(normalize(item.text))
        if not text:
            continue
        if is_boilerplate(text):
            dropped["boilerplate"] += 1
            continue
        style = (item.style.name if item.style is not None else "") or ""
        m = DOCX_HEADING_RE.match(style)
        runs = [r for r in item.runs if r.text.strip()]
        all_bold = bool(runs) and all(r.bold or (r.style is not None and r.style.font.bold)
                                      for r in runs)
        numbered = item._p.pPr is not None and item._p.pPr.numPr is not None
        if m or style.lower() == "title":
            blocks.append(Block("heading", text, level=int(m.group(1)) if m else 1))
        elif HEADING_RE.match(text) and len(text) <= MAX_HEADING_CHARS:
            blocks.append(Block("heading", text, level=1))
        elif all_bold and len(text) <= MAX_HEADING_CHARS and not text.endswith((".", ",", ";")):
            blocks.append(Block("heading", text, level=3))
        elif numbered or "list" in style.lower() or BULLET_RE.match(text):
            level = 0
            if numbered and item._p.pPr.numPr.ilvl is not None:
                level = int(item._p.pPr.numPr.ilvl.val)
            blocks.append(Block("list_item", BULLET_RE.sub("", text), level=level))
        else:
            blocks.append(Block("paragraph", text))
    props = doc.core_properties
    meta = {"created": props.created.isoformat() if props.created else "",
            "modified": props.modified.isoformat() if props.modified else "",
            "author": props.author or ""}
    return ParsedDoc(blocks, title=normalize(props.title or ""), meta=meta, dropped=dict(dropped))


# -------------------------------------------------------------------------------------- PPTX

PPTX_SKIP_PLACEHOLDERS = {PP_PLACEHOLDER.FOOTER, PP_PLACEHOLDER.SLIDE_NUMBER, PP_PLACEHOLDER.DATE}
PPTX_TITLE_PLACEHOLDERS = {PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE}
PPTX_MIN_LABEL_CHARS = 2


def _pptx_shapes(shapes):
    """Shapes in reading order (top-to-bottom, left-to-right), groups flattened."""
    flat = []
    for s in shapes:
        if s.shape_type == MSO_SHAPE_TYPE.GROUP:
            flat += _pptx_shapes(s.shapes)
        else:
            flat.append(s)
    return sorted(flat, key=lambda s: ((s.top or 0) // 100000, s.left or 0))


def parse_pptx(path: Path) -> ParsedDoc:
    prs = Presentation(str(path))
    blocks: list[Block] = []
    dropped: Counter = Counter()
    for no, slide in enumerate(prs.slides, 1):
        title_shape = slide.shapes.title
        title = (squash(normalize(title_shape.text_frame.text))
                 if getattr(title_shape, "has_text_frame", False) else "")
        body: list[Block] = []
        for shape in _pptx_shapes(slide.shapes):
            if shape.is_placeholder:
                pt = shape.placeholder_format.type
                if pt in PPTX_SKIP_PLACEHOLDERS:
                    dropped["slide_footer_number_date"] += 1
                    continue
                if pt in PPTX_TITLE_PLACEHOLDERS:
                    continue
            if getattr(shape, "has_table", False):
                rows = [[normalize(c.text) for c in r.cells] for r in shape.table.rows]
                md, header = md_table(rows)
                if md:
                    body.append(Block("table", md, page=no, header=header))
                continue
            if not getattr(shape, "has_text_frame", False):
                continue
            paras = [(squash(normalize(p.text)), p.level) for p in shape.text_frame.paragraphs]
            paras = [(t, lvl) for t, lvl in paras if t]
            for t, lvl in paras:
                if is_boilerplate(t) or PAGE_NUMBER_RE.match(t):
                    dropped["boilerplate"] += 1
                elif len(t) <= PPTX_MIN_LABEL_CHARS:
                    dropped["diagram_label"] += 1  # "a", "b", "1." next to arrows and boxes
                else:
                    kind = "list_item" if len(paras) > 1 or lvl > 0 else "paragraph"
                    body.append(Block(kind, BULLET_RE.sub("", t), level=lvl, page=no))
        # decks drawn without a title placeholder: the first short text line is the title
        if not title and body and body[0].kind != "table" and len(body[0].text) <= 100 \
                and len(re.findall(r"\w", body[0].text)) >= 3:
            title = body.pop(0).text
        blocks.append(Block("heading", title or f"Slide {no}", level=2, page=no))
        blocks += body
        frame = slide.notes_slide.notes_text_frame if slide.has_notes_slide else None
        if frame is not None:
            notes = squash(normalize(frame.text))
            if notes and not PAGE_NUMBER_RE.match(notes):
                blocks.append(Block("paragraph", f"Speaker notes: {notes}", page=no))
    deck_title = squash(normalize(prs.core_properties.title or ""))
    meta = {"n_slides": len(prs.slides),
            "created": prs.core_properties.created.isoformat()
            if prs.core_properties.created else ""}
    return ParsedDoc(blocks, title=deck_title, meta=meta, dropped=dict(dropped))
