# Golden set: annotation guide

One file per document: `data/golden/<doc_id>.json`

```json
{
  "doc_id": "ocw-8-08-the_fermi_gas",
  "status": "draft | reviewed",
  "notes": "free-text remarks about ambiguous decisions",
  "card": { ...LectureCard... }
}
```

Drafts are pre-filled and must be checked by a human; only `reviewed` files are used as
ground truth. Review with `python -m coursedeck.golden.review`.

## General rules

- **Only what the document shows.** Use every page of the document (title pages, headers,
  footers, the OCW citation page) but nothing else: not the file name, not the manifest,
  not the course web page, not your own knowledge. If it is not in the document, it is `null`
  (or an empty list).
- Ukrainian documents are one lecture cut out of a course book, preceded by the book's
  title pages (cover, title page, its reverse). The title pages are part of the document and
  are the usual source of the course name, authors, institution and year.
- **Copy facts as written**: keep the document's language and spelling. Collapse whitespace,
  drop line-break hyphens, and write ALL-CAPS text in normal capitalization. Evaluation
  ignores case, whitespace and quote/apostrophe variants.
- Content lists (`topics`, `key_terms`, `references`) are in the document's language.

## Facts

| Field | Rule |
|---|---|
| `course_title` | Name of the course without its code. English: from the document header/title slide, else from the OCW citation page (`18.06 Linear Algebra` → `Linear Algebra`). Ukrainian book: the discipline named on the title pages (`з дисципліни «X»` → `X`); otherwise the book title without genre words such as `курс лекцій`, `конспект лекцій`, `навчальний посібник`, `схемоконспект лекцій`, `для студентів …` (`Загальна паразитологія. Конспект лекцій` → `Загальна паразитологія`). |
| `course_code` | The first course number as written in the header/title (`6.241J / 16.338J` → `6.241J`); if the header has none, the first one on the OCW citation page. Specialty codes (`014 Середня освіта`), УДК/ББК and ISBN are not course codes. |
| `institution` | The university (top-level institution) as written, without ministry, faculty, department or institute (`Київський національний університет імені Тараса Шевченка`, not `ННЦ «Інститут біології та медицини»`). Use its fullest form shown anywhere in the document (`Massachusetts Institute of Technology` over `MIT`); if the only mention is the OCW footer, `MIT OpenCourseWare`. |
| `lecturers` | Authors, lecturers or compilers (`автори`, `укладачі`) of the material, one person per item, in document order, in the fullest form shown, without academic titles, degrees or positions (`Prof.`, `Dr.`, `к.б.н., доц.`). Not scribes or note-takers, reviewers (`рецензенти`), editors, people who are cited, thanked or credited for images. Evaluation matches names by surname. |
| `lecture_number` | Only a number labelled as a lecture/topic/session: `Lecture 17`, `Lec. 3`, `L3`, `Session 5`, `Лекція 3`, `Тема № 1`. Not chapter, section or part numbers (`Chapter 4`, `4.6`, `VIII`, `Розділ 1`, `Частина 2`), weeks, page or slide numbers, or the file name. |
| `lecture_title` | The heading of this lecture/topic without its `Lecture N` / `Тема N` prefix or section number. If there is no labelled lecture heading: the main heading at the top of the first content page or title slide that names the subject of the whole document. Not a heading that covers only part of the document, and not the course or book title. Otherwise `null`. |
| `year` | The first available of: (1) a date of the lecture/document on the content pages (`September 9, 2003`, `2/11/04`); (2) the term/year of the course offering in the header or title (`Spring 2005`); (3) the year of publication or approval on the book's title pages (`Харків – 2022`, `© 2022`); (4) the OCW citation page (`Spring 2012`). Never years of cited works or dates in the subject matter. |
| `term` | Only a term stated together with the chosen year (same source): `Fall` → `fall`, `Spring` → `spring`, `IAP`/`January` → `winter`, `осінній семестр` → `fall`; otherwise `null`. |

## Classification

`discipline`: one value, the primary field of the *content of this lecture* (not the
department offering the course):

| Value | Includes |
|---|---|
| mathematics | analysis, algebra, calculus of variations, statistics, probability, discrete mathematics, mathematical logic |
| physics | mechanics as physics, electromagnetism, quantum mechanics, statistical physics, optics |
| chemistry | general, organic, physical chemistry, crystallography |
| biology | zoology, entomology, parasitology, soil-animal ecology, genetics, cell biology, neurobiology |
| computer_science | algorithms, programming, databases, information security, DevOps, quantum algorithms |
| engineering | control theory, dynamic systems, mechanics of materials, hydrodynamics, reaction engineering, energy systems |
| earth_environmental_sciences | geology, geochemistry, oceanography, climate, environmental monitoring and quality |
| medicine_health | clinical medicine, physiology, hygiene, public health |
| economics_business | economics, management, finance, marketing, entrepreneurship |
| social_sciences | sociology, social communication, political science, psychology, anthropology, law |
| humanities | philosophy (including philosophy of education), history, literature, linguistics, music, philosophical logic (e.g. modal logic taught as philosophy) |
| arts_architecture | art, design, architecture |
| education | pedagogy, teaching methodology, health pedagogy, educational practice |

`doc_type`:
- `lecture_notes` — prose, typed or handwritten notes for one lecture;
- `slides` — a slide deck (one idea per page, landscape, bullet points), including
  Ukrainian slide-style `схемоконспект`;
- `handout` — a short supplementary sheet: worked problems, a summary table, figures,
  reading lists;
- `textbook_chapter` — a chapter or topic of a book: Ukrainian course-book excerpts, and
  English documents with book-style running headers (`CHAPTER 4 …`) and page numbers;
- `outline` — a plan or bullet outline of a lecture without full exposition.

Title pages do not change `doc_type`: classify the lecture pages.

## Content

- `topics`: 3–10 main topics in document order, short noun phrases (2–8 words), following
  the lecture plan, section headings or slide titles. Merge sub-points into their topic.
  Title pages contribute nothing.
- `key_terms`: up to 20 terms the lecture introduces, defines or emphasizes (bold/italic,
  "is called", `Означення`, `називається`), most important first. Base form as written,
  no definitions. Prefer specific terms (`Fermi-Dirac distribution`) over generic words.
- `references`: every entry of a literature list in the document (`References`, `Reading`,
  `Література`, `Рекомендована література`, `Список джерел`), one entry per item, copied as
  written (may be shortened to authors, title, year). Not footnote-only or inline citations
  (`[1]`) without a list, image credits, `Cite as` notices, links to course pages.
