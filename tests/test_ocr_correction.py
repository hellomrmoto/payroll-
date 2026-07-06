"""The anti-corruption core: every corruption from the spec's Section 1 table
must be recovered to the correct code, and unknown codes must never be
fabricated."""

from wd_reader.ocr_correction import correct_code, normalize_glyphs


def test_reference_corruptions_recover_to_ground_truth():
    cases = [
        ("@1311", "Secretary I", "01311"),
        ("61313", "Secretary IIT", "01313"),   # 0->6 AND III->IIT
        ("e9eee", "Furniture Maintenance And Repair Occupations", "09000"),
        ("11150", "Janitor", "11150"),          # clean; must stay clean
    ]
    for raw, title, expected in cases:
        result = correct_code(raw, ocr_title=title)
        assert result.best is not None, f"{raw!r} produced no candidate"
        assert result.best.code == expected, (
            f"{raw!r} -> {result.best.code}, expected {expected}"
        )


def test_clean_code_is_not_flagged_as_corrupted():
    result = correct_code("11150", ocr_title="Janitor")
    assert result.was_corrupted is False
    assert result.best.code == "11150"


def test_corrupted_code_is_flagged_as_corrupted():
    for raw in ("@1311", "61313", "e9eee"):
        assert correct_code(raw).was_corrupted is True


def test_glyph_normalization():
    assert normalize_glyphs("@1311") == "01311"
    assert normalize_glyphs("e9eee") == "09000"
    assert normalize_glyphs("  11150  ") == "11150"


def test_unknown_code_is_not_invented():
    # 55555 is well-formed but not in the Directory; nothing near it either.
    result = correct_code("55555", ocr_title="Nonexistent Occupation")
    assert not result.recoverable or result.best.code != "55555"
    # It must never return 55555 as a *valid* recovered code.
    assert "55555" not in {c.code for c in result.candidates}


def test_title_disambiguates_between_close_codes():
    # 01311/01312/01313 are all one edit apart. The title must steer it.
    r1 = correct_code("0131l", ocr_title="Secretary I")     # l->1
    r3 = correct_code("0131l", ocr_title="Secretary III")
    assert r1.best.code == "01311"
    assert r3.best.code == "01313"
