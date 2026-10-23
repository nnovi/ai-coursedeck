"""Read and write golden annotation files: data/golden/<doc_id>.json.

File layout:
    doc_id   document id from the manifest
    status   "draft" (pre-filled, unchecked) | "reviewed" (ground truth)
    notes    reviewer remarks
    card     the LectureCard
    draft    the card as first pre-filled, kept on the first save to measure review edits
"""

import json
from pathlib import Path

from coursedeck.schema import LectureCard

GOLDEN_DIR = Path("data/golden")
STATUSES = ("draft", "reviewed")


def path_for(doc_id: str) -> Path:
    return GOLDEN_DIR / f"{doc_id}.json"


def load(doc_id: str) -> dict | None:
    p = path_for(doc_id)
    return json.loads(p.read_text("utf-8")) if p.exists() else None


def save(doc_id: str, card: dict, notes: str, status: str) -> dict:
    """Validate and write an annotation; raises pydantic.ValidationError on a bad card."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    validated = LectureCard.model_validate(card).model_dump(mode="json")
    prev = load(doc_id) or {}
    record = {
        "doc_id": doc_id,
        "status": status,
        "notes": notes,
        "card": validated,
        "draft": prev.get("draft", prev.get("card")),
    }
    path_for(doc_id).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return record


def load_reviewed() -> dict[str, LectureCard]:
    """Ground-truth cards keyed by doc_id (reviewed files only)."""
    out = {}
    for p in sorted(GOLDEN_DIR.glob("*.json")):
        rec = json.loads(p.read_text("utf-8"))
        if rec["status"] == "reviewed":
            out[rec["doc_id"]] = LectureCard.model_validate(rec["card"])
    return out
