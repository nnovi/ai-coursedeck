# CourseDeck

Teacher assistant: from a lecture-notes PDF to a structured lecture card and a presentation draft in Visme.

Stages:
1. **Extraction**: PDF → lecture card (Pydantic schema, structured output).
2. **RAG**: search over lecture-note chunks with document/page citations.
3. **Agent**: builds a presentation draft from retrieved material.
4. **Service**: FastAPI, batch processing of new documents.

## Quick start

Requires Python 3.11+. Optional: [Ollama](https://ollama.com) for the local model.

```bash
git clone https://github.com/nnovi/ai-coursedeck.git
cd ai-coursedeck
python -m venv .venv
.venv/Scripts/activate            # Windows; use `source .venv/bin/activate` elsewhere
pip install -e ".[dev]"
cp .env.example .env              # add ANTHROPIC_API_KEY and/or OPENROUTER_API_KEY

python main.py                    # or: make run
```

`main.py` runs the experiment matrix from `configs/experiments.toml` and writes the
comparison table to `results/comparison.md`. Results already in `results/runs/` are reused,
so on a fresh clone it only recomputes the metrics (no API cost, no keys needed).

- `python main.py --local` — also run local Qwen3-VL experiments
  (`ollama pull qwen3-vl:4b-instruct` fits a laptop; `qwen3-vl:8b-instruct` needs ~16 GB VRAM).
- `python main.py --only NAME --force` — rerun one experiment;
  `--dry-run` shows what would run.
- `python -m pytest -q` — tests.

The comparison and the production choice are in [REPORT.md](REPORT.md).

## Layout

```
main.py               one-command benchmark: run missing experiments, score, compare
configs/              experiment matrix (models, input modes, prompt versions, sampling)
prompts/extract/      versioned prompts v1..v3 + CHANGELOG.md
src/coursedeck/
  schema.py           LectureCard (Pydantic) and field groups
  llm/                provider-neutral client + Anthropic, OpenRouter, Ollama adapters
  extract/            page rendering, request building, validation + retry, run CLI
  eval/               metrics against the golden set
  golden/             golden-set store and review UI
  dataset/            manifests, PDF inspection, fetching by manifest
  rag/                RAG corpus manifest, parsers (PDF/HTML/DOCX/PPTX), cleaning,
                      deduplication, chunking, ingestion CLI
data/manifests/       dataset manifests (CSV) and the golden-set list
data/rag/             RAG corpus manifest, raw HTML/DOCX, chunks.jsonl, ingest report
results/rag/          chunking comparison (structure vs fixed)
data/pdfs/            core documents (tier 50, committed)
data/golden/          hand-labelled golden set (+ annotation guide)
results/runs/         model outputs per experiment (config, per-document JSON, summary)
results/comparison.md metrics table: model x mode x prompt x sampling
scripts/              dataset collection and selection
tests/
```

## Dataset

Lecture notes in English (MIT OpenCourseWare, CC BY-NC-SA 4.0) and Ukrainian
(university course books on Zenodo, CC BY 4.0 / CC BY-SA 4.0). Ukrainian books cover a
whole course, so each document is one lecture cut out of a book, preceded by the book's title
pages (cover, title page and its reverse) that carry the course name, authors, institution
and year. The manifest's `pages` column lists the source pages, e.g. `1-3,30-37`.

Manifests are nested: every tier contains the previous one.

| Manifest | Docs | EN | UK | Stored |
|---|---|---|---|---|
| `dataset_050.csv` | 50 | 38 | 12 | in the repo (`data/pdfs/`) |
| `dataset_100.csv` | 100 | 80 | 20 | +50 fetched |
| `dataset_200.csv` | 200 | 165 | 35 | +150 fetched |
| `dataset_500.csv` | 500 | 440 | 60 | +450 fetched |
| `golden.csv` | 20 | 14 | 6 | subset of tier 50 |

English documents are stratified into scans (no text layer), slides and regular notes;
departments are sampled round-robin so even small tiers cover many fields.

Fetch a larger tier (downloads source PDFs, verifies SHA-256, cuts the page ranges):

```bash
python -m coursedeck.dataset.fetch data/manifests/dataset_200.csv
```

Rebuild the dataset from scratch (indexes the sources, downloads ~1 GB of candidates into
`data/cache/`, selects documents, rewrites manifests and `data/pdfs/`):

```bash
python scripts/collect_sources.py
python scripts/build_dataset.py candidates
python scripts/build_dataset.py download
python scripts/build_dataset.py inspect
python scripts/build_dataset.py select
```

Selection rules: 2–30 pages; documents with MIT's "excluded from our Creative Commons
license" notice (third-party material) are dropped; Zenodo records under NoDerivatives
licenses are skipped because cutting out a lecture is an adaptation; duplicates are removed
by text fingerprint and lecture heading. Manual decisions live in
`scripts/manual_segments.json` (title pages and lecture ranges for scanned books) and
`scripts/exclude.json`.

## Extraction

A single run outside the matrix:

```bash
python -m coursedeck.extract.run --model haiku --mode image --prompt v3 --effort medium
python -m coursedeck.extract.run --model qwen3-vl-8b --mode image --temperature 0 --top-p 0.9
```

- Models (`src/coursedeck/llm/models.py`): `haiku`, `sonnet` (Anthropic API),
  `gpt-6-luna` (OpenRouter), `qwen3-vl-8b`, `qwen3-vl-4b` (Ollama), all behind one
  `Adapter` interface. Current Claude models reject non-default temperature/top_p, so their
  sampling knob is `effort`; the other models use `temperature`/`top_p`.
- Every request has a timeout and transport retries (HTTP 429/5xx); both are set in
  `configs/experiments.toml`.
- Input modes: `text` (text layer), `image` (page images), `text+image`, `pdf` (native PDF
  input, Claude only). Page images are scaled so the smallest text on the page is ~14 px
  tall, capped at 1568 px on the long edge; scans get the full budget.
- Prompts are versioned in `prompts/extract/` (see its `CHANGELOG.md`); from v3 the source
  file name is sent as a fallback source of facts.
- Every reply is validated against `LectureCard`; an invalid reply gets one retry with the
  validation error, then the document is marked `failed`. Each run directory logs the model,
  prompt version and hash, sampling, timeout and git commit (`config.json`), and per
  document the card, every attempt, tokens, cost and latency.

## Evaluation

```bash
python -m coursedeck.eval.score results/runs/<run_a> results/runs/<run_b>
```

Scores each run against the reviewed golden cards (`--include-drafts` also uses unreviewed
ones), per field group:

- facts: exact match for code, lecture number, year and term; fuzzy match for course title,
  institution (with MIT aliases) and lecture title; lecturers by surname. Also the
  hallucination rate (filled although the golden value is empty) and omission rate;
- classification: accuracy, with the confusions listed;
- content: fuzzy F1 of topics, key terms and references (greedy one-to-one matching).

Results are also broken down by stratum (Ukrainian, English scans, slides, notes) to show
where page images help.

## RAG corpus and chunking

```bash
make ingest        # = python -m coursedeck.rag.corpus fetch && python -m coursedeck.rag.ingest
```

### Corpus

131 documents in four formats, centred on courses so that one question can need a lecture,
its slides and the course syllabus (`data/rag/corpus.csv`, built by
`scripts/build_rag_corpus.py`):

| Format | Docs | What | Source |
|---|---|---|---|
| PDF | 43 (32 EN, 11 UK) | lecture notes and slides with a text layer (tier 50 above) | OCW, Zenodo |
| HTML | 55 | course home, syllabus and calendar pages of 21 OCW course runs | OCW |
| PPTX | 25 (21 EN, 4 UK) | lecture slides (18.404J, 12.010, CMS.595, 6.007, RES.11-003, Zenodo) | OCW, Zenodo |
| DOCX | 8 (4 EN, 4 UK) | lecture texts, a workbook, a course schedule | Zenodo |

- Older runs of some courses (12.010 Fall 2011 vs Fall 2024, 5.13 Fall 2003 vs Fall 2006,
  PE.550 IAP 2007 vs Spring 2009) and "X" vs "X 2.0" decks of RES.11-003 are kept on
  purpose: they are the "similar document / outdated version" distractors for the eval
  set. Chunks carry `version`, `year` and `is_latest`, so retrieval can filter or prefer
  the current run.
- Scanned PDFs (7 of the 50) are left out: they have no text layer to index.
- HTML and DOCX files are committed in `data/rag/raw/`; PPTX decks (~100 MB) are
  downloaded by `python -m coursedeck.rag.corpus fetch` and checked against the manifest's
  SHA-256. PDFs are the committed `data/pdfs/`.

### Ingestion (`src/coursedeck/rag/`)

1. **Parse to structure** (`parse.py`): every format becomes a list of blocks (heading with
   level, paragraph, list item with depth, table as Markdown) with page/slide numbers.
   - PDF (PyMuPDF): heading levels from font sizes relative to the body text, bold
     stand-alone lines and "Lecture 3 / Тема 1" patterns; bullets and numbered items;
     ruled tables via `find_tables`.
   - HTML (BeautifulSoup): only the content root (`<main>`), `h1–h6`, `p`, nested lists,
     tables with header rows.
   - DOCX (python-docx): heading styles, list numbering, tables in document order.
   - PPTX (python-pptx): one section per slide (title placeholder, else the first short
     line), bullet levels, tables, speaker notes.
2. **Clean** (`clean.py`): Unicode NFC, ligatures, soft hyphens, zero-width and
   non-breaking spaces, CP1252 mojibake; end-of-line hyphenation undone ("transfor-" +
   "mation"), paragraphs re-joined across page breaks; running headers/footers (lines in
   the page margins repeated on ≥ 50% of pages), page numbers and the OCW license page
   removed; HTML navigation, cookie banners, icons and duplicated mobile/desktop blocks
   removed; slide footers, numbers, dates and 1–2 character diagram labels removed. Counts
   per document are in `data/rag/ingest_report.json`.
3. **Deduplicate** (`dedup.py`): documents by a SHA-256 of the normalized text (same
   content in another file or format) and by word 5-gram shingles (Jaccard ≥ 0.8 or
   containment ≥ 0.9). Near duplicates of the same course run are copies: the more complete
   one is kept (here: a workbook and the same workbook with answers, Jaccard 0.99). Near
   duplicates from different runs are kept and linked as versions. Chunks are deduplicated
   by the hash of their normalized text (repeated title slides, cover pages).
4. **Chunk** (`chunk.py`) and write `data/rag/chunks.jsonl` (1121 chunks).

Each chunk carries `chunk_id`, `doc_id`, `text`, `context` (course | document | section,
prepended for embedding and shown with citations), `section` (heading path), `pages`
(PDF pages or slide numbers), `n_tokens`, `format`, `kind`, `lang`, `source`, `course_id`,
`course_title`, `title`, `version`, `year`, `is_latest`, `url` and `doc_sha256`.

### Chunking strategy and why

**Structure-aware chunks of at most 400 tokens**: a chunk never crosses a section
boundary, except that sections smaller than 100 tokens are merged with their siblings
(consecutive slides, short subsections), each keeping its `## heading` line. A block is
split only when it alone exceeds 400 tokens: paragraphs at sentence boundaries, tables by
rows with the header row repeated in every part.

- **Why by structure.** Lecture material is already organized into units that answer one
  question: a definition under a subsection, a slide, a syllabus section ("Grading",
  "Prerequisites"), a calendar table. A chunk that follows them can be cited by document
  and section, which the RAG step needs for its citations.
- **Why 400 tokens.** Measured with the bge-m3 tokenizer (the planned embedding model,
  multilingual EN/UK), the median non-empty section is 78 tokens, and 90% of sections fit
  in 400 tokens (76% in 200). So 400 keeps almost every section whole. It also keeps chunks
  focused enough for embedding similarity, and 6–8 retrieved chunks fit a ~3K-token
  context budget.
- **Why merge below 100 tokens.** Slides and short syllabus sections alone are too short
  to embed well ("Outline", a title slide). Without merging, 40% of chunks are under
  50 tokens; with it, 4%.
- **Tokens, not characters.** In this tokenizer Ukrainian text takes 2.0 tokens per word
  and English 1.6, so a character or word limit would give the two languages different
  real chunk sizes.

**Compared with fixed-size chunks** (400 tokens, 50-token overlap) on the whole corpus
(details and side-by-side examples: [results/rag/chunking.md](results/rag/chunking.md)):

| strategy | chunks | tokens p50 | cut mid-block | mixed sections | table rows without header |
|---|---|---|---|---|---|
| structure | 1128 | 272 | 2% | 32%¹ | 0% |
| fixed | 855 | 400 | 95% | 63% | 9% |

¹ structure chunks mix sections only when merging small siblings, and they keep each
heading as a line; fixed chunks mix arbitrary text without markers, so for them the
`section` label is only partly right.

Fixed windows start and end mid-sentence in 95% of chunks. They split syllabus and
calendar tables so that 21% of HTML chunks hold rows without the header, and 91% of slide
chunks span several slides. Whether this also lowers retrieval quality is measured in step 2
(recall@k on both chunk files; `data/rag/chunks_fixed.jsonl` is kept for that).

## Attribution

Each manifest row carries the source landing page (`source_url`) and license. MIT
OpenCourseWare materials are © MIT, licensed CC BY-NC-SA 4.0. Zenodo documents are
licensed by their authors as listed on the record page; Ukrainian documents are excerpts
(single lectures) of the original works.
