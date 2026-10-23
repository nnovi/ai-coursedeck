from coursedeck.dataset.pdf import format_pages, parse_pages, to_ranges


def test_parse_and_format_round_trip():
    for spec in ["1-3,30-37", "5", "1,4-9", "1-20"]:
        assert format_pages(parse_pages(spec)) == spec


def test_to_ranges_merges_adjacent_pages():
    # title page 1 directly followed by a lecture starting on page 2
    assert to_ranges([1] + list(range(2, 21))) == [(1, 20)]
    assert to_ranges([1, 2, 3, 30, 31]) == [(1, 3), (30, 31)]
