# CourseDeck — extraction benchmark report

Task: turn a lecture-notes PDF into a `LectureCard` (13 fields: 8 facts, 2 classifications,
3 content lists; `src/coursedeck/schema.py`) and choose the model, prompt and settings for
production. All numbers below are reproducible with `python main.py` (saved outputs in
`results/runs/`, full table in `results/comparison.md`).

## 1. Setup

| | |
|---|---|
| Data | 50 PDFs (38 EN from MIT OCW, 12 UK lectures cut from Zenodo course books): typed notes, handwritten and typed scans without text layer, slide decks, book chapters; 2–30 pages |
| Golden set | 20 documents (14 EN, 6 UK) annotated by the guide `data/golden/README.md`, double-checked and human-reviewed |
| Models | **Claude Haiku 5.5**, **Claude Sonnet 5.5** (Anthropic API), **GPT-6 Luna** (OpenRouter), **Qwen3-VL 8B / 4B** (local, Ollama) — one `Adapter` interface |
| Input modes | `text` (PDF text layer), `image` (page images sized to the smallest text), `text+image`, `pdf` (native PDF input, Claude only) |
| Prompts | `prompts/extract/v1` baseline → `v2` + annotation rules → `v3` + file-name fallback, term rule, anti-hallucination lines (`CHANGELOG.md`) |
| Sampling | Claude rejects non-default `temperature`/`top_p`, so its knob is `effort` (low/medium/high); GPT and Qwen use `temperature`/`top_p` |
| Validation | structured output + Pydantic validation; one repair retry with the error, then `failed`; transport retries and timeouts from `configs/experiments.toml` |

Metrics (`src/coursedeck/eval/metrics.py`), measured on the 20 golden documents:

- **facts** — share of correct facts (exact for code, number, year, term; fuzzy for course
  title, institution, lecture title; lecturers by surname);
- **halluc.** — share of facts filled although the golden value is empty;
  **omitted** — empty although the golden value is filled;
- **class.** — accuracy of `discipline` and `doc_type`;
- **content F1** — fuzzy F1 of topics, key terms and references;
- **overall** — mean of the three group scores;
- **valid** — share of schema-valid cards after at most one repair retry;
- **p50 / p95** — latency per document; **$/1000** — cost per 1000 documents from token
  usage and list prices (local models: 0, hardware not counted).

## 2. Comparison: model × prompt version × sampling

Main matrix, `image` mode (the best mode for every model, see §3):

| model | prompt | sampling | valid | facts | halluc. | omitted | class. | content F1 | **overall** | p50 s | p95 s | $/1000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Haiku 5.5 | v1 | effort=medium | 1.00 | 0.91 | 0.07 | 0.05 | 0.82 | 0.68 | 0.81 | 5.3 | 10.0 | 1.94 |
| Haiku 5.5 | v2 | effort=medium | 1.00 | 0.94 | 0.05 | 0.06 | 1.00 | 0.82 | 0.92 | 5.7 | 11.5 | 2.15 |
| **Haiku 5.5** | **v3** | **effort=medium** | **1.00** | **0.94** | **0.07** | **0.03** | **1.00** | **0.83** | **0.93** | **6.1** | **12.4** | **2.13** |
| Haiku 5.5 | v3 | effort=low | 1.00 | 0.89 | 0.16 | 0.04 | 0.90 | 0.79 | 0.86 | 3.6 | 6.6 | 1.87 |
| Haiku 5.5 | v3 | effort=high | 1.00 | 0.97 | 0.05 | 0.00 | 0.97 | 0.86 | 0.94 | 8.4 | 18.7 | 2.47 |
| Haiku 5.5, all 50 docs | v3 | effort=medium | 1.00 | 0.94 | 0.05 | 0.03 | 1.00 | 0.84 | 0.93 | 6.9 | 10.6 | 1.98 |
| Sonnet 5.5 | v3 | effort=medium | 1.00 | 0.95 | 0.09 | 0.00 | 1.00 | 0.87 | 0.94 | 5.5 | 9.7 | 35.10 |
| Sonnet 5.5 (`pdf` mode) | v3 | effort=medium | 1.00 | 0.96 | 0.09 | 0.00 | 1.00 | 0.88 | **0.95** | 4.7 | 9.2 | 49.58 |
| GPT-6 Luna | v3 | default | 1.00 | 0.95 | 0.10 | 0.00 | 1.00 | 0.82 | 0.92 | 10.5 | 22.7 | 1.87 |
| GPT-6 Luna | v3 | t=0 | 1.00 | 0.94 | 0.12 | 0.00 | 0.97 | 0.82 | 0.91 | 10.9 | 22.7 | 1.87 |
| GPT-6 Luna | v3 | t=0.7, top_p=0.9 | 1.00 | 0.95 | 0.10 | 0.00 | 1.00 | 0.82 | 0.92 | 10.7 | 21.9 | 0.61* |
| Qwen3-VL 8B (local) | v1 | t=0 | 1.00 | 0.79 | 0.34 | 0.05 | 0.47 | 0.47 | 0.58 | 9.3 | 35.0 | 0 |
| Qwen3-VL 8B (local) | v2 | t=0 | 1.00 | 0.80 | 0.28 | 0.12 | 0.82 | 0.73 | 0.78 | 8.9 | 35.3 | 0 |
| Qwen3-VL 8B (local) | v2 | t=0.7 | 1.00 | 0.82 | 0.22 | 0.11 | 0.80 | 0.70 | 0.77 | 8.7 | 40.9 | 0 |
| Qwen3-VL 8B (local) | v3 | t=0 | 1.00 | 0.79 | 0.34 | 0.08 | 0.80 | 0.69 | 0.76 | 7.5 | 34.4 | 0 |
| Qwen3-VL 8B (local) | v3 | t=0.7, top_p=0.9 | 1.00 | 0.79 | 0.33 | 0.09 | 0.80 | 0.69 | 0.76 | 7.3 | 30.6 | 0 |
| Qwen3-VL 4B (local) | v2 | t=0 | 1.00 | 0.82 | 0.24 | 0.08 | 0.80 | 0.66 | 0.76 | 5.2 | 23.4 | 0 |
| Qwen3-VL 4B (local) | v3 | t=0 | 1.00 | 0.79 | 0.31 | 0.09 | 0.70 | 0.65 | 0.71 | 3.9 | 28.4 | 0 |

\* OpenRouter served most of this run's prompt from its cache (same prompts as the two runs
before), so its token cost is not comparable. Local latency is on an RTX 4090; a laptop
CPU/GPU will be several times slower.

Input-mode axis (prompt v3; Claude effort=medium, GPT default):

| model | text | image | text+image | pdf |
|---|---|---|---|---|
| Haiku 5.5 — overall / $ per 1000 | 0.80 / 0.96 | **0.93 / 2.13** | 0.92 / 2.55 | 0.93 / 2.78 |
| Sonnet 5.5 — overall / $ per 1000 | 0.86 / 16.6 | 0.94 / 35.1 | 0.92 / 46.2 | **0.95 / 49.6** |
| GPT-6 Luna — overall / $ per 1000 | 0.81 / 0.80 | **0.92 / 1.87** | 0.92 / 2.28 | – |
| Qwen3-VL 8B — overall | 0.71 | **0.76** | – | – |

Overall score by document type (prompt v3, effort=medium):

| run | EN notes | EN scans | EN slides | UK book chapters |
|---|---|---|---|---|
| Haiku `text` | 0.83 | **0.57** | 0.90 | 0.81 |
| Haiku `image` | 0.93 | 0.92 | 0.94 | 0.91 |
| Sonnet `pdf` | 0.95 | 0.92 | 0.94 | 0.96 |
| GPT-6 Luna `image` | 0.93 | 0.90 | 0.88 | 0.94 |
| Qwen3-VL 8B `image` | 0.83 | 0.74 | 0.72 | 0.70 |

Per-field scores of every run (13 fields) and all 32 configurations, including `text+image`
for every model and the Qwen v1/v2 matrix, are in `results/comparison.md`.

## 3. What the numbers say

1. **Prompt rules matter most for classification and content.** Haiku v1 → v2: overall
   0.81 → 0.92, `doc_type`/`discipline` 0.82 → 1.00, references F1 0.52 → 0.94 (v1 had no
   "literature list only" rule and listed laws such as "Конституція України", the book's
   own bibliographic record, "MIT OCW" and names of scholarly schools as references). v2 → v3 is +0.01 for
   Haiku; v3's new anti-hallucination lines did **not** help Qwen (0.78 → 0.76,
   hallucinations 0.28 → 0.34): the small local model does not follow negative rules.
2. **Page images are needed.** Text-only loses everything on scans (0.57 vs 0.92) and
   misclassifies document types (`doc_type` 0.70 vs 1.00) for every provider model.
   `text+image` adds cost but no quality; Claude's native `pdf` mode equals `image` for
   Haiku at +30% cost.
3. **Sampling is a minor knob.** GPT-6 Luna: default / t=0 / t=0.7, top_p=0.9 → 0.92 /
   0.91 / 0.92; Qwen: t=0 vs t=0.7 (+top_p=0.9) → within 0.01–0.02. With 20 documents one
   wrong field of one document moves `overall` by ~0.003–0.02, so these differences are
   noise. Claude's `effort` is the knob that matters: `low` (less thinking) raises
   hallucinations to 16% (0.86); `high` gains +0.01 for +16% cost and +40% latency.
4. **Provider models beat the local model by a wide margin** (0.92–0.95 vs 0.76–0.78), and
   the gap is mostly hallucinated facts (5–10% vs 22–34%).
5. **Validity is not the problem:** after the repetition-loop fix (error 5) every
   configuration returns 100% valid cards on the first attempt, except one Qwen v1 run
   (19/20; the repair retry did not help).

## 4. Characteristic errors

**1. Scans in text mode: empty text layer → empty card.**
`ocw-8-08-the_fermi_gas` (18 handwritten pages), Haiku `text`: `topics: []`,
`key_terms: []`, `lecture_title: null` instead of `"The Fermi gas"` and 10 topics.
Same for `ocw-7-29j-…_lecture3` and the scanned Ukrainian `zen-14978718-p006`.
*Why:* these PDFs have no text layer, the model only sees `[no text layer on this page]`.
It correctly does not invent content, but the document is lost. *Fix:* send page images —
`image` mode scores 0.92 on scans.

**2. Document type guessed without the layout.**
Haiku `text`: `ocw-10-37-lec10…`, `ocw-2-001-lec24`, `ocw-2-20-lecture12` →
`slides` instead of `lecture_notes`; `ocw-6-241j-…_lec03` → `lecture_notes` instead of
`slides`; the Ukrainian book excerpt `zen-14978718-p006` → `lecture_notes` instead of
`textbook_chapter`. *Why:* the text layer of terse notes (short lines, equations) looks
like slide bullets and the text of a slide deck looks like notes; landscape pages, running
book headers and title pages are only visible in the image. *Fix:* `image` mode
(`doc_type` 1.00 for all provider models).

**3. Hallucinated institution "MIT OpenCourseWare".**
Qwen3-VL 8B (v2 and v3): `institution: "MIT OpenCourseWare"` on `ocw-8-08-the_fermi_gas`,
`ocw-12-480-lecture_16` and `ocw-22-105-lecture4`, whose pages never mention MIT; it also
puts the lecture title into `course_title` (`"The Fermi gas"`, `"Conformal Mapping and
Green's Theorem"`). The provider models make the institution mistake only once, on
`ocw-7-03-lecture33_1`, whose only trace of MIT is the image credit "Figure by MIT OCW"
(Haiku and Sonnet: "MIT OpenCourseWare", GPT: "MIT OCW"). *Why:* the model recognises the
OCW style from pre-training and fills a plausible value instead of `null`; the golden rule
does not count image credits as an institution. v3 added "do not name an institution the
document does not name"; Qwen ignores it (same three documents, hallucination rate 34%),
and the provider models still read the image credit as an institution — the 7.03 case is
arguably a guide decision, not only a model error.

**4. Scribe instead of lecturer.**
`ocw-18-435j-qc_lec02`, Haiku `text`: `lecturers: ["Vitaly Feldman"]` instead of
`["P. Shor"]`, `course_title: null` instead of `"Quantum Computation"`. *Why:* the course
name and the lecturer are only in the page header image; the text layer starts with
"Lecture 2: Basics of Quantum Mechanics / Scribed by: Vitaly Feldman", so the only person
in the input is the scribe, and the model picks him despite the rule to exclude scribes.
`image` mode gets all three facts right.

**5. Qwen repetition loop → invalid output.**
Before the fix, Qwen3-VL 8B on `zen-23470007-p002` (a Ukrainian lecture with 36 footnotes)
generated `"Терепищий С. Філософія освіти… С. 476."`, `"… С. 23."`, `"… С. 358."`, … until
`max_tokens`; the JSON was cut off, the repair retry repeated it, the document was marked
`failed` (2–3 failures per run; `results/runs/_archive_pre_maxitems/`). *Why:* at
temperature 0 a small model falls into a loop on near-identical items, and nothing in a
JSON grammar ends a list. *Fix:* for grammar-based backends the list fields get
`maxItems` (topics ≤ 10, key terms ≤ 20, references ≤ 40, `LIST_LIMITS` in
`schema.py`) and `num_predict ≤ 4096`; after that every Qwen run is 100% valid.

Not model errors, but worth knowing when reading the tables:
- **Convention mismatches.** `course_code` "18.435/2.111" vs golden "18.435" (the guide
  takes the first of cross-listed codes), "24.244" (citation page) vs golden "Philosophy
  244" (header wins), `lecture_number` 5 from an unlabeled "#5". These cost ~0.05 on
  `course_code`/`lecture_number` for every model.
- **A metric bug found during the analysis.** Ukrainian "ґрунтових" vs "грунтових" (the same
  word in two spellings) scored 0.78 < 0.85 with `token_sort_ratio`, because "ґ" sorts
  after all Cyrillic letters and reorders the words. The metric now folds ґ → г
  (test in `tests/test_metrics.py`); all runs were re-scored.

## 5. Production choice

**Claude Haiku 5.5, `image` mode, prompt v3, effort `medium`.** It reaches 0.93 overall on
the golden set (and 0.93 on all 50 documents), 100% valid cards on the first attempt
(50/50),
1.00 on classification, 5–7% hallucinated facts, p50 ≈ 6–7 s / p95 ≈ 11–12 s per
document, at about **$2 per 1000 documents** — within 0.01–0.02 of Sonnet 5.5 (0.94–0.95)
at 1/17–1/23 of its cost, and handling scans, slides and Ukrainian books equally well.

I would change the decision if:
- **documents must not leave our infrastructure** → Qwen3-VL 8B `image` with prompt v2
  (0.78), but only with human review of the facts (22–28% hallucinated);
- **facts are published without human review** → Sonnet 5.5 `pdf` (0.95) or Haiku with
  `effort=high` (0.94, +16% cost, +40% latency);
- **the corpus is almost entirely born-digital text PDFs and cost dominates** → route by the
  manifest's `text_layer`/`layout`: `text` mode (≈ $1 per 1000) for text PDFs, `image` for
  scans and slides — after checking that `doc_type` errors (error 2) are acceptable;
- **Anthropic is unavailable or GPT gets cheaper** → GPT-6 Luna `image` is an equal
  fallback (0.92, $1.9 per 1000) behind the same interface;
- **volume grows to batch processing** → the same configuration through the Batch API
  (−50% cost, latency no longer matters).

## 6. Limitations

- 20 golden documents: differences below ~0.02 overall are within noise.
- Content lists are scored by fuzzy string matching; paraphrased topics count as misses
  (topics F1 0.79 for the chosen model partly reflects wording, not errors).
- Latency of local models was measured on an RTX 4090; the 4B model is the laptop option.
- Costs come from token usage and list prices (Oct 2026); OpenRouter bills ~12% more than
  list price.
- Stretch items: a third, cheap provider model (GPT-6 Luna), cached responses (results are
  reused by `main.py`) and a one-command regression run on the golden set
  (`python main.py --only <name> --force`).
