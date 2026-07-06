import unittest
from decimal import Decimal

from sca_extraction.confidence import classify
from sca_extraction.schema import Citation, ConfidenceLevel, WDParity
from sca_extraction.validation import (
    parse_parity,
    parse_rate,
    score_code,
    score_hw,
    score_parity,
    score_rate,
)

CIT = Citation(page=1)


class TestParseRate(unittest.TestCase):
    def test_exact_decimal_no_float(self):
        v = parse_rate("18.42")
        self.assertEqual(v, Decimal("18.42"))
        self.assertIsInstance(v, Decimal)

    def test_dollar_sign_and_spaces(self):
        self.assertEqual(parse_rate("$ 22.05"), Decimal("22.05"))

    def test_thousands_separator(self):
        self.assertEqual(parse_rate("1,234.56"), Decimal("1234.56"))

    def test_unparseable_returns_none(self):
        self.assertIsNone(parse_rate("n/a"))


class TestScoreRate(unittest.TestCase):
    def test_clean_rate_high_confidence(self):
        tv = score_rate("18.42", CIT, is_ocr=False)
        self.assertEqual(tv.value, Decimal("18.42"))
        self.assertGreaterEqual(tv.meta.confidence, Decimal("0.95"))

    def test_out_of_band_penalised(self):
        tv = score_rate("500.00", CIT, is_ocr=False)
        self.assertIn("rate_out_of_band", tv.meta.flags)
        self.assertLess(tv.meta.confidence, Decimal("0.80"))

    def test_orphaned_rate_low_confidence(self):
        tv = score_rate("18.42", CIT, is_ocr=True, orphaned=True)
        self.assertIn("rate_orphaned", tv.meta.flags)
        # Orphaned + OCR should require confirmation (hard/soft, not auto).
        self.assertTrue(tv.meta.requires_confirmation())

    def test_non_positive_rejected(self):
        tv = score_rate("0.00", CIT, is_ocr=False)
        self.assertIsNone(tv.value)

    def test_unparseable_rejected(self):
        tv = score_rate("see note", CIT, is_ocr=False)
        self.assertIsNone(tv.value)
        self.assertIn("rate_unparseable", tv.meta.flags)


class TestScoreHW(unittest.TestCase):
    def test_matches_national_boosts_and_cross_checks(self):
        tv = score_hw("$5.55 per hour", CIT, is_ocr=False)
        self.assertEqual(tv.value, Decimal("5.55"))
        self.assertTrue(tv.meta.cross_checked)
        self.assertIn("hw_matches_national", tv.meta.flags)

    def test_mismatch_penalised(self):
        tv = score_hw("$9.99 per hour", CIT, is_ocr=False)
        self.assertEqual(tv.value, Decimal("9.99"))
        self.assertFalse(tv.meta.cross_checked)
        self.assertIn("hw_mismatch", tv.meta.flags)

    def test_prior_schedule_value_still_matches(self):
        tv = score_hw("$5.36", CIT, is_ocr=False)
        self.assertTrue(tv.meta.cross_checked)


class TestScoreCode(unittest.TestCase):
    def test_clean_code_auto_level_without_crosscheck_is_soft_or_auto(self):
        tv, repair = score_code("01311", CIT, is_ocr=False)
        self.assertEqual(tv.value, "01311")
        # High confidence but not cross-checked -> not auto-confirm by itself.
        self.assertNotEqual(tv.meta.level(), ConfidenceLevel.HARD_CONFIRM)

    def test_corrected_code_flagged_and_penalised(self):
        tv, repair = score_code("@1311", CIT, is_ocr=True)
        self.assertEqual(tv.value, "01311")
        self.assertIn("code_corrected", tv.meta.flags)

    def test_ambiguous_code_yields_none_and_candidates(self):
        from sca_extraction.occupations import Directory

        d = Directory({"01311": "A", "81311": "B"})
        tv, repair = score_code("0131l", CIT, is_ocr=True, directory=d)
        self.assertIsNone(tv.value)
        self.assertIn("code_ambiguous", tv.meta.flags)
        self.assertTrue(tv.meta.requires_confirmation())
        self.assertEqual(sorted(tv.meta.candidates), ["01311", "81311"])


class TestParity(unittest.TestCase):
    def test_odd(self):
        self.assertEqual(parse_parity("2015-4281"), WDParity.ODD)

    def test_even(self):
        self.assertEqual(parse_parity("2015-4280"), WDParity.EVEN)

    def test_indeterminate_returns_none(self):
        self.assertIsNone(parse_parity(None))
        self.assertIsNone(parse_parity(""))

    def test_score_parity_null_when_no_wd_number(self):
        tv = score_parity(None, CIT, Decimal("0.0"))
        self.assertIsNone(tv.value)
        self.assertIn("parity_indeterminate", tv.meta.flags)
        self.assertTrue(tv.meta.requires_confirmation())

    def test_score_parity_inherits_wd_confidence(self):
        tv = score_parity("2015-4281", CIT, Decimal("0.90"))
        self.assertEqual(tv.value, WDParity.ODD)
        self.assertEqual(tv.meta.confidence, Decimal("0.90"))


class TestClassify(unittest.TestCase):
    def test_auto_requires_crosscheck(self):
        self.assertEqual(
            classify(Decimal("0.99"), cross_checked=False), ConfidenceLevel.SOFT_CONFIRM
        )
        self.assertEqual(
            classify(Decimal("0.99"), cross_checked=True), ConfidenceLevel.AUTO_CONFIRM
        )

    def test_hard_below_080(self):
        self.assertEqual(
            classify(Decimal("0.79"), cross_checked=True), ConfidenceLevel.HARD_CONFIRM
        )

    def test_human_confirm_overrides(self):
        self.assertEqual(
            classify(Decimal("0.10"), cross_checked=False, human_confirmed=True),
            ConfidenceLevel.AUTO_CONFIRM,
        )


if __name__ == "__main__":
    unittest.main()
