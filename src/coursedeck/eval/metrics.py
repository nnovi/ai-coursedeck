"""Per-field metrics, one family per field group (see coursedeck.schema.FIELD_GROUPS).

fact            exact match (codes, numbers, year, term) or fuzzy match (titles, institution);
                lecturers by surname. Each fact is also classified as hallucinated (filled
                although the golden value is empty) or omitted (empty although it is not).
classification  exact match.
content         fuzzy F1 between item lists (greedy one-to-one matching).
"""

import re
import unicodedata

from rapidfuzz import fuzz

from coursedeck.schema import FIELD_GROUPS

EXACT_FACTS = {"course_code", "lecture_number", "year", "term"}
FUZZY_FACTS = {"course_title", "institution", "lecture_title"}
FACT_THRESHOLD = 85  # token_sort_ratio for titles and institution names
# token_set_ratio per content list; topics are paraphrased more than terms or references
CONTENT_THRESHOLDS = {"topics": 70, "key_terms": 85, "references": 80}

QUOTES = str.maketrans({c: "'" for c in "’‘ʼ′`´“”«»\""}) | str.maketrans({"–": "-", "—": "-"})
INSTITUTION_ALIASES = {  # normalized name -> canonical
    "mit": "mit",
    "mit opencourseware": "mit",
    "massachusetts institute of technology": "mit",
}


def norm(value) -> str:
    s = unicodedata.normalize("NFKC", str(value)).casefold().translate(QUOTES)
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip(" .,;:")


def empty(value) -> bool:
    return value is None or value == [] or (isinstance(value, str) and not value.strip())


def _institution(value: str) -> str:
    n = norm(value)
    return INSTITUTION_ALIASES.get(n, n)


def same_fact(field: str, gold, pred) -> bool:
    if empty(gold) or empty(pred):
        return empty(gold) and empty(pred)
    if field in EXACT_FACTS:
        return norm(gold) == norm(pred)
    if field == "institution":
        gold, pred = _institution(gold), _institution(pred)
        if gold == pred:
            return True
    return fuzz.token_sort_ratio(norm(gold), norm(pred)) >= FACT_THRESHOLD


def _name_tokens(name: str) -> set[str]:
    """Non-initial tokens of a person's name: 'П.Г. Балан' -> {'балан'}."""
    tokens = re.split(r"[\s.]+", norm(name))
    return {t for t in tokens if len(t) > 2}


def same_person(a: str, b: str) -> bool:
    return bool(_name_tokens(a) & _name_tokens(b))


def list_f1(gold: list[str], pred: list[str], match) -> tuple[float, float, float]:
    """Precision, recall, F1 with greedy one-to-one matching; two empty lists score 1."""
    if not gold and not pred:
        return 1.0, 1.0, 1.0
    if not gold or not pred:
        return 0.0, 0.0, 0.0
    pairs = sorted(((match(g, p), i, j) for i, g in enumerate(gold) for j, p in enumerate(pred)),
                   reverse=True)
    used_g, used_p, hits = set(), set(), 0
    for score, i, j in pairs:
        if score <= 0:
            break
        if i not in used_g and j not in used_p:
            used_g.add(i)
            used_p.add(j)
            hits += 1
    p, r = hits / len(pred), hits / len(gold)
    return p, r, (2 * p * r / (p + r) if hits else 0.0)


def content_match(field: str):
    threshold = CONTENT_THRESHOLDS[field]

    def match(g: str, p: str) -> float:
        score = fuzz.token_set_ratio(norm(g), norm(p))
        return score if score >= threshold else 0

    return match


def score_card(gold: dict, pred: dict | None) -> dict:
    """Per-field scores for one document. A missing card (invalid output) scores zero."""
    out: dict = {"fact": {}, "classification": {}, "content": {}}
    for field in FIELD_GROUPS["fact"]:
        g = gold[field]
        p = pred.get(field) if pred else None
        if field == "lecturers":
            _, _, f1 = list_f1(g, p or [], lambda a, b: 1.0 if same_person(a, b) else 0)
            correct = f1 == 1.0
        else:
            correct = same_fact(field, g, p) if pred else False
        out["fact"][field] = {
            "correct": correct,
            "hallucinated": bool(pred) and empty(g) and not empty(p),
            "omitted": bool(pred) and not empty(g) and empty(p),
            "gold_empty": empty(g),
        }
    for field in FIELD_GROUPS["classification"]:
        p = pred.get(field) if pred else None
        out["classification"][field] = {"correct": p == gold[field], "gold": gold[field],
                                        "pred": p}
    for field in FIELD_GROUPS["content"]:
        p, r, f1 = list_f1(gold[field], (pred or {}).get(field) or [], content_match(field))
        out["content"][field] = {"precision": p, "recall": r, "f1": f1}
    return out


def mean(values) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def aggregate(per_doc: dict[str, dict]) -> dict:
    """Field and group means over documents."""
    docs = list(per_doc.values())
    facts = {f: mean(d["fact"][f]["correct"] for d in docs) for f in FIELD_GROUPS["fact"]}
    classes = {f: mean(d["classification"][f]["correct"] for d in docs)
               for f in FIELD_GROUPS["classification"]}
    content = {f: mean(d["content"][f]["f1"] for d in docs) for f in FIELD_GROUPS["content"]}
    fact_cells = [c for d in docs for c in d["fact"].values()]
    gold_empty = [c for c in fact_cells if c["gold_empty"]]
    gold_filled = [c for c in fact_cells if not c["gold_empty"]]
    groups = {"fact": mean(facts.values()), "classification": mean(classes.values()),
              "content": mean(content.values())}
    return {
        "n_docs": len(docs),
        "fields": {**facts, **classes, **content},
        "groups": groups,
        "overall": mean(groups.values()),
        "hallucination_rate": mean(c["hallucinated"] for c in gold_empty),
        "omission_rate": mean(c["omitted"] for c in gold_filled),
        "confusions": sorted(
            f"{f}: {d['classification'][f]['gold']} -> {d['classification'][f]['pred']}"
            for d in docs for f in FIELD_GROUPS["classification"]
            if not d["classification"][f]["correct"]
        ),
    }
