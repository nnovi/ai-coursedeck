"""Build the RAG corpus manifest (data/rag/corpus.csv) and download its non-PDF files.

    python scripts/build_rag_corpus.py

The corpus is centred on courses, so questions can need several documents and formats:
- PDF: lecture notes with a text layer from the extraction dataset (tier 50, data/pdfs/);
- HTML: OCW course pages (home, syllabus, calendar) of the courses those notes come from,
  plus older runs of some courses (same course number, different year) as "outdated
  version" distractors;
- PPTX: OCW and Zenodo lecture slides (English and Ukrainian);
- DOCX: Zenodo lecture texts and course material (English and Ukrainian).

Selection is curated below; licenses are CC BY / CC BY-SA / CC BY-NC-SA (no NoDerivatives).
"""

import csv
import json
import re
from pathlib import Path
from urllib.parse import unquote

import httpx

from coursedeck.rag.corpus import RAW_DIR, CorpusDoc, download, sha256_bytes, write_corpus
from coursedeck.rag.parse import parse

DATASET = Path("data/manifests/dataset_050.csv")
ZENODO_INDEX = Path("data/cache/zenodo_index.jsonl")
GOLDEN_DIR = Path("data/golden")
OCW = "https://ocw.mit.edu/courses/"
OCW_LICENSE = "cc-by-nc-sa-4.0"
MAX_FILE_BYTES = 15_000_000

# OCW course runs whose pages go into the corpus: course_number -> run slugs.
# Runs of golden-set PDF courses are added automatically from the dataset manifest.
EXTRA_RUNS = {
    "18.404J": ["18-404j-theory-of-computation-fall-2020"],
    "12.010": ["12-010-computational-methods-of-scientific-programming-fall-2024",
               "12-010-computational-methods-of-scientific-programming-fall-2011"],  # older run
    "CMS.595": ["cms-595-learning-media-and-technology-spring-2024"],
    "6.007": ["6-007-electromagnetic-energy-from-motors-to-lasers-spring-2011"],
    "RES.11-003": ["res-11-003-climate-justice-instructional-toolkit-spring-2025"],
    "5.13": ["5-13-organic-chemistry-ii-fall-2006", "5-13-organic-chemistry-ii-fall-2003"],
    "PE.550": ["pe-550-designing-your-life-spring-2009",
               "pe-550-designing-your-life-january-iap-2007"],
}
OCW_PAGES = {"course_home": "", "syllabus": "pages/syllabus/", "calendar": "pages/calendar/"}

# OCW lecture slides: run slug -> resource page slugs.
OCW_SLIDES = {
    "18-404j-theory-of-computation-fall-2020": [
        "mit18_404f20_lec1", "mit18_404f20_lec2", "mit18_404f20_lec3", "mit18_404f20_lec4",
        "mit18_404f20_lec8", "mit18_404f20_lec12"],
    "12-010-computational-methods-of-scientific-programming-fall-2024": [
        "mit12_010_f24_lec01_pptx", "mit12_010_f24_lec02_pptx", "mit12_010_f24_lec05_pptx",
        "mit12_010_f24_lec10_pptx"],
    "cms-595-learning-media-and-technology-spring-2024": [
        "mitcms_595_s24_ses1_pptx", "mitcms_595_s24_ses2_pptx", "mitcms_595_s24_ses3_pptx"],
    "6-007-electromagnetic-energy-from-motors-to-lasers-spring-2011": [
        "mit6_007s11_lec01-1", "mit6_007s11_lec02-1"],
    # "X" and "X 2.0" decks: near-duplicate versions of one lecture
    "res-11-003-climate-justice-instructional-toolkit-spring-2025": [
        "mitres_11_003_s25_introduction_climate_justice_pptx",
        "mitres_11_003_s25_mapping_environmental_justice_pptx",
        "mitres_11_003_s25_mapping_environmental_justice2_pptx",
        "mitres_11_003_s25_engineering_climate_justice_pptx",
        "mitres_11_003_s25_engineering_climate_justice2_pptx"],
}

# Zenodo records: id -> (lang, kind, file-name regex)
ZENODO_FILES = {
    # Ukrainian
    13370817: ("uk", "lecture_text", r"\.docx$"),  # Danylevskyi, lecture 1 (1921)
    13952149: ("uk", "lecture_text", r"\.docx$"),  # Danylevskyi, lecture 2
    14171838: ("uk", "lecture_text", r"\.docx$"),  # Danylevskyi, lecture 3
    22272798: ("uk", "lecture_notes", r"\.docx$"),  # career counselling, lecture texts
    21074760: ("uk", "lecture_slides", r"\.pptx$"),  # marketing, lecture 2
    21157343: ("uk", "lecture_slides", r"\.pptx$"),  # marketing, lecture 4
    21332548: ("uk", "lecture_slides", r"\.pptx$"),  # marketing, lecture 5
    21952908: ("uk", "lecture_slides", r"\.pptx$"),  # marketing, lecture 6
    # English
    20835946: ("en", "lecture_notes", r"\.docx$"),  # history of Christian theology
    3366923: ("en", "schedule", r"Course Schedule\.docx$"),  # data structures course
    15370436: ("en", "workbook", r"workbook.*\.docx$"),  # amino acids: workbook + answers
    19944360: ("en", "lecture_slides", r"Lecture-[24]\.pptx$"),  # energy system modelling
}

SEASON_RE = re.compile(r"(fall|spring|summer|january-iap)-(\d{4})$")


def run_version(slug: str) -> tuple[str, int | None]:
    m = SEASON_RE.search(slug)
    if not m:
        return "", None
    season = {"january-iap": "January IAP"}.get(m.group(1), m.group(1).title())
    return f"{season} {m.group(2)}", int(m.group(2))


def short_run(slug: str) -> str:
    """'18-310-principles-of-...-fall-2013' -> '18-310-f13'."""
    num = re.match(r"(?:[a-z]+-)?\d+[a-z]?-\d+[a-z]?|[a-z]+-\d+[a-z]?", slug).group(0)
    m = SEASON_RE.search(slug)
    tag = {"fall": "f", "spring": "s", "summer": "su", "january-iap": "iap"}[m.group(1)]
    return f"{num}-{tag}{m.group(2)[2:]}"


# "lec10.pdf", "MIT6_241JS11_lec03", "Microsoft Word - Document3"
FILE_NAME_RE = re.compile(r"\.\w{3,4}$|^[\w.-]+$|^Microsoft (?:Word|PowerPoint) - ")


def pdf_title(row: dict) -> str:
    """Lecture title: the reviewed golden card if there is one; an OCW resource title that is
    only a file name is replaced by the PDF's metadata title or its first heading."""
    golden = GOLDEN_DIR / f"{row['doc_id']}.json"
    if golden.exists():
        card = json.loads(golden.read_text(encoding="utf-8"))["card"]
        if card.get("lecture_title"):
            return card["lecture_title"]
    title = row["lecture_title"]
    if not FILE_NAME_RE.search(title):
        return title
    parsed = parse(Path(f"data/pdfs/{row['doc_id']}.pdf"), "pdf")
    if parsed.title and not FILE_NAME_RE.search(parsed.title) and len(parsed.title) <= 120:
        return parsed.title
    heading = next((b.text for b in parsed.blocks if b.kind == "heading"), "")
    return heading or title


def pdf_rows() -> tuple[list[CorpusDoc], dict[str, set[str]]]:
    zen = {}
    if ZENODO_INDEX.exists():
        for line in ZENODO_INDEX.open(encoding="utf-8"):
            r = json.loads(line)
            zen[str(r["record_id"])] = r
    rows, runs = [], {}
    with DATASET.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["text_layer"] == "none":
                continue  # scans: no text layer to index (see README, "Corpus")
            if r["source"] == "ocw":
                slug = r["source_url"].split("/courses/")[1].split("/")[0]
                version, year = run_version(slug)
                if r["golden"] == "True":
                    runs.setdefault(r["course_id"], set()).add(slug)
            else:
                date = zen.get(r["course_id"], {}).get("publication_date", "")
                version, year = date, int(date[:4]) if date[:4].isdigit() else None
            rows.append(CorpusDoc(
                doc_id=r["doc_id"], format="pdf",
                kind="lecture_slides" if r["layout"] == "slides" else "lecture_notes",
                lang=r["lang"], source=r["source"], license=r["license"],
                course_id=r["course_id"], course_title=r["course_title"],
                title=pdf_title(r), version=version, year=year, url=r["source_url"],
                file_url=r["pdf_url"], path=f"data/pdfs/{r['doc_id']}.pdf",
                sha256=r["source_sha256"]))
    return rows, runs


def save(doc_id: str, fmt: str, data: bytes) -> str:
    path = RAW_DIR / fmt / f"{doc_id}.{fmt}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path.as_posix()


def html_rows(client: httpx.Client, runs: dict[str, set[str]]) -> list[CorpusDoc]:
    rows = []
    for course_id, slugs in sorted(runs.items()):
        for slug in sorted(slugs):
            version, year = run_version(slug)
            for kind, page in OCW_PAGES.items():
                url = f"{OCW}{slug}/{page}"
                try:
                    r = client.get(url)
                except httpx.HTTPError as e:  # a missing page may redirect in a loop
                    print(f"  skip {url}: {type(e).__name__}")
                    continue
                if r.status_code != 200 or "course-content-section" not in r.text and kind != "course_home":
                    print(f"  skip {url}: {r.status_code}")
                    continue
                doc_id = f"html-{short_run(slug)}-{kind.replace('_', '-')}"
                path = save(doc_id, "html", r.content)
                parsed = parse(Path(path), "html")
                if len(parsed.text) < 200:
                    Path(path).unlink()
                    print(f"  skip {url}: {len(parsed.text)} chars")
                    continue
                parts = [p.strip() for p in parsed.title.split("|")]
                course_title = parts[1] if kind != "course_home" and len(parts) > 1 else parts[0]
                rows.append(CorpusDoc(
                    doc_id=doc_id, format="html", kind=kind, lang="en", source="ocw",
                    license=OCW_LICENSE, course_id=course_id, course_title=course_title,
                    title=f"{course_title}: {kind.replace('_', ' ')}", version=version,
                    year=year, url=url, file_url=url, path=path, sha256=sha256_bytes(r.content)))
                print(f"  {doc_id}")
    return rows


OCW_FILE_HREF_RE = re.compile(r'href="(/courses/[^"]+?\.pptx)"', re.IGNORECASE)


def ocw_slide_rows(client: httpx.Client, course_ids: dict[str, str]) -> list[CorpusDoc]:
    rows = []
    for slug, resources in OCW_SLIDES.items():
        version, year = run_version(slug)
        for res in resources:
            page_url = f"{OCW}{slug}/resources/{res}/"
            html = client.get(page_url).raise_for_status().text
            m = OCW_FILE_HREF_RE.search(html)
            if not m:
                print(f"  no pptx link: {page_url}")
                continue
            file_url = "https://ocw.mit.edu" + m.group(1)
            data = download(client, file_url)
            if len(data) > MAX_FILE_BYTES:
                print(f"  too large ({len(data) // 1_000_000} MB): {file_url}")
                continue
            stem = re.sub(r"^[0-9a-f]{32}_", "", file_url.rsplit("/", 1)[1]).removesuffix(".pptx")
            doc_id = f"pptx-ocw-{stem.lower()}"
            path = save(doc_id, "pptx", data)
            title = re.search(r"<title>([^|<]+)", html).group(1).strip()
            course_title = re.search(r"<title>[^|]+\|\s*([^|<]+)", html).group(1).strip()
            rows.append(CorpusDoc(
                doc_id=doc_id, format="pptx", kind="lecture_slides", lang="en", source="ocw",
                license=OCW_LICENSE, course_id=course_ids[slug], course_title=course_title,
                title=title, version=version, year=year, url=page_url, file_url=file_url,
                path=path, sha256=sha256_bytes(data)))
            print(f"  {doc_id}")
    return rows


def zenodo_rows(client: httpx.Client) -> list[CorpusDoc]:
    rows = []
    for rec_id, (lang, kind, pattern) in ZENODO_FILES.items():
        rec = client.get(f"https://zenodo.org/api/records/{rec_id}").raise_for_status().json()
        meta = rec["metadata"]
        files = [f for f in rec["files"] if re.search(pattern, f["key"], re.IGNORECASE)]
        for i, f in enumerate(sorted(files, key=lambda f: f["key"]), 1):
            fmt = f["key"].rsplit(".", 1)[1].lower()
            if f["size"] > MAX_FILE_BYTES:
                print(f"  too large: {f['key']}")
                continue
            data = download(client, f["links"]["self"])
            doc_id = f"{fmt}-zen-{rec_id}" + (f"-{i}" if len(files) > 1 else "")
            path = save(doc_id, fmt, data)
            date = meta.get("publication_date", "")
            rows.append(CorpusDoc(
                doc_id=doc_id, format=fmt, kind=kind, lang=lang, source="zenodo",
                license=(meta.get("license") or {}).get("id", ""), course_id=str(rec_id),
                course_title=meta["title"], title=unquote(f["key"]).rsplit(".", 1)[0],
                version=date, year=int(date[:4]) if date[:4].isdigit() else None,
                url=rec["links"]["self_html"], file_url=f["links"]["self"], path=path,
                sha256=sha256_bytes(data)))
            print(f"  {doc_id}")
    return rows


def main() -> None:
    rows, runs = pdf_rows()
    print(f"pdf: {len(rows)}")
    for course_id, slugs in EXTRA_RUNS.items():
        runs.setdefault(course_id, set()).update(slugs)
    course_of_run = {s: c for c, slugs in runs.items() for s in slugs}
    with httpx.Client(timeout=120, follow_redirects=True,
                      headers={"User-Agent": "coursedeck/0.1"}) as client:
        print("html:")
        rows += html_rows(client, runs)
        print("pptx (ocw):")
        rows += ocw_slide_rows(client, course_of_run)
        print("zenodo:")
        rows += zenodo_rows(client)
    write_corpus(rows)
    by_fmt = {f: sum(r.format == f for r in rows) for f in ("pdf", "html", "docx", "pptx")}
    print(f"corpus: {len(rows)} documents {by_fmt}")


if __name__ == "__main__":
    main()
