from backend.config import parse_extra_animal_class_ids


def test_parse_extra_empty():
    assert parse_extra_animal_class_ids(None) == set()
    assert parse_extra_animal_class_ids("") == set()
    assert parse_extra_animal_class_ids("   ") == set()


def test_parse_extra_single_and_multiple():
    assert parse_extra_animal_class_ids("80") == {80}
    assert parse_extra_animal_class_ids("80, 1, 2") == {80, 1, 2}


def test_parse_extra_skips_invalid():
    assert parse_extra_animal_class_ids("80, bad, 1") == {80, 1}
