"""Build the extraction request for a document and get a validated LectureCard back.

Input modes:
  text        the text layer of every page
  image       an image of every page
  text+image  both, page by page
  pdf         the PDF itself (providers with native PDF input read text and page images)

Every reply is validated against LectureCard; on failure the model gets one retry with the
validation error.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pydantic import ValidationError

from coursedeck.extract.pages import load_pages
from coursedeck.llm.base import (
    Adapter,
    ImagePart,
    LLMRequest,
    Message,
    PdfPart,
    TextPart,
    Usage,
)
from coursedeck.schema import LectureCard

MODES = ("text", "image", "text+image", "pdf")
NO_TEXT = "[no text layer on this page]"
TASK = "Extract the lecture card from this document."
MAX_RETRIES = 1


@dataclass
class DocInput:
    parts: list
    n_pages: int
    image_pixels: int = 0  # total pixels of page images sent


def build_input(pdf: Path, mode: str) -> DocInput:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if mode == "pdf":
        pages = load_pages(pdf, with_images=False)
        return DocInput([PdfPart(pdf.read_bytes()), TextPart(TASK)], len(pages))

    pages = load_pages(pdf, with_images=mode != "text")
    parts: list = [TextPart(f"The document has {len(pages)} pages.")]
    for p in pages:
        if mode == "text":
            parts.append(TextPart(f"--- Page {p.number} ---\n{p.text or NO_TEXT}"))
        elif mode == "image":
            parts += [TextPart(f"--- Page {p.number} ---"), ImagePart(p.image)]
        else:
            parts += [TextPart(f"--- Page {p.number} ---"), ImagePart(p.image),
                      TextPart(f"Text layer of page {p.number}:\n{p.text or NO_TEXT}")]
    parts.append(TextPart(TASK))
    return DocInput(parts, len(pages), sum(p.width_px * p.height_px for p in pages))


@dataclass
class Attempt:
    text: str
    stop_reason: str
    usage: Usage
    latency_s: float
    error: str | None = None
    request_id: str | None = None


@dataclass
class Extraction:
    card: LectureCard | None
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def usage(self) -> Usage:
        total = Usage()
        for a in self.attempts:
            total = total + a.usage
        return total

    @property
    def latency_s(self) -> float:
        return sum(a.latency_s for a in self.attempts)

    @property
    def error(self) -> str | None:
        return None if self.card else (self.attempts[-1].error if self.attempts else "no attempt")

    def attempts_json(self) -> list[dict]:
        return [asdict(a) for a in self.attempts]


def parse_card(text: str, stop_reason: str) -> tuple[LectureCard | None, str | None]:
    if stop_reason == "max_tokens":
        return None, "the reply was cut off at max_tokens"
    try:
        return LectureCard.model_validate(json.loads(text)), None
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e}"
    except ValidationError as e:
        errors = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
        return None, f"schema validation failed: {errors}"


def extract(adapter: Adapter, system: str, doc: DocInput, max_tokens: int = 16000) -> Extraction:
    schema = LectureCard.model_json_schema()
    messages = [Message("user", doc.parts)]
    result = Extraction(card=None)
    for attempt in range(MAX_RETRIES + 1):
        resp = adapter.complete(LLMRequest(system, messages, schema, max_tokens))
        card, error = parse_card(resp.text, resp.stop_reason)
        if resp.stop_reason == "refusal":
            error = "the model refused"
        result.attempts.append(Attempt(resp.text, resp.stop_reason, resp.usage, resp.latency_s,
                                       error, resp.request_id))
        if card or resp.stop_reason == "refusal" or attempt == MAX_RETRIES:
            result.card = card
            return result
        messages = messages + [
            Message("assistant", [TextPart(resp.text or "(empty reply)")]),
            Message("user", [TextPart(
                f"Your reply is not a valid lecture card: {error}. "
                "Return the corrected JSON object only.")]),
        ]
    return result
