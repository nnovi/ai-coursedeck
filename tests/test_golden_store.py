import json

import pytest
from pydantic import ValidationError

from coursedeck.golden import store

CARD = {
    "course_title": "Quantum Computation", "course_code": "18.435J", "institution": None,
    "lecturers": [], "lecture_number": 2, "lecture_title": None, "year": None, "term": None,
    "discipline": "computer_science", "doc_type": "lecture_notes",
    "topics": ["Qubits"], "key_terms": [], "references": [],
}


@pytest.fixture(autouse=True)
def golden_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "GOLDEN_DIR", tmp_path)
    return tmp_path


def test_first_save_keeps_original_card_as_draft(golden_dir):
    (golden_dir / "d1.json").write_text(json.dumps(
        {"doc_id": "d1", "status": "draft", "notes": "", "card": CARD}), "utf-8")
    edited = {**CARD, "discipline": "physics"}
    store.save("d1", edited, "fixed discipline", "reviewed")
    store.save("d1", {**edited, "year": 2003}, "", "reviewed")

    rec = store.load("d1")
    assert rec["draft"]["discipline"] == "computer_science"
    assert rec["card"]["year"] == 2003
    assert list(store.load_reviewed()) == ["d1"]


def test_invalid_card_is_not_written(golden_dir):
    with pytest.raises(ValidationError):
        store.save("d2", {**CARD, "discipline": "astrology"}, "", "draft")
    assert not (golden_dir / "d2.json").exists()
