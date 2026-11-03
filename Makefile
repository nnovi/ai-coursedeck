.PHONY: install run run-local score test ingest

install:
	python -m venv .venv
	.venv/bin/pip install -e ".[dev]" || .venv/Scripts/pip install -e ".[dev]"

run:          ## run missing API experiments and score everything
	python main.py

run-local:    ## also run local Ollama experiments
	python main.py --local

score:        ## recompute metrics from saved results only
	python main.py --score-only

ingest:       ## RAG corpus: fetch missing files, parse, clean, dedup, chunk
	python -m coursedeck.rag.corpus fetch
	python -m coursedeck.rag.ingest

test:
	python -m pytest -q
