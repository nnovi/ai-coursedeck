"""Fetch dataset documents listed in a manifest that are not stored in the repo.

    python -m coursedeck.dataset.fetch data/manifests/dataset_200.csv

Each source PDF is downloaded, checked against `source_sha256`, and the lecture page range
is written to data/pdfs_extra/<doc_id>.pdf. Already present files are skipped.
"""

import argparse
import hashlib
import sys
import tempfile
import time
from pathlib import Path

import httpx

from coursedeck.dataset.manifest import ManifestRow, read_manifest
from coursedeck.dataset.pdf import extract_pages


def download(client: httpx.Client, url: str, retries: int = 5) -> bytes:
    for attempt in range(retries):
        r = client.get(url)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(60, 2 ** (attempt + 2)))
            continue
        return r.raise_for_status().content
    raise RuntimeError(f"failed to download {url}")


def fetch_row(client: httpx.Client, row: ManifestRow) -> None:
    data = download(client, row.pdf_url)
    digest = hashlib.sha256(data).hexdigest()
    if digest != row.source_sha256:
        raise ValueError(f"checksum mismatch: {digest} != {row.source_sha256}")
    row.path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "source.pdf"
        src.write_bytes(data)
        extract_pages(src, row.path, row.page_start, row.page_end)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("manifest", type=Path)
    args = ap.parse_args()

    rows = [r for r in read_manifest(args.manifest) if not r.path.exists()]
    missing_core = [r.doc_id for r in rows if r.in_repo]
    if missing_core:
        sys.exit(f"core documents missing from data/pdfs (check your checkout): {missing_core[:5]}")

    failed = 0
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for i, row in enumerate(rows, 1):
            try:
                fetch_row(client, row)
                print(f"[{i}/{len(rows)}] {row.doc_id}")
            except Exception as e:  # noqa: BLE001 - keep going, report at the end
                failed += 1
                print(f"[{i}/{len(rows)}] {row.doc_id} FAILED: {e}", file=sys.stderr)
            if row.source == "zenodo":
                time.sleep(2)  # Zenodo allows ~30 anonymous requests per minute
    print(f"done: {len(rows) - failed} fetched, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
