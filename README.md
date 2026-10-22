# CourseDeck

Teacher assistant: from a lecture-notes PDF to a structured lecture card and a presentation draft in Visme.

Stages:
1. **Extraction**: PDF → lecture card (Pydantic schema, structured output).
2. **RAG**: search over lecture-note chunks with document/page citations.
3. **Agent**: builds a presentation draft from retrieved material.
4. **Service**: FastAPI, batch processing of new documents.

## Layout

```
src/coursedeck/   package code
data/raw/         source PDFs (Creative Commons licensed, committed)
data/golden/      hand-labelled golden set
scripts/          dataset collection and utilities
tests/
```

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use .venv/bin/activate elsewhere
pip install -e ".[dev]"
```
