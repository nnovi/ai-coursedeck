import pytest

from coursedeck.eval.metrics import aggregate, list_f1, same_fact, same_person, score_card

GOLD = {
    "course_title": "Основи варіаційного числення", "course_code": None,
    "institution": "Massachusetts Institute of Technology",
    "lecturers": ["Наталія Кугай", "Микола Калініченко"], "lecture_number": 1,
    "lecture_title": "Основні поняття варіаційного числення", "year": 2022, "term": None,
    "discipline": "mathematics", "doc_type": "textbook_chapter",
    "topics": ["Поняття функціонала", "Варіація функції"], "key_terms": ["функціонал"],
    "references": [],
}


def test_fact_normalization():
    assert same_fact("course_title", "ОСНОВИ ВАРІАЦІЙНОГО ЧИСЛЕННЯ", "Основи варіаційного числення")
    assert same_fact("institution", "MIT OpenCourseWare", "Massachusetts Institute of Technology")
    assert same_fact("lecture_title", "Van der Waerden’s Theorem", "Van der Waerden's theorem")
    assert not same_fact("course_code", "6.241", "6.241J")
    assert same_fact("year", 2022, "2022")


def test_names_match_by_surname_in_any_form():
    assert same_person("Наталія Кугай", "Кугай Н. В.")
    assert same_person("П.Г. Балан", "Балан П. Г.")
    assert not same_person("П.Г. Балан", "П.Я. Кілочицький")


def test_list_f1_greedy_one_to_one():
    assert list_f1([], [], lambda a, b: 1) == (1.0, 1.0, 1.0)
    p, r, _ = list_f1(["a", "b"], ["a", "a", "c"], lambda g, x: 1.0 if g == x else 0)
    assert (p, r) == (pytest.approx(1 / 3), 0.5)


def test_hallucination_and_omission():
    pred = {**GOLD, "course_code": "18.06", "lecture_number": None,
            "lecturers": ["Кугай Н. В.", "Калініченко М. М."], "references": ["Smith 2001"]}
    s = score_card(GOLD, pred)
    assert s["fact"]["course_code"]["hallucinated"]
    assert s["fact"]["lecture_number"]["omitted"]
    assert s["fact"]["lecturers"]["correct"]
    assert s["content"]["references"]["f1"] == 0.0
    agg = aggregate({"d": s})
    assert agg["hallucination_rate"] == pytest.approx(1 / 2)  # course_code, term are gold-empty


def test_invalid_output_scores_zero_but_is_not_hallucination():
    s = score_card(GOLD, None)
    assert not any(c["correct"] or c["hallucinated"] for c in s["fact"].values())
    assert s["content"]["topics"]["f1"] == 0.0
