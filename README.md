# CourseDeck

Teacher assistant: from a lecture-notes PDF to a structured lecture card and a presentation draft in Visme.

Stages:
1. **Extraction**: PDF → lecture card (Pydantic schema, structured output).
2. **RAG**: search over lecture-note chunks with document/page citations.
3. **Agent**: builds a presentation draft from retrieved material.
4. **Service**: FastAPI, batch processing of new documents.

## Layout

```
src/coursedeck/       package code
  dataset/            manifests, PDF inspection, fetching by manifest
data/manifests/       dataset manifests (CSV) and the golden-set list
data/pdfs/            core documents (tier 50, committed)
data/pdfs_extra/      larger tiers, fetched by manifest (not committed)
data/golden/          hand-labelled golden set
scripts/              dataset collection and selection
tests/
```

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use .venv/bin/activate elsewhere
pip install -e ".[dev]"
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

Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` for Claude models; local models
run through [Ollama](https://ollama.com) (`ollama pull qwen3-vl:8b-instruct`).

```bash
python -m coursedeck.extract.run --model haiku --mode text --prompt v2 --effort medium
python -m coursedeck.extract.run --model qwen3-vl-8b --mode image --prompt v2 --temperature 0
```

- Models (`coursedeck/llm/models.py`): `haiku`, `sonnet` (Anthropic API), `qwen3-vl-8b`,
  `qwen3-vl-4b` (Ollama). Current Claude models reject non-default temperature, so their
  sampling axis is `--effort`; local models use `--temperature`.
- Input modes: `text` (text layer), `image` (page images), `text+image`, `pdf` (native PDF
  input, Claude only). Page images are scaled so the smallest text on the page is ~14 px
  tall, capped at 1568 px on the long edge; scans get the full budget.
- Prompts are versioned in `src/coursedeck/prompts/extract/` (see its `CHANGELOG.md`).
- Every reply is validated against `LectureCard`; an invalid reply gets one retry with the
  validation error. Results go to `runs/<run_id>/` (card, attempts, tokens, cost, latency).

## Evaluation

```bash
python -m coursedeck.eval.score runs/<run_a> runs/<run_b> [--include-drafts]
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

## Attribution

Each manifest row carries the source landing page (`source_url`) and license. MIT
OpenCourseWare materials are © MIT, licensed CC BY-NC-SA 4.0. Zenodo documents are
licensed by their authors as listed on the record page; Ukrainian documents are excerpts
(single lectures) of the original works.
