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
data/manifests/       dataset manifests (CSV) and the golden-set list
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

## Attribution

Each manifest row carries the source landing page (`source_url`) and license. MIT
OpenCourseWare materials are © MIT, licensed CC BY-NC-SA 4.0. Zenodo documents are
licensed by their authors as listed on the record page; Ukrainian documents are excerpts
(single lectures) of the original works.
