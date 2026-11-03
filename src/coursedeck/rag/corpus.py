"""RAG corpus manifest: one CSV row per source document, any format.

    python -m coursedeck.rag.corpus fetch      # download files missing from data/rag/raw/

PDF lecture notes are reused from the extraction dataset (data/pdfs/); HTML pages, DOCX and
PPTX files live in data/rag/raw/<format>/. Each row records where the file came from
(`url` = landing page, `file_url` = download link) and its SHA-256, so fetching is verifiable.
"""

import argparse
import csv
import hashlib
import sys
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import httpx

CORPUS_DIR = Path("data/rag")
RAW_DIR = CORPUS_DIR / "raw"
MANIFEST = CORPUS_DIR / "corpus.csv"
FORMATS = ("pdf", "html", "docx", "pptx")


@dataclass
class CorpusDoc:
    doc_id: str
    format: str  # pdf | html | docx | pptx
    kind: str  # lecture_notes | lecture_slides | course_home | syllabus | calendar | ...
    lang: str  # en | uk
    source: str  # ocw | zenodo
    license: str
    course_id: str  # OCW course number or Zenodo record id
    course_title: str
    title: str
    version: str  # course run ("Fall 2020") or publication date ("2024-08-18")
    year: int | None
    url: str  # landing page (attribution)
    file_url: str  # direct download link
    path: str  # local file, relative to the repo root
    sha256: str

    @property
    def file(self) -> Path:
        return Path(self.path)


FIELDS = [f.name for f in fields(CorpusDoc)]


def read_corpus(path: Path = MANIFEST) -> list[CorpusDoc]:
    with path.open(encoding="utf-8", newline="") as f:
        return [CorpusDoc(**{**r, "year": int(r["year"]) if r["year"] else None})
                for r in csv.DictReader(f)]


def write_corpus(rows: list[CorpusDoc], path: Path = MANIFEST) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for r in sorted(rows, key=lambda r: (FORMATS.index(r.format), r.doc_id)):
            w.writerow(asdict(r))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(client: httpx.Client, url: str, retries: int = 5) -> bytes:
    for attempt in range(retries):
        r = client.get(url)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(60, 2 ** (attempt + 2)))
            continue
        return r.raise_for_status().content
    raise RuntimeError(f"failed to download {url}")


def fetch(rows: list[CorpusDoc]) -> int:
    """Download rows whose file is missing; returns the number of failures."""
    missing = [r for r in rows if not r.file.exists()]
    failed = 0
    with httpx.Client(timeout=120, follow_redirects=True,
                      headers={"User-Agent": "coursedeck/0.1"}) as client:
        for i, r in enumerate(missing, 1):
            try:
                data = download(client, r.file_url)
                if r.format != "html" and sha256_bytes(data) != r.sha256:
                    raise ValueError("checksum mismatch")
                r.file.parent.mkdir(parents=True, exist_ok=True)
                r.file.write_bytes(data)
                print(f"[{i}/{len(missing)}] {r.doc_id}")
            except Exception as e:  # noqa: BLE001 - keep going, report at the end
                failed += 1
                print(f"[{i}/{len(missing)}] {r.doc_id}: {type(e).__name__}: {e}", file=sys.stderr)
    return failed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("command", choices=["fetch"])
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    args = ap.parse_args()
    if fetch(read_corpus(args.manifest)):
        sys.exit(1)


if __name__ == "__main__":
    main()
