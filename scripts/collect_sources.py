"""Collect candidate lecture-note PDFs from MIT OCW and Zenodo into local JSONL indexes.

Output (not committed, regenerated on demand):
    data/cache/ocw_index.jsonl
    data/cache/zenodo_index.jsonl
"""

import argparse
import json
import re
import time
from pathlib import Path

import httpx

CACHE = Path("data/cache")

OCW_API = "https://api.learn.mit.edu/api/v1/contentfiles/"
ZENODO_API = "https://zenodo.org/api/records"

# Ukrainian phrases that mark lecture notes / course textbooks on Zenodo.
ZENODO_QUERIES = [
    '"конспект лекцій"',
    '"курс лекцій"',
    '"схемоконспект лекцій"',
    '"лекція"',
    '"лекції"',
    '"навчальний посібник"',
    '"текст лекцій"',
    '"опорний конспект"',
]
ZENODO_PAGE = 25  # max page size for anonymous requests
UK_LETTERS_RE = re.compile(r"[іїєґ]", re.IGNORECASE)
OPEN_LICENSES = ("cc-by", "cc0")  # prefix match: cc-by-4.0, cc-by-sa-4.0, cc0-1.0, ...


def get_json(client: httpx.Client, url: str, params: dict | None = None, retries: int = 5) -> dict:
    """GET with backoff on 429/5xx (Zenodo allows 30 anonymous requests per minute)."""
    for attempt in range(retries):
        r = client.get(url, params=params)
        if r.status_code == 429:
            reset = float(r.headers.get("X-RateLimit-Reset", 0))
            time.sleep(max(reset - time.time(), 0) + 5 if reset else 65)
            continue
        if r.status_code >= 500:
            time.sleep(2 ** (attempt + 2))
            continue
        return r.raise_for_status().json()
    r.raise_for_status()
    raise RuntimeError(f"gave up on {url}")


def collect_ocw(client: httpx.Client) -> list[dict]:
    rows, url = [], OCW_API
    params = {"platform": "ocw", "content_feature_type": "Lecture Notes", "limit": 100}
    while url:
        page = get_json(client, url, params)
        params = None  # `next` already carries the query string
        for x in page["results"]:
            if x.get("file_extension") != ".pdf":
                continue
            rows.append({
                "key": x["key"],
                "page_url": x["url"],
                "title": x["title"],
                "run_slug": x["run_slug"],
                "course_title": x["run_title"],
                "course_number": (x.get("course_number") or [None])[0],
                "departments": [d["name"] for d in x.get("departments") or []],
                "topics": [t["name"] for t in x.get("topics") or [] if t.get("parent") is None],
                "semester": x.get("semester"),
                "year": x.get("year"),
            })
        url = page["next"]
        print(f"ocw: {len(rows)} / {page['count']}", end="\r")
    print()
    return rows


def collect_zenodo(client: httpx.Client) -> list[dict]:
    seen: dict[int, dict] = {}
    for q in ZENODO_QUERIES:
        page_no = 1
        while True:
            r = get_json(client, ZENODO_API, {
                "q": q, "size": ZENODO_PAGE, "page": page_no,
            })
            time.sleep(2.5)
            hits = r["hits"]["hits"]
            for h in hits:
                m = h["metadata"]
                lic = (m.get("license") or {}).get("id", "")
                pdfs = [
                    {"key": f["key"], "size": f["size"], "url": f["links"]["self"]}
                    for f in h.get("files", [])
                    if f["key"].lower().endswith(".pdf")
                ]
                if not pdfs or not lic.startswith(OPEN_LICENSES):
                    continue
                # Language metadata is often missing, so detect Ukrainian by its letters.
                if not UK_LETTERS_RE.search(m["title"]):
                    continue
                seen[h["id"]] = {
                    "record_id": h["id"],
                    "page_url": h["links"]["self_html"],
                    "doi": h.get("doi"),
                    "title": m["title"],
                    "license": lic,
                    "resource_type": m["resource_type"]["type"],
                    "creators": [c["name"] for c in m.get("creators", [])],
                    "publication_date": m.get("publication_date"),
                    "files": pdfs,
                }
            if len(hits) < ZENODO_PAGE:
                break
            page_no += 1
        print(f"zenodo: {q} -> {len(seen)} records total")
    return list(seen.values())


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows -> {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=["ocw", "zenodo", "all"], default="all")
    args = ap.parse_args()
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        if args.source in ("ocw", "all"):
            write_jsonl(CACHE / "ocw_index.jsonl", collect_ocw(client))
        if args.source in ("zenodo", "all"):
            write_jsonl(CACHE / "zenodo_index.jsonl", collect_zenodo(client))


if __name__ == "__main__":
    main()
