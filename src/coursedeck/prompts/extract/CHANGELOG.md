# Extraction prompt changelog

The JSON schema (`coursedeck.schema.LectureCard`, including field descriptions) is sent with
every prompt version as the structured-output format.

## v2 — annotation rules
- Adds the rules of the golden-set annotation guide (`data/golden/README.md`): source
  priority for facts, what counts as a lecture number, lecturer exclusions, the discipline
  table, doc_type definitions, and the content-list rules.
- Purpose: the model and the ground truth use the same definitions; v1 → v2 measures how
  much the explicit rules are worth.

## v1 — baseline
- Role, document kinds, "only what the document shows", null when absent, document language
  for content fields. Field semantics come only from the schema descriptions.
