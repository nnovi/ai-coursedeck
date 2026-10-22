from coursedeck.schema import FIELD_GROUPS, LectureCard


def test_field_groups_cover_schema_exactly():
    grouped = [f for fields in FIELD_GROUPS.values() for f in fields]
    assert sorted(grouped) == sorted(LectureCard.model_fields)
    assert len(grouped) == len(set(grouped))


def test_json_schema_is_closed_and_fully_required():
    # Structured-output backends need every property listed as required and no extras.
    schema = LectureCard.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(LectureCard.model_fields)


def test_minimal_card_validates():
    card = LectureCard.model_validate({
        "course_title": None, "course_code": None, "institution": None, "lecturers": [],
        "lecture_number": None, "lecture_title": None, "year": None, "term": None,
        "discipline": "physics", "doc_type": "lecture_notes",
        "topics": [], "key_terms": [], "references": [],
    })
    assert card.discipline == "physics"
