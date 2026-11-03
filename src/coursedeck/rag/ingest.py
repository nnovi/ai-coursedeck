"""Ingestion: corpus manifest -> parse -> clean -> deduplicate -> chunk -> chunks.jsonl.

    python -m coursedeck.rag.ingest                 # both strategies + comparison report

Outputs:
    data/rag/chunks.jsonl         structure-aware chunks (the index input)
    data/rag/chunks_fixed.jsonl   fixed-size baseline, kept for the retrieval comparison
    data/rag/ingest_report.json   per document: blocks, cleaning counts, dedup decision, chunks
    results/rag/chunking.md       structure vs fixed: size and boundary statistics, examples
"""

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from coursedeck.rag.blocks import ParsedDoc
from coursedeck.rag.chunk import STRATEGIES, RawChunk, render
from coursedeck.rag.corpus import CORPUS_DIR, MANIFEST, CorpusDoc, read_corpus
from coursedeck.rag.dedup import chunk_hash, content_hash, dedup_docs
from coursedeck.rag.parse import parse

RESULTS = Path("results/rag")
CHUNK_FILES = {"structure": CORPUS_DIR / "chunks.jsonl", "fixed": CORPUS_DIR / "chunks_fixed.jsonl"}
# documents shown side by side in the comparison report: notes PDF, slides, HTML table, DOCX
EXAMPLE_DOCS = ["ocw-6-241j-mit6_241js11_lec03", "pptx-ocw-mit18_404f20_lec2",
                "html-18-310-f13-calendar", "docx-zen-20835946"]


def latest_versions(docs: list[CorpusDoc]) -> set[str]:
    """Doc ids that belong to the newest run of their course (per document kind): an older
    syllabus of the same course is an outdated version, not a separate source."""
    newest: dict[tuple[str, str], int] = {}
    for d in docs:
        key = (d.course_id, d.kind)
        newest[key] = max(newest.get(key, 0), d.year or 0)
    return {d.doc_id for d in docs if (d.year or 0) == newest[(d.course_id, d.kind)]}


def chunk_record(doc: CorpusDoc, i: int, c: RawChunk, strategy: str, is_latest: bool) -> dict:
    section = " > ".join(c.path)
    return {
        "chunk_id": f"{doc.doc_id}#{i:03d}",
        "doc_id": doc.doc_id,
        "strategy": strategy,
        "text": c.text,
        # prepended to the text for embedding and shown with citations
        "context": " | ".join(x for x in (doc.course_title, doc.title, section) if x),
        "section": section,
        "pages": c.pages,  # PDF pages or PPTX slide numbers
        "n_tokens": c.tokens,
        "format": doc.format,
        "kind": doc.kind,
        "lang": doc.lang,
        "source": doc.source,
        "course_id": doc.course_id,
        "course_title": doc.course_title,
        "title": doc.title,
        "version": doc.version,
        "year": doc.year,
        "is_latest": is_latest,  # False for an older run of the same course
        "url": doc.url,
        "doc_sha256": doc.sha256,
    }


def ingest(docs: list[CorpusDoc], max_tokens: int, min_tokens: int, overlap: int):
    parsed: dict[str, ParsedDoc] = {}
    for i, d in enumerate(docs, 1):
        parsed[d.doc_id] = parse(d.file, d.format)
        print(f"\rparse {i}/{len(docs)}", end="", file=sys.stderr)
    print(file=sys.stderr)
    decisions = dedup_docs([(d.doc_id, f"{d.course_id}|{d.version}", parsed[d.doc_id].text)
                            for d in docs])
    keep = [d for d in docs if decisions[d.doc_id].action in {"keep", "keep_version"}]
    latest = latest_versions(keep)

    out, report = {}, {d.doc_id: {} for d in docs}
    for strategy, fn in STRATEGIES.items():
        kwargs = ({"max_tokens": max_tokens, "min_tokens": min_tokens} if strategy == "structure"
                  else {"max_tokens": max_tokens, "overlap": overlap})
        records, raw, seen, dup_chunks, n_kept = [], {}, set(), Counter(), Counter()
        for d in keep:
            chunks = fn(parsed[d.doc_id], **kwargs)
            raw[d.doc_id] = chunks
            for c in chunks:
                h = chunk_hash(c.text)
                if h in seen or not re.search(r"\w{2}", c.text):
                    dup_chunks[d.doc_id] += 1
                    continue
                seen.add(h)
                records.append(chunk_record(d, n_kept[d.doc_id], c, strategy,
                                            d.doc_id in latest))
                n_kept[d.doc_id] += 1
        out[strategy] = (records, raw)
        for d in docs:
            report[d.doc_id][f"chunks_{strategy}"] = sum(r["doc_id"] == d.doc_id for r in records)
            report[d.doc_id][f"duplicate_chunks_{strategy}"] = dup_chunks[d.doc_id]
    for d in docs:
        p = parsed[d.doc_id]
        report[d.doc_id] = {
            "format": d.format, "kind": d.kind, "lang": d.lang,
            "chars": len(p.text), "content_hash": content_hash(p.text),
            "blocks": dict(Counter(b.kind for b in p.blocks)),
            "dropped": p.dropped,
            "dedup": {k: v for k, v in asdict(decisions[d.doc_id]).items() if v and k != "doc_id"},
            **report[d.doc_id],
        }
    return parsed, out, report


# ------------------------------------------------------------------------------- comparison

def boundary_stats(chunks: list[RawChunk], doc: ParsedDoc) -> dict:
    """How chunk boundaries relate to the document structure."""
    rendered = {render(b).strip() for b in doc.blocks}
    n = len(chunks) or 1
    cut = 0  # chunk starts or ends inside a block (mid-paragraph, mid-list item, mid-row)
    for c in chunks:
        lines = [x.strip() for x in c.text.split("\n") if x.strip() and not x.startswith("## ")]
        if not lines:
            continue
        first, last = lines[0], lines[-1]
        # a table part is clean when it starts with the (repeated) header and ends on a full row
        header_first = first.startswith("|") and len(lines) > 1 and lines[1].startswith("|---")
        starts_clean = first in rendered or header_first
        ends_clean = last in rendered or last.endswith((".", "!", "?", ":", "|"))
        cut += not (starts_clean and ends_clean)
    headerless = sum(bool(re.search(r"^\|.*\|$", c.text, re.MULTILINE)) and "|---" not in c.text
                     for c in chunks)
    return {"cut": cut, "multi_section": sum(c.n_sections > 1 for c in chunks),
            "headerless_table": headerless, "n": n}


def compare(parsed: dict[str, ParsedDoc], out: dict, docs: list[CorpusDoc], max_tokens: int,
            min_tokens: int, overlap: int) -> str:
    fmt_of = {d.doc_id: d.format for d in docs}
    lines = [
        "# Chunking: structure-aware vs fixed-size",
        "",
        (f"Generated by `python -m coursedeck.rag.ingest`. Both strategies use the bge-m3 "
         f"tokenizer and `max_tokens={max_tokens}`; structure merges chunks under "
         f"{min_tokens} tokens with sibling sections, fixed uses a {overlap}-token overlap."),
        "",
        "- **cut**: the chunk starts or ends inside a paragraph, list item or table row;",
        ("- **multi-section**: the chunk holds content of more than one heading path. "
         "Structure chunks merge only small sibling sections and keep their `## heading` "
         "lines; fixed chunks mix sections with no marker, so their `section` label is "
         "only partly right;"),
        "- **headerless table**: table rows without the header row (columns lose meaning).",
        "",
        ("| format | strategy | docs | chunks | tokens p50 | tokens p95 | < 50 tokens | cut | "
         "multi-section | headerless table |"),
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for fmt in ["all", "pdf", "html", "docx", "pptx"]:
        for strategy, (_, raw) in out.items():
            ids = [i for i in raw if fmt == "all" or fmt_of[i] == fmt]
            chunks = [c for i in ids for c in raw[i]]
            stats = Counter()
            for i in ids:
                stats.update(boundary_stats(raw[i], parsed[i]))
            toks = sorted(c.tokens for c in chunks)
            n = len(chunks) or 1
            p95 = toks[int(0.95 * (len(toks) - 1))] if toks else 0
            lines.append(
                f"| {fmt} | {strategy} | {len(ids)} | {len(chunks)} | "
                f"{statistics.median(toks) if toks else 0:.0f} | {p95} | "
                f"{sum(t < 50 for t in toks) / n:.0%} | {stats['cut'] / n:.0%} | "
                f"{stats['multi_section'] / n:.0%} | {stats['headerless_table'] / n:.0%} |")
    lines += ["", "## Examples", "",
              "First chunks of the same document under both strategies (text shortened)."]
    for doc_id in EXAMPLE_DOCS:
        if doc_id not in out["structure"][1]:
            continue
        lines += ["", f"### {doc_id} ({fmt_of[doc_id]})", ""]
        for strategy, (_, raw) in out.items():
            lines += [f"**{strategy}**", ""]
            for c in raw[doc_id][:3]:
                text = c.text if len(c.text) <= 600 else c.text[:600] + " …"
                lines += [(f"- section `{' > '.join(c.path) or '-'}`, pages {c.pages}, "
                           f"{c.tokens} tokens:"), "", "  ```text"]
                lines += ["  " + x for x in text.split("\n")]
                lines += ["  ```", ""]
    return "\n".join(lines) + "\n"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--min-tokens", type=int, default=100)
    ap.add_argument("--overlap", type=int, default=50, help="fixed strategy only")
    args = ap.parse_args()

    docs = read_corpus(args.manifest)
    missing = [d.doc_id for d in docs if not d.file.exists()]
    if missing:
        sys.exit(f"{len(missing)} files missing (run `python -m coursedeck.rag.corpus fetch`): "
                 f"{missing[:3]}")
    parsed, out, report = ingest(docs, args.max_tokens, args.min_tokens, args.overlap)
    for strategy, (records, _) in out.items():
        write_jsonl(CHUNK_FILES[strategy], records)
        print(f"{strategy}: {len(records)} chunks -> {CHUNK_FILES[strategy]}")
    actions = Counter(r["dedup"].get("action", "keep") for r in report.values())
    summary = {"documents": len(docs), "formats": dict(Counter(d.format for d in docs)),
               "dedup": dict(actions),
               "params": {"max_tokens": args.max_tokens, "min_tokens": args.min_tokens,
                          "overlap": args.overlap}}
    (CORPUS_DIR / "ingest_report.json").write_text(
        json.dumps({"summary": summary, "documents": report}, ensure_ascii=False, indent=1),
        encoding="utf-8", newline="\n")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "chunking.md").write_text(
        compare(parsed, out, docs, args.max_tokens, args.min_tokens, args.overlap),
        encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
