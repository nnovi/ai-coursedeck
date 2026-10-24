import json

import pymupdf
import pytest

from coursedeck.extract.extractor import build_input, extract, parse_card
from coursedeck.extract.pages import MAX_LONG_EDGE_PX, TARGET_FONT_PX, page_zoom
from coursedeck.llm.base import ImagePart, LLMResponse, PdfPart, TextPart, Usage
from coursedeck.llm.models import MODELS

CARD = {
    "course_title": "Modal Logic", "course_code": "24.244", "institution": None,
    "lecturers": [], "lecture_number": None, "lecture_title": "Stronger Systems",
    "year": 2015, "term": "spring", "discipline": "humanities", "doc_type": "lecture_notes",
    "topics": ["S4"], "key_terms": ["S5"], "references": [],
}


@pytest.fixture
def pdf(tmp_path):
    path = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    page = doc.new_page()  # letter-size page with 8pt and 12pt text
    page.insert_text((72, 72), "Small footnote text here", fontsize=8)
    page.insert_text((72, 120), "Body text of the lecture", fontsize=12)
    doc.new_page()  # blank page: no text layer
    doc.save(path)
    return path


def test_zoom_follows_smallest_text_and_scans_get_full_budget(pdf):
    with pymupdf.open(pdf) as doc:
        assert page_zoom(doc[0]) == pytest.approx(TARGET_FONT_PX / 8)
        assert page_zoom(doc[1]) == pytest.approx(MAX_LONG_EDGE_PX / doc[1].rect.height)


def test_build_input_modes(pdf):
    text = build_input(pdf, "text")
    assert not any(isinstance(p, ImagePart) for p in text.parts)
    assert any("[no text layer" in p.text for p in text.parts if isinstance(p, TextPart))

    both = build_input(pdf, "text+image")
    assert sum(isinstance(p, ImagePart) for p in both.parts) == 2
    assert both.image_pixels > 0

    native = build_input(pdf, "pdf")
    assert isinstance(native.parts[0], PdfPart) and native.n_pages == 2


class FakeAdapter:
    supports_pdf = False

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        text, stop = self.replies.pop(0)
        return LLMResponse(text, stop, Usage(100, 50), 0.5)


def test_invalid_reply_gets_one_retry_with_the_error(pdf):
    adapter = FakeAdapter([('{"course_title": 1}', "end_turn"), (json.dumps(CARD), "end_turn")])
    result = extract(adapter, "system", build_input(pdf, "text"))
    assert result.card is not None and result.card.year == 2015
    assert len(result.attempts) == 2 and result.attempts[0].error
    retry_msg = adapter.requests[1].messages[-1].parts[0].text
    assert "not a valid lecture card" in retry_msg
    assert result.usage.input_tokens == 200


def test_second_failure_is_reported(pdf):
    adapter = FakeAdapter([("not json", "end_turn"), ("still not", "end_turn")])
    result = extract(adapter, "system", build_input(pdf, "text"))
    assert result.card is None and "invalid JSON" in result.error


def test_truncated_reply_is_an_error_even_if_parseable():
    card, error = parse_card(json.dumps(CARD), "max_tokens")
    assert card is None and "max_tokens" in error


def test_ollama_schema_gets_list_limits_without_touching_the_original():
    from coursedeck.llm.ollama_adapter import OllamaAdapter
    from coursedeck.schema import LIST_LIMITS, LectureCard

    schema = LectureCard.model_json_schema()
    patched = OllamaAdapter("m", max_items=LIST_LIMITS)._schema(schema)
    assert patched["properties"]["references"]["maxItems"] == LIST_LIMITS["references"]
    assert "maxItems" not in schema["properties"]["references"]


def test_openrouter_schema_has_no_refs():
    import json as _json

    from coursedeck.llm.openrouter_adapter import inline_refs
    from coursedeck.schema import LectureCard

    schema = inline_refs(LectureCard.model_json_schema())
    text = _json.dumps(schema)
    assert "$ref" not in text and "$defs" not in text
    assert "enum" in schema["properties"]["discipline"]
    assert schema["properties"]["discipline"]["description"]


def test_source_file_strips_ocw_hash():
    from pathlib import Path

    from coursedeck.dataset.manifest import read_manifest

    rows = {r.doc_id: r for r in read_manifest(Path("data/manifests/golden.csv"))}
    assert rows["ocw-12-480-lecture_16"].source_file == "lecture_16.pdf"
    assert rows["zen-14978718-p006"].source_file.endswith(".pdf")


def test_cost_uses_long_prompt_pricing():
    haiku = MODELS["haiku"]
    assert haiku.cost(Usage(1_000_000, 0)) == pytest.approx(0.50)  # > 100K prompt tier
    assert haiku.cost(Usage(50_000, 10_000)) == pytest.approx(0.005 + 0.005)
    assert MODELS["qwen3-vl-8b"].cost(Usage(10**6, 10**6)) == 0
