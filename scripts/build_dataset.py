"""Build the CourseDeck dataset from the source indexes (see collect_sources.py).

Steps (each caches its output in data/cache/ and can be re-run independently):
    candidates  pick an ordered, department-balanced candidate list
    download    download candidate PDFs into data/cache/src/
    inspect     inspect PDFs; split Ukrainian course books into lecture units
    select      fill nested tiers (50/100/200/500), pick the golden set,
                write data/manifests/*.csv and copy the core tier into data/pdfs/
"""

import argparse
import hashlib
import json
import random
import re
import shutil
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pymupdf

from coursedeck.dataset.manifest import PDF_DIR, ManifestRow, write_manifest
from coursedeck.dataset.pdf import extract_pages, format_pages, inspect_pdf, to_ranges

CACHE = Path("data/cache")
SRC_DIR = CACHE / "src"
MANIFEST_DIR = Path("data/manifests")
SEED = 42

TIERS = [50, 100, 200, 500]
UK_PER_TIER = {50: 12, 100: 20, 200: 35, 500: 60}
# Minimum share of hard English documents per tier.
EN_SCAN_SHARE = 0.12
EN_SLIDES_SHARE = 0.15
MIN_PAGES, MAX_PAGES = 2, 30
GOLDEN_MIN_PAGES = 3
MAX_SOURCE_MB = 60
# Hand-picked pages for scanned books that have no text to segment on:
# {"cand_id": {"front": [title pages], "lectures": [[start, end, "heading"], ...]}}
MANUAL_SEGMENTS = Path("scripts/manual_segments.json")
MAX_FRONT_PAGES = 3  # cover, title page, reverse of the title page
FRONT_STOP_RE = re.compile(
    r"^\s*(?:ЗМІСТ|ЗМIСТ|Зміст|ПЕРЕДМОВА|Передмова|ВСТУП|Вступ|ПЕРЕЛІК\s+УМОВНИХ|СПИСОК\s+СКОРОЧЕНЬ)",
    re.MULTILINE,
)
# Documents rejected on manual review: {"cand_id": "reason"}
EXCLUDE = Path("scripts/exclude.json")

GOLDEN = {"en": {"scan": 3, "slides": 3, "notes": 8}, "uk": {"any": 6}}

OCW_SKIP_RE = re.compile(
    r"syllabus|problem set|pset|solution|exam|quiz|homework|assignment|calendar|reading list",
    re.IGNORECASE,
)
ZEN_EDU_RE = re.compile(
    r"конспект|лекці|посібник|навчальн\w* (?:дисциплін|видання)|матеріали навчальної"
    r"|course of lectures",
    re.IGNORECASE,
)
ZEN_SKIP_RE = re.compile(r"рецензі|р е ц е н з і я", re.IGNORECASE)

# Lecture heading near the top of a page: "ЛЕКЦІЯ 3", "Лекція № 3", "ТЕМА 2.", "Розділ IV"
LECTURE_START_RE = re.compile(
    r"^\s*(?:ЛЕКЦІЯ|Лекція|ТЕМА|Тема|РОЗДІЛ|Розділ)\s*(?:№\s*)?(\d{1,2}|[IVXІ]{1,4})\b", re.MULTILINE
)
HEAD_CHARS = 1000  # how far from the top of a page a lecture heading may appear
# Outline entries that are front/back matter or subsections ("2.1 ...") rather than lectures
TOC_SKIP_RE = re.compile(
    r"^\s*(?:\d+\.\d|зміст|вступ|передмова|титульн|список|література|додат|покажчик|відомості"
    r"|рекомендована|питання для|зміст лекції|ключові поняття|після лекції)",
    re.IGNORECASE,
)
BACK_MATTER_RE = re.compile(
    r"^\s*(?:СПИСОК\s+(?:ВИКОРИСТАНОЇ\s+)?ЛІТЕРАТУРИ|ЛІТЕРАТУРА|ДОДАТКИ?|ПРЕДМЕТНИЙ\s+ПОКАЖЧИК)\s*$",
    re.MULTILINE,
)


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows -> {path}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def round_robin(groups: dict[str, list]) -> list:
    """Interleave lists: one item from each group in turn."""
    out, queues = [], [list(g) for g in groups.values()]
    while any(queues):
        for q in queues:
            if q:
                out.append(q.pop(0))
    return out


# --------------------------------------------------------------------------- candidates


def ocw_candidates(rng: random.Random, per_course: int = 2) -> list[dict]:
    index = read_jsonl(CACHE / "ocw_index.jsonl")
    latest: dict[str, str] = {}  # course_number -> run_slug of the newest run
    runs: dict[str, list[dict]] = defaultdict(list)
    for r in index:
        if OCW_SKIP_RE.search(r["title"]):
            continue
        runs[r["run_slug"]].append(r)
        cur = latest.get(r["course_number"])
        if cur is None or (r["year"] or 0) > (runs[cur][0]["year"] or 0):
            latest[r["course_number"]] = r["run_slug"]

    picks_by_round: list[dict[str, list]] = [defaultdict(list) for _ in range(per_course)]
    for slug in sorted(set(latest.values())):
        files = sorted(runs[slug], key=lambda r: r["key"])
        rng.shuffle(files)
        dept = (files[0]["departments"] or ["Other"])[0]
        for i, f in enumerate(files[:per_course]):
            picks_by_round[i][dept].append(f)

    out = []
    for groups in picks_by_round:  # first one lecture per course, then the second
        for dept_list in groups.values():
            rng.shuffle(dept_list)
        for f in round_robin(dict(sorted(groups.items()))):
            # file names repeat across courses (lecture_5.pdf), so prefix the course number
            course = re.sub(r"[^a-z0-9]+", "-", (f["course_number"] or "").lower()).strip("-")
            stem = f["key"].rstrip("/").split("/")[-1].removesuffix("_pdf")
            out.append({
                "cand_id": f"ocw-{course}-{stem}",
                "source": "ocw",
                "lang": "en",
                "license": "cc-by-nc-sa-4.0",
                "page_url": f["page_url"],
                "pdf_url": None,  # resolved during download
                "course_id": f["course_number"],
                "group": f["course_number"],
                "course_title": f["course_title"],
                "department": (f["departments"] or [""])[0],
                "title": re.sub(r"\s*\(PDF\)\s*$", "", f["title"]),
            })
    return out


def zenodo_candidates() -> list[dict]:
    out = []
    for r in read_jsonl(CACHE / "zenodo_index.jsonl"):
        if not ZEN_EDU_RE.search(r["title"]) or ZEN_SKIP_RE.search(r["title"]):
            continue
        if "-nd-" in r["license"]:  # NoDerivatives: cutting out a lecture is an adaptation
            continue
        for i, f in enumerate(r["files"]):
            if f["size"] > MAX_SOURCE_MB * 1e6:
                continue
            out.append({
                "cand_id": f"zen-{r['record_id']}" + (f"-f{i}" if len(r["files"]) > 1 else ""),
                "source": "zenodo",
                "lang": "uk",
                "license": r["license"],
                "page_url": r["page_url"],
                "pdf_url": f["url"],
                "course_id": str(r["record_id"]),
                # one author often uploads the same course several times
                "group": (r["creators"] or [str(r["record_id"])])[0],
                "course_title": r["title"],
                "department": "",
                "title": r["title"],
            })
    return out


def cmd_candidates(_: argparse.Namespace) -> None:
    rng = random.Random(SEED)
    cands = ocw_candidates(rng) + zenodo_candidates()
    ids = [c["cand_id"] for c in cands]
    assert len(ids) == len(set(ids)), "candidate ids must be unique (they name cached files)"
    write_jsonl(CACHE / "candidates.jsonl", cands)


# --------------------------------------------------------------------------- download

OCW_PDF_HREF_RE = re.compile(r'href="(/courses/[^"]+?\.pdf)"', re.IGNORECASE)


def resolve_ocw_pdf(client: httpx.Client, page_url: str) -> str:
    html = client.get(page_url).raise_for_status().text
    m = OCW_PDF_HREF_RE.search(html)
    if not m:
        raise ValueError("no PDF link on resource page")
    return "https://ocw.mit.edu" + m.group(1)


def download_one(client: httpx.Client, c: dict) -> dict:
    dst = SRC_DIR / f"{c['cand_id']}.pdf"
    try:
        if not dst.exists():
            url = c["pdf_url"] or resolve_ocw_pdf(client, c["page_url"])
            for attempt in range(5):
                r = client.get(url)
                if r.status_code == 429:
                    time.sleep(60)
                    continue
                r.raise_for_status()
                break
            if not r.content.startswith(b"%PDF"):
                raise ValueError("not a PDF")
            dst.write_bytes(r.content)
            c = {**c, "pdf_url": url}
        return {**c, "file": str(dst), "source_sha256": sha256(dst), "error": None}
    except Exception as e:  # noqa: BLE001 - record and move on
        return {**c, "file": None, "error": f"{type(e).__name__}: {e}"}


def cmd_download(args: argparse.Namespace) -> None:
    cands = read_jsonl(CACHE / "candidates.jsonl")
    ocw = [c for c in cands if c["source"] == "ocw"][: args.limit_ocw]
    zen = [c for c in cands if c["source"] == "zenodo"]
    prev = {}
    if (CACHE / "downloads.jsonl").exists():
        prev = {d["cand_id"]: d for d in read_jsonl(CACHE / "downloads.jsonl") if d["file"]}
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        todo = [c for c in ocw if c["cand_id"] not in prev]
        with ThreadPoolExecutor(8) as pool:
            for i, d in enumerate(pool.map(lambda c: download_one(client, c), todo), 1):
                results.append(d)
                print(f"ocw {i}/{len(todo)}", end="\r")
        print()
        for i, c in enumerate([c for c in zen if c["cand_id"] not in prev], 1):
            results.append(download_one(client, c))  # sequential: Zenodo rate limits
            print(f"zenodo {i}", end="\r")
            time.sleep(2)
        print()
    # keep download info for cached files but refresh their candidate metadata
    keep = ("pdf_url", "file", "source_sha256", "error")
    results = [{**c, **{k: prev[c["cand_id"]][k] for k in keep}}
               for c in ocw + zen if c["cand_id"] in prev] + results
    errors = [d for d in results if d["error"]]
    print(f"downloaded {len(results) - len(errors)}, errors {len(errors)}")
    for d in errors[:10]:
        print("  ", d["cand_id"], d["error"])
    write_jsonl(CACHE / "downloads.jsonl", results)


# --------------------------------------------------------------------------- inspect


def _text_starts(doc: pymupdf.Document) -> list[tuple[int, str]]:
    """Pages whose top contains a lecture heading."""
    starts: list[tuple[int, str]] = []
    for i in range(doc.page_count):
        text = doc[i].get_text()
        if len(set(LECTURE_START_RE.findall(text))) >= 3:  # table of contents page
            continue
        head = text.strip()[:HEAD_CHARS]
        m = LECTURE_START_RE.search(head)
        if m and (not starts or starts[-1][1] != m.group(1)):
            line = " ".join(head[m.start():].lstrip().split("\n")[:2]).strip()
            starts.append((i + 1, m.group(1), line[:120]))
    return [(p, line) for p, _, line in starts]


def _toc_starts(doc: pymupdf.Document) -> list[tuple[int, str]]:
    """Top-level outline entries that look like lectures."""
    toc = [(lvl, t.strip(), p) for lvl, t, p in doc.get_toc() if p > 0]
    if not toc:
        return []
    top = min(lvl for lvl, _, _ in toc)
    starts: list[tuple[int, str]] = []
    for lvl, title, page in toc:
        if lvl != top or TOC_SKIP_RE.search(title) or (starts and starts[-1][0] == page):
            continue
        starts.append((page, title[:120]))
    return starts


def front_matter_pages(doc: pymupdf.Document, lecture_start: int) -> list[int]:
    """Leading title pages of a book (cover, title page, its reverse), up to MAX_FRONT_PAGES.

    They carry the course name, authors, institution and year, which a lecture cut out of
    the middle of the book would otherwise lose.
    """
    pages = []
    for i in range(min(MAX_FRONT_PAGES, lecture_start - 1)):
        head = doc[i].get_text().strip()[:HEAD_CHARS]
        if FRONT_STOP_RE.search(head) or LECTURE_START_RE.search(head):
            break
        pages.append(i + 1)
    return pages


def _back_matter_page(doc: pymupdf.Document) -> int:
    n = doc.page_count
    for i in range(n // 2, n):
        if BACK_MATTER_RE.search(doc[i].get_text().strip()[:HEAD_CHARS]):
            return i + 1
    return n + 1


def _to_segments(starts: list[tuple[int, str]], end_page: int) -> list[tuple[int, int, str]]:
    segs = []
    for k, (s, title) in enumerate(starts):
        e = starts[k + 1][0] - 1 if k + 1 < len(starts) else end_page
        if e >= s:
            segs.append((s, e, title))
    return segs


def lecture_segments(path: Path) -> list[tuple[int, int, str]]:
    """Split a Ukrainian course book into lectures: [(start, end, heading)], 1-based inclusive.

    Tries page headings and the PDF outline; keeps whichever yields more lectures of a
    usable length.
    """
    with pymupdf.open(path) as doc:
        end_page = _back_matter_page(doc) - 1
        candidates = [_to_segments(s, end_page) for s in (_text_starts(doc), _toc_starts(doc))]

    def ok(segs: list) -> list:
        return [s for s in segs if MIN_PAGES <= s[1] - s[0] + 1 <= MAX_PAGES]

    return max((ok(c) for c in candidates), key=len)


def spread(items: list, k: int) -> list:
    """Pick k items spread evenly over the list (first, middle, last, ...)."""
    if len(items) <= k:
        return items
    step = (len(items) - 1) / (k - 1) if k > 1 else 0
    return [items[round(i * step)] for i in range(k)]


def book_units(path: Path, manual: dict | None, per_book: int) -> list[tuple[list[int], int, int, str]]:
    """[(front_pages, start, end, heading)] for the lectures taken from one course book."""
    if manual:
        segs = [tuple(s) for s in manual["lectures"]]
    else:
        segs = lecture_segments(path)
    out = []
    with pymupdf.open(path) as doc:
        for s, e, title in spread(segs, per_book):
            front = ([p for p in manual["front"] if p < s] if manual
                     else front_matter_pages(doc, s))
            out.append((front, s, e, title))
    return out


def cmd_inspect(args: argparse.Namespace) -> None:
    manual = json.loads(MANUAL_SEGMENTS.read_text("utf-8")) if MANUAL_SEGMENTS.exists() else {}
    units = []
    for d in read_jsonl(CACHE / "downloads.jsonl"):
        if not d["file"]:
            continue
        path = Path(d["file"])
        try:
            if d["source"] == "ocw":
                info = inspect_pdf(path)
                units.append({**d, "page_start": 1, "page_end": info.n_pages,
                              "lecture_title": d["title"], **info.to_dict()})
                continue
            lectures = book_units(path, manual.get(d["cand_id"]), args.per_book)
            if not lectures:
                info = inspect_pdf(path)
                units.append({**d, "page_start": 1, "page_end": info.n_pages,
                              "lecture_title": "", "unsegmented": True, **info.to_dict()})
                continue
            for rank, (front, s, e, title) in enumerate(lectures):
                info = inspect_pdf(path, s, e)  # stats describe the lecture, not the title pages
                units.append({**d, "cand_id": f"zen-{d['course_id']}-p{s:03d}", "rank": rank,
                              "front_pages": front, "page_start": s, "page_end": e,
                              "lecture_title": title, **info.to_dict()})
        except Exception as ex:  # noqa: BLE001
            print("  inspect failed", d["cand_id"], ex)
    write_jsonl(CACHE / "units.jsonl", units)


# --------------------------------------------------------------------------- select


def kind(u: dict) -> str:
    # Landscape decks without text are photo/figure slides, not scans.
    if u["landscape_ratio"] >= 0.8:
        return "slides"
    return "scan" if u["text_layer"] == "none" else "notes"


def usable(u: dict) -> str | None:
    """Return a rejection reason, or None if the unit is usable."""
    if u.get("unsegmented"):
        return "unsegmented"
    if u["encrypted"]:
        return "encrypted"
    if not MIN_PAGES <= u["n_pages"] <= MAX_PAGES:
        return "page_count"
    if u["third_party"]:
        return "third_party"
    if kind(u) != "scan" and u["lang_guess"] not in (u["lang"], "unknown"):
        return f"lang_{u['lang_guess']}"
    return None


def cmd_select(_: argparse.Namespace) -> None:
    excluded = json.loads(EXCLUDE.read_text("utf-8")) if EXCLUDE.exists() else {}
    units = read_jsonl(CACHE / "units.jsonl")
    unknown = set(excluded) - {u["cand_id"] for u in units}
    assert not unknown, f"exclude.json lists unknown ids: {unknown}"
    units = [u for u in units if u["cand_id"] not in excluded]
    rejected: dict[str, int] = defaultdict(int, manual=len(excluded))
    pools: dict[tuple[str, str], list[dict]] = defaultdict(list)
    seen: set[str] = set()
    for u in units:
        # same text, or (for course books) the same lecture heading reused across courses
        keys = {u["fingerprint"]} if u["fingerprint"] else set()
        if u["source"] == "zenodo" and u["lecture_title"]:
            keys.add(re.sub(r"\W+", "", u["lecture_title"].lower()))
        reason = usable(u) or ("duplicate" if keys & seen else None)
        seen |= keys
        if reason:
            rejected[reason] += 1
            continue
        pools[(u["lang"], "any" if u["lang"] == "uk" else kind(u))].append(u)
    print("rejected:", dict(rejected))
    print("pools:", {k: len(v) for k, v in pools.items()})
    # Ukrainian units: one lecture per book first, then the second, ...; scans are rare,
    # so they go first within each round
    pools[("uk", "any")].sort(key=lambda u: (u.get("rank", 0), kind(u) != "scan"))

    taken: list[dict] = []
    for tier in TIERS:
        uk_n = UK_PER_TIER[tier]
        en_n = tier - uk_n
        targets = {
            ("uk", "any"): uk_n,
            ("en", "scan"): round(en_n * EN_SCAN_SHARE),
            ("en", "slides"): round(en_n * EN_SLIDES_SHARE),
        }
        targets[("en", "notes")] = en_n - targets[("en", "scan")] - targets[("en", "slides")]
        have = defaultdict(int)
        for u in taken:
            have[u["stratum"]] += 1
        for stratum, n in targets.items():
            pool = pools[stratum]
            while have[stratum] < n and pool:
                u = pool.pop(0)
                taken.append({**u, "stratum": stratum, "tier": tier})
                have[stratum] += 1
        # backfill shortfalls (e.g. too few Ukrainian lectures) with English notes
        while len(taken) < tier and pools[("en", "notes")]:
            taken.append({**pools[("en", "notes")].pop(0), "stratum": ("en", "notes"),
                          "tier": tier})
        print(f"tier {tier}: {len(taken)} docs", dict(have))

    golden_ids = pick_golden([u for u in taken if u["tier"] == TIERS[0]])
    rows = [to_row(u, golden=u["cand_id"] in golden_ids) for u in taken]

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    for stale in PDF_DIR.glob("*.pdf"):
        stale.unlink()
    for r, u in zip(rows, taken):
        if r.in_repo:
            if u["source"] == "ocw":
                shutil.copyfile(u["file"], r.path)
            else:
                extract_pages(Path(u["file"]), r.path, r.page_ranges)
    for tier in TIERS:
        write_manifest(MANIFEST_DIR / f"dataset_{tier:03d}.csv", [r for r in rows if r.tier <= tier])
    write_manifest(MANIFEST_DIR / "golden.csv", [r for r in rows if r.golden])
    print("golden:", len(golden_ids))


def pick_golden(core: list[dict]) -> set[str]:
    chosen, groups = [], set()
    for lang, quotas in GOLDEN.items():
        for k, n in quotas.items():
            pool = [
                u for u in core
                if u["lang"] == lang and (k == "any" or kind(u) == k)
                and u["n_pages"] >= GOLDEN_MIN_PAGES
            ]
            # math-heavy documents first so the golden set exercises formula extraction;
            # for "any", scans first so Ukrainian scans are covered too
            pool.sort(key=lambda u: (kind(u) != "scan", -min(u["math_symbols"], 50)))
            for u in pool:
                if n == 0:
                    break
                if u["group"] not in groups:
                    chosen.append(u["cand_id"])
                    groups.add(u["group"])
                    n -= 1
            if n:
                print(f"golden: {n} short in {lang}/{k}")
    return set(chosen)


def to_row(u: dict, golden: bool) -> ManifestRow:
    ranges = to_ranges(u.get("front_pages", []) + list(range(u["page_start"], u["page_end"] + 1)))
    return ManifestRow(
        doc_id=u["cand_id"],
        lang=u["lang"],
        source=u["source"],
        license=u["license"],
        course_id=u["course_id"],
        course_title=u["course_title"],
        department=u["department"],
        lecture_title=u["lecture_title"],
        source_url=u["page_url"],
        pdf_url=u["pdf_url"],
        source_sha256=u["source_sha256"],
        pages=format_pages(ranges),
        n_pages=sum(e - s + 1 for s, e in ranges),
        text_layer=u["text_layer"],
        layout="slides" if u["landscape_ratio"] >= 0.8 else "notes",
        math_heavy=u["math_symbols"] >= 30,
        in_repo=u["tier"] == TIERS[0],
        golden=golden,
        tier=u["tier"],
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("candidates").set_defaults(fn=cmd_candidates)
    p = sub.add_parser("download")
    p.add_argument("--limit-ocw", type=int, default=900, help="OCW candidates to download")
    p.set_defaults(fn=cmd_download)
    p = sub.add_parser("inspect")
    p.add_argument("--per-book", type=int, default=3, help="lectures to take per course book")
    p.set_defaults(fn=cmd_inspect)
    sub.add_parser("select").set_defaults(fn=cmd_select)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
