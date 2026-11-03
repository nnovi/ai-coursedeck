"""Chunking strategies over ParsedDoc blocks.

structure  sections from headings (PDF font sizes, HTML h1-h6, DOCX heading styles, one
           section per slide); blocks are packed within a section up to `max_tokens`; a
           block is split only if it alone is too long (paragraph -> sentences, table ->
           row groups with the header repeated); small chunks are merged with their
           neighbours under the same top-level section.
fixed      the rendered document cut into windows of `max_tokens` with `overlap` tokens,
           ignoring structure; the baseline the structure strategy is compared against.

Token counts use the tokenizer of the embedding model (BAAI/bge-m3), so sizes mean the same
for English and Ukrainian text.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache

from tokenizers import Tokenizer

from coursedeck.rag.blocks import Block, ParsedDoc

TOKENIZER = "BAAI/bge-m3"
SENTENCE_RE = re.compile(r"(?<=[.!?…;])\s+(?=[\"«(\[]?[A-ZА-ЯІЇЄҐ0-9])")


@lru_cache(maxsize=1)
def tokenizer() -> Tokenizer:
    return Tokenizer.from_pretrained(TOKENIZER)


def n_tokens(text: str) -> int:
    return len(tokenizer().encode(text, add_special_tokens=False).ids)


@dataclass
class Piece:
    """Rendered text of one block (or of a part of a too-long block) with its position."""
    text: str
    path: tuple[str, ...]  # heading path
    page: int | None
    tokens: int


@dataclass
class RawChunk:
    text: str
    path: tuple[str, ...]  # section of the first piece
    pages: list[int] = field(default_factory=list)
    tokens: int = 0
    n_sections: int = 1  # distinct heading paths the chunk's content comes from


def render(b: Block) -> str:
    if b.kind == "list_item":
        return "  " * b.level + "- " + b.text
    return b.text


def _cut_words(text: str, budget: int) -> list[str]:
    parts, buf = [], []
    for w in text.split(" "):
        if buf and n_tokens(" ".join(buf + [w])) > budget:
            parts.append(" ".join(buf))
            buf = []
        buf.append(w)
    return parts + [" ".join(buf)] if buf else parts


def _split_long(b: Block, max_tokens: int) -> list[str]:
    """A block longer than max_tokens -> parts: tables by rows (header repeated), other text
    by sentences; a single sentence or row that is still too long is cut by words."""
    if b.kind == "table" and b.header:
        header, sep = b.header, "\n"
        units = b.text.split("\n")[len(header.split("\n")):]
    else:
        header, sep = "", " "
        units = SENTENCE_RE.split(render(b))
    budget = max_tokens - n_tokens(header) - 1
    small = []
    for u in units:
        small += [u] if n_tokens(u) <= budget else _cut_words(u, budget)
    parts, cur = [], []
    for u in small:
        if cur and n_tokens(sep.join(cur + [u])) > budget:
            parts.append(sep.join(cur))
            cur = []
        cur.append(u)
    if cur:
        parts.append(sep.join(cur))
    return [f"{header}\n{p}" if header else p for p in parts]


def pieces(doc: ParsedDoc, max_tokens: int) -> list[Piece]:
    """Content blocks with their heading path. Headings build the path; a heading with
    nothing under it (title page, title-only slide) becomes an empty piece, so the chunk
    still carries its "## heading" line."""
    out, stack = [], []  # stack of (level, heading text)
    empty: Block | None = None  # last heading that has no content yet
    for b in doc.blocks:
        if b.kind == "heading":
            if empty is not None and b.level <= empty.level:
                out.append(Piece("", tuple(t for _, t in stack), empty.page, 0))
            while stack and stack[-1][0] >= b.level:
                stack.pop()
            stack.append((b.level, b.text))
            empty = b
            continue
        empty = None
        path = tuple(t for _, t in stack)
        text = render(b)
        tokens = n_tokens(text)
        if tokens <= max_tokens:
            out.append(Piece(text, path, b.page, tokens))
        else:
            out += [Piece(t, path, b.page, n_tokens(t)) for t in _split_long(b, max_tokens)]
    if empty is not None:
        out.append(Piece("", tuple(t for _, t in stack), empty.page, 0))
    return out


def _heading_line(path: tuple[str, ...]) -> str:
    return f"## {path[-1]}" if path else ""


def _append(chunk: RawChunk, p: Piece, prev_path: tuple[str, ...] | None) -> None:
    lines = [chunk.text] if chunk.text else []
    if p.path != prev_path and p.path:
        lines.append(_heading_line(p.path))
    if p.text:
        lines.append(p.text)
    chunk.text = "\n".join(lines)
    if prev_path is not None and p.path != prev_path:
        chunk.n_sections += 1
    if p.page is not None and p.page not in chunk.pages:
        chunk.pages.append(p.page)


def chunk_structure(doc: ParsedDoc, max_tokens: int = 400, min_tokens: int = 100) -> list[RawChunk]:
    ps = pieces(doc, max_tokens)
    # 1) pack pieces within a section
    chunks: list[RawChunk] = []
    cur: RawChunk | None = None
    last_path = None
    for p in ps:
        heading_cost = n_tokens(_heading_line(p.path)) if p.path != last_path else 0
        if cur is None or p.path != cur.path or cur.tokens + heading_cost + p.tokens > max_tokens:
            cur = RawChunk("", p.path)
            chunks.append(cur)
            last_path = None
            heading_cost = n_tokens(_heading_line(p.path))
        _append(cur, p, last_path)
        cur.tokens += heading_cost + p.tokens
        last_path = p.path
    # 2) merge small chunks into a neighbour under the same top-level section or parent
    #    (sibling sections, consecutive slides)
    merged: list[RawChunk] = []
    for c in chunks:
        prev = merged[-1] if merged else None
        if (prev and (prev.tokens < min_tokens or c.tokens < min_tokens)
                and (prev.path[:1] == c.path[:1] or prev.path[:-1] == c.path[:-1])
                and prev.tokens + c.tokens <= max_tokens):
            prev.text = f"{prev.text}\n{c.text}"
            prev.tokens += c.tokens
            prev.n_sections += c.n_sections
            prev.pages += [pg for pg in c.pages if pg not in prev.pages]
        else:
            merged.append(c)
    return merged


def chunk_fixed(doc: ParsedDoc, max_tokens: int = 400, overlap: int = 50) -> list[RawChunk]:
    """Fixed-size token windows over the whole rendered document (headings included as
    lines). The section and page of a chunk are those at its first character."""
    parts, spans, pos = [], [], 0  # spans: (start char, path, page)
    stack: list[tuple[int, str]] = []
    for b in doc.blocks:
        if b.kind == "heading":
            while stack and stack[-1][0] >= b.level:
                stack.pop()
            stack.append((b.level, b.text))
        text = render(b)
        spans.append((pos, tuple(t for _, t in stack), b.page))
        parts.append(text)
        pos += len(text) + 1
    full = "\n".join(parts)
    enc = tokenizer().encode(full, add_special_tokens=False)
    offsets = enc.offsets
    chunks, start = [], 0
    while start < len(offsets):
        end = min(start + max_tokens, len(offsets))
        a, b = offsets[start][0], offsets[end - 1][1]
        at = [s for s in spans if s[0] <= a][-1] if spans else (0, (), None)
        inside = [s[2] for s in spans if a <= s[0] < b and s[2] is not None]
        pages = sorted({p for p in [at[2], *inside] if p is not None})
        n_sections = len({at[1], *(s[1] for s in spans if a <= s[0] < b)})
        chunks.append(RawChunk(full[a:b], at[1], pages, end - start, n_sections))
        if end == len(offsets):
            break
        start = end - overlap
    return chunks


STRATEGIES = {"structure": chunk_structure, "fixed": chunk_fixed}
