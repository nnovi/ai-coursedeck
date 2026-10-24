"""Lecture card: the structured record extracted from one lecture-notes document.

Fields fall into three groups, evaluated differently (see `FIELD_GROUPS`):
  fact            stated in the document or absent -> null; exact match after normalization
  classification  inferred from the document into a closed set; accuracy
  content         lists of items present in the document; fuzzy-matched F1

Generated content (summaries, student questions, examples, prerequisites) is out of scope
for extraction and belongs to the presentation agent.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Discipline(StrEnum):
    mathematics = "mathematics"
    physics = "physics"
    chemistry = "chemistry"
    biology = "biology"
    computer_science = "computer_science"
    engineering = "engineering"
    earth_environmental_sciences = "earth_environmental_sciences"
    medicine_health = "medicine_health"
    economics_business = "economics_business"
    social_sciences = "social_sciences"
    humanities = "humanities"
    arts_architecture = "arts_architecture"
    education = "education"


class DocType(StrEnum):
    lecture_notes = "lecture_notes"  # prose notes written for one lecture
    slides = "slides"  # a slide deck
    handout = "handout"  # short supplementary sheet: summary, worked problems, figures
    textbook_chapter = "textbook_chapter"  # a chapter/topic of a course book or textbook
    outline = "outline"  # lecture plan or bullet outline without full exposition


class Term(StrEnum):
    spring = "spring"
    summer = "summer"
    fall = "fall"
    winter = "winter"  # includes MIT's January IAP term


class LectureCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # --- facts: copy as written in the document; null when the document does not state it
    course_title: str | None = Field(
        description="Course name as written in the document, without the course code."
    )
    course_code: str | None = Field(
        description="Course code or number as written, e.g. '18.06' or '6.241J'."
    )
    institution: str | None = Field(
        description="University or institution named in the document."
    )
    lecturers: list[str] = Field(
        description="Names of the lecturers/authors as written; empty if none are named."
    )
    lecture_number: int | None = Field(
        description="Number of this lecture or topic as numbered in the document."
    )
    lecture_title: str | None = Field(
        description="Title of this lecture or topic, without the 'Lecture N' prefix."
    )
    year: int | None = Field(description="Year the lecture was given or the document dated.")
    term: Term | None = Field(description="Academic term, if the document states one.")

    # --- classification
    discipline: Discipline = Field(description="Primary academic discipline of the lecture.")
    doc_type: DocType = Field(description="Kind of document.")

    # --- content: items present in the document, in the document's language
    topics: list[str] = Field(
        description="Main topics covered, in order, as short phrases (3-10 items)."
    )
    key_terms: list[str] = Field(
        description="Key terms introduced or defined in the lecture (up to 20)."
    )
    references: list[str] = Field(
        description="Literature or sources cited in the document, one entry per item."
    )


# Upper bounds from the annotation guide. Not part of the JSON schema (Anthropic structured
# output does not support maxItems); grammar-based local backends enforce them to stop
# repetition loops.
LIST_LIMITS: dict[str, int] = {"topics": 10, "key_terms": 20, "references": 40}

FIELD_GROUPS: dict[str, list[str]] = {
    "fact": [
        "course_title", "course_code", "institution", "lecturers",
        "lecture_number", "lecture_title", "year", "term",
    ],
    "classification": ["discipline", "doc_type"],
    "content": ["topics", "key_terms", "references"],
}
