import unittest

from sca_extraction.occupations import Directory, default_directory
from sca_extraction.ocr_corrections import repair_code, repair_title_roman


class TestRepairCode(unittest.TestCase):
    def test_clean_valid_code_passes_through(self):
        r = repair_code("01311")
        self.assertTrue(r.is_clean_valid)
        self.assertEqual(r.corrected, "01311")
        self.assertFalse(r.was_corrupt)

    def test_leading_zero_read_as_at_sign(self):
        # '@1311' -> '01311'
        r = repair_code("@1311")
        self.assertEqual(r.corrected, "01311")
        self.assertTrue(r.was_corrupt)
        self.assertFalse(r.ambiguous)

    def test_zero_read_as_six(self):
        # '61313' -> '01313' (only directory match)
        r = repair_code("61313")
        self.assertEqual(r.corrected, "01313")

    def test_zero_read_as_e(self):
        # 'e9e1e' -> '09010' which is in the directory
        r = repair_code("e9e1e")
        self.assertEqual(r.corrected, "09010")

    def test_unknown_glyph_is_unresolved(self):
        r = repair_code("0#311")
        self.assertIsNone(r.corrected)
        self.assertEqual(r.candidates, [])

    def test_wrong_length_unresolved(self):
        r = repair_code("013")
        self.assertIsNone(r.corrected)
        self.assertIn("length", r.reason)

    def test_five_clean_digits_not_in_directory(self):
        r = repair_code("99999")
        self.assertIsNone(r.corrected)
        self.assertEqual(r.reason, "no_directory_match")

    def test_ambiguous_multiple_matches_not_auto_resolved(self):
        # Custom directory where two codes are both reachable from one raw read.
        # '0' can be read as {0,6,8}; both 01311 and 81311 exist -> ambiguous.
        d = Directory({"01311": "A", "81311": "B"})
        r = repair_code("0131l", d)  # trailing l -> 1
        self.assertIsNone(r.corrected)
        self.assertTrue(r.ambiguous)
        self.assertEqual(sorted(r.candidates), ["01311", "81311"])

    def test_separators_are_stripped(self):
        r = repair_code(" 013-11 ")
        self.assertEqual(r.corrected, "01311")


class TestRepairTitleRoman(unittest.TestCase):
    def test_iit_becomes_iii(self):
        fixed, changed = repair_title_roman("Secretary IIT")
        self.assertEqual(fixed, "Secretary III")
        self.assertTrue(changed)

    def test_clean_title_unchanged(self):
        fixed, changed = repair_title_roman("Accounting Clerk I")
        self.assertEqual(fixed, "Accounting Clerk I")
        self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()
