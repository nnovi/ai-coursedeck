"""Format-neutral document structure produced by the parsers and consumed by the chunkers."""

from dataclasses import dataclass, field


@dataclass
class Block:
    kind: str  # heading | paragraph | list_item | table
    text: str  # tables are Markdown; everything else is plain text
    level: int = 0  # heading level (1 = top) or list nesting depth (0 = top)
    page: int | None = None  # 1-based page (PDF) or slide (PPTX); None for HTML/DOCX
    header: str = ""  # tables only: Markdown header rows, repeated when a table is split


@dataclass
class ParsedDoc:
    blocks: list[Block]
    title: str = ""  # title found in the file itself (metadata, <title>, first heading)
    meta: dict = field(default_factory=dict)  # format-specific extras (dates, page count, ...)
    dropped: dict = field(default_factory=dict)  # cleaning log: what was removed and how often

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks)


def md_table(rows: list[list[str]], n_header: int = 1) -> tuple[str, str]:
    """Rows of cell texts -> (Markdown table, its header part)."""
    rows = [[" ".join(c.split()).replace("|", "\\|") for c in r] for r in rows if any(c.strip() for c in r)]
    if not rows:
        return "", ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    n_header = min(max(n_header, 1), len(rows))
    lines = ["| " + " | ".join(r) + " |" for r in rows]
    header = lines[:n_header] + ["|" + "---|" * width]
    return "\n".join(header + lines[n_header:]), "\n".join(header)
