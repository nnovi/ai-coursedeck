"""Deduplication of documents and chunks.

documents  exact: SHA-256 of the normalized text (case, whitespace and punctuation folded),
           so the same content in another file or format is caught;
           near: Jaccard similarity / containment of word 5-gram shingles. A near duplicate of
           the same course run is the same material twice (e.g. a workbook and the same
           workbook with answers): the more complete one is kept. A near duplicate from a
           different run or year is a separate version: both are kept and linked, so the
           retriever can filter by version.
chunks     exact hash of the normalized chunk text: repeated title slides, cover pages and
           course-info boxes are indexed once.
"""

import hashlib
import re
from dataclasses import dataclass

SHINGLE = 5
NEAR_JACCARD = 0.8
NEAR_CONTAINMENT = 0.9


def norm_text(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def content_hash(text: str) -> str:
    return hashlib.sha256(norm_text(text).encode()).hexdigest()


def shingles(text: str, n: int = SHINGLE) -> set[int]:
    words = norm_text(text).split()
    return {hash(" ".join(words[i:i + n])) for i in range(max(len(words) - n + 1, 1))}


@dataclass
class DocDecision:
    doc_id: str
    action: str  # keep | drop_exact | drop_near | keep_version
    other: str = ""  # the document it duplicates (or is a version of)
    jaccard: float = 0.0
    containment: float = 0.0


def dedup_docs(docs: list[tuple[str, str, str]]) -> dict[str, DocDecision]:
    """docs: (doc_id, version key, text) in manifest order -> decision per doc_id.

    The version key identifies a course run or publication ("6.007|Spring 2011"); near
    duplicates with equal keys are copies, with different keys they are versions."""
    decisions = {d: DocDecision(d, "keep") for d, _, _ in docs}
    seen: dict[str, str] = {}
    for doc_id, _, text in docs:
        h = content_hash(text)
        if h in seen:
            decisions[doc_id] = DocDecision(doc_id, "drop_exact", seen[h], 1.0, 1.0)
        else:
            seen[h] = doc_id
    live = [(d, v, t, shingles(t)) for d, v, t in docs if decisions[d].action == "keep"]
    for i, (a, va, ta, sa) in enumerate(live):
        for b, vb, tb, sb in live[i + 1:]:
            inter = len(sa & sb)
            if not inter:
                continue
            jac = inter / len(sa | sb)
            cont = inter / min(len(sa), len(sb))
            if jac < NEAR_JACCARD and cont < NEAR_CONTAINMENT:
                continue
            if va == vb:  # same material twice: keep the longer (more complete) one
                small, big = (a, b) if len(sa) < len(sb) else (b, a)
                if decisions[small].action == "keep":
                    decisions[small] = DocDecision(small, "drop_near", big, round(jac, 3),
                                                   round(cont, 3))
            else:
                for x, y in ((a, b), (b, a)):
                    if decisions[x].action == "keep":
                        decisions[x] = DocDecision(x, "keep_version", y, round(jac, 3),
                                                   round(cont, 3))
    return decisions


def chunk_hash(text: str) -> str:
    return hashlib.sha1(norm_text(text).encode()).hexdigest()
