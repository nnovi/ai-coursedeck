from docx import Document as DocxDocument
from pptx import Presentation
from pptx.util import Inches

from coursedeck.rag.blocks import Block, ParsedDoc, md_table
from coursedeck.rag.chunk import chunk_fixed, chunk_structure, n_tokens
from coursedeck.rag.clean import join_lines, normalize, repeated
from coursedeck.rag.dedup import dedup_docs
from coursedeck.rag.parse import parse_docx, parse_html, parse_pptx

HTML = """<html><head><title>Syllabus | Course X | MIT OpenCourseWare</title></head><body>
<nav><a href="/">Home</a> Menu</nav>
<div class="cookie-banner">We use cookies</div>
<main id="course-content-section">
  <h2>Grading</h2>
  <p>Problem sets&nbsp;and two exams.</p>
  <ul><li>Problem sets</li><li>Exams<ul><li>Midterm</li></ul></li></ul>
  <table><tr><th>Activity</th><th>Share</th></tr><tr><td>Exams</td><td>60%</td></tr></table>
</main>
<footer>MIT OpenCourseWare footer</footer></body></html>"""


def test_normalize_and_dehyphenation():
    assert normalize("ﬁeld of\u200b study") == "field of study"
    assert join_lines(["transfor-", "mation of the", "Navier-", "Stokes"]) == \
        "transformation of the Navier-Stokes"
    assert join_lines(["пара-", "зитологія"]) == "паразитологія"


def test_running_headers_need_most_pages():
    pages = [{"6.241 lecture #", "a"}, {"6.241 lecture #", "b"}, {"6.241 lecture #"}, {"c"}]
    assert repeated(pages) == {"6.241 lecture #"}


def test_html_keeps_structure_and_drops_chrome(tmp_path):
    f = tmp_path / "p.html"
    f.write_text(HTML, encoding="utf-8")
    doc = parse_html(f)
    kinds = [(b.kind, b.level, b.text) for b in doc.blocks]
    assert kinds[0] == ("heading", 2, "Grading")
    assert ("paragraph", 0, "Problem sets and two exams.") in kinds
    assert ("list_item", 1, "Midterm") in kinds
    table = next(b for b in doc.blocks if b.kind == "table")
    assert table.header.splitlines()[0] == "| Activity | Share |"
    assert "cookies" not in doc.text and "footer" not in doc.text


def test_docx_headings_lists_tables(tmp_path):
    d = DocxDocument()
    d.add_heading("Лекція 1. Вступ", level=1)
    d.add_paragraph("Основний текст.")
    d.add_paragraph("пункт списку", style="List Bullet")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Термін", "Визначення"
    t.cell(1, 0).text, t.cell(1, 1).text = "Паразит", "Організм"
    d.save(tmp_path / "a.docx")
    blocks = parse_docx(tmp_path / "a.docx").blocks
    assert [b.kind for b in blocks] == ["heading", "paragraph", "list_item", "table"]
    assert blocks[0].level == 1 and "| Паразит | Організм |" in blocks[3].text


def test_pptx_slide_titles_and_bullets(tmp_path):
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Finite Automata"
    body = s.placeholders[1].text_frame
    body.text = "States"
    body.add_paragraph().text = "Transitions"
    s2 = prs.slides.add_slide(prs.slide_layouts[6])  # blank: no title placeholder
    s2.shapes.add_textbox(Inches(1), Inches(0.5), Inches(6), Inches(1)).text_frame.text = "NFA"
    s2.shapes.add_textbox(Inches(1), Inches(2), Inches(6), Inches(1)).text_frame.text = \
        "Nondeterminism allows several paths."
    prs.save(tmp_path / "a.pptx")
    blocks = parse_pptx(tmp_path / "a.pptx").blocks
    assert (blocks[0].kind, blocks[0].text, blocks[0].page) == ("heading", "Finite Automata", 1)
    assert [b.text for b in blocks if b.kind == "list_item"] == ["States", "Transitions"]
    assert any(b.kind == "heading" and b.text == "NFA" and b.page == 2 for b in blocks)


def _doc(sections: dict[str, list[str]]) -> ParsedDoc:
    blocks = []
    for title, paras in sections.items():
        blocks.append(Block("heading", title, level=1))
        blocks += [Block("paragraph", p) for p in paras]
    return ParsedDoc(blocks)


def test_structure_chunks_follow_sections_and_merge_small_ones():
    long = " ".join(f"Sentence number {i} explains the method." for i in range(80))
    doc = _doc({"Intro": ["Short intro."], "Outline": ["Two items."], "Method": [long]})
    chunks = chunk_structure(doc, max_tokens=200, min_tokens=50)
    assert chunks[0].path == ("Intro",) and "## Outline" in chunks[0].text  # small siblings merged
    method = [c for c in chunks if c.path == ("Method",)]
    assert len(method) > 1 and all(c.tokens <= 200 for c in method)
    assert all(c.text.rstrip().endswith(".") for c in method)  # split at sentence boundaries


def test_long_table_is_split_by_rows_with_header():
    md, header = md_table([["Lecture", "Topic"]] + [[f"L{i}", f"Topic {i} " * 5] for i in range(60)])
    doc = ParsedDoc([Block("heading", "Calendar", level=1), Block("table", md, header=header)])
    chunks = chunk_structure(doc, max_tokens=150)
    assert len(chunks) > 1
    assert all("| Lecture | Topic |\n|---|---|" in c.text for c in chunks)


def test_fixed_chunks_have_size_and_overlap():
    doc = _doc({"A": [" ".join(f"word{i}" for i in range(600))]})
    chunks = chunk_fixed(doc, max_tokens=100, overlap=20)
    assert all(c.tokens <= 100 for c in chunks)
    assert chunks[0].text[-15:] in chunks[1].text  # the overlap repeats the tail
    assert n_tokens(chunks[0].text) <= 101


def test_dedup_exact_near_and_versions():
    base = " ".join(f"term{i} is defined in lecture" for i in range(200))
    decisions = dedup_docs([
        ("a", "c1|2020", base),
        ("b", "c1|2020", base.upper()),  # same text after normalization
        ("c", "c1|2020", base + " plus answers to all exercises"),  # more complete copy
        ("d", "c1|2010", base + " old syllabus remark"),  # another run: a version
    ])
    assert decisions["b"].action == "drop_exact" and decisions["b"].other == "a"
    assert decisions["a"].action == "drop_near" and decisions["a"].other == "c"
    assert decisions["d"].action == "keep_version"
