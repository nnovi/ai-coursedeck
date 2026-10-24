# Extraction prompt changelog

The JSON schema (`coursedeck.schema.LectureCard`, including field descriptions) is sent with
every prompt version as the structured-output format.

## v3 — file name fallback, term rule, anti-hallucination
- The source file name is sent with the document (`Source file name: ...`) and may fill a
  fact the content lacks (e.g. `lecture_16.pdf` → lecture 16); the content always wins.
- term: any term stated in the document for the chosen year (e.g. the OCW citation page),
  never inferred from a month.
- Explicit "do not name an institution or course the document does not name" and "a
  lecture title is not a course title": the two most frequent hallucinations of Qwen3-VL
  with v2.
- Matches the annotation-guide update of 2026-10-24.

## v2 — annotation rules
- Adds the rules of the golden-set annotation guide (`data/golden/README.md`): source
  priority for facts, what counts as a lecture number, lecturer exclusions, the discipline
  table, doc_type definitions, and the content-list rules.
- Purpose: the model and the ground truth use the same definitions; v1 → v2 measures how
  much the explicit rules are worth.

## v1 — baseline
- Role, document kinds, "only what the document shows", null when absent, document language
  for content fields. Field semantics come only from the schema descriptions.
