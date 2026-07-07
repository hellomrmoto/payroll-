import json
import os
import unittest
from decimal import Decimal

from sca_extraction import extract_from_pages, reconcile, unavailable_provider
from sca_extraction.parsing import parse_document
from sca_extraction.schema import ConfidenceLevel

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load_pages(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as fh:
        return [(1, fh.read())]


class FakeSam:
    """Structured SAM.gov record used to exercise cross-check reconciliation."""

    def __init__(self, wd_number, revision, hw, rates_by_code):
        self.wd_number = wd_number
        self.revision = revision
        self.hw_fringe_rate = hw
        self.rates_by_code = rates_by_code


class TestParsing(unittest.TestCase):
    def test_clean_textlayer_rows_and_header(self):
        raw = parse_document(load_pages("clean_textlayer.txt"))
        self.assertEqual(raw.wd_number.raw, "2015-4281")
        self.assertEqual(raw.revision.raw, "24")
        self.assertEqual(raw.locality.raw, "California")
        self.assertEqual(len(raw.rows), 7)
        self.assertEqual(raw.rows[0].code.raw, "01011")
        self.assertEqual(raw.rows[0].rate.raw, "18.42")
        self.assertIsNotNone(raw.hw_fringe)

    def test_two_column_orphan_is_reunited(self):
        raw = parse_document(load_pages("two_column_orphan.txt"))
        # The lone "18.42" line is reattached to the rateless Accounting Clerk row.
        self.assertEqual(len(raw.rows), 2)
        acc = raw.rows[0]
        self.assertEqual(acc.code.raw, "01011")
        self.assertIsNotNone(acc.rate)
        self.assertEqual(acc.rate.raw, "18.42")
        self.assertTrue(acc.orphaned_rate)


class TestExtractClean(unittest.TestCase):
    def setUp(self):
        self.result = extract_from_pages(
            load_pages("clean_textlayer.txt"), "clean.txt", is_ocr=False
        )

    def test_occupations_extracted(self):
        wd = self.result.wage_determination
        self.assertEqual(len(wd.occupations), 7)
        self.assertEqual(wd.occupations[0].code.value, "01011")
        self.assertEqual(wd.occupations[0].rate.value, Decimal("18.42"))

    def test_parity_is_odd(self):
        self.assertEqual(self.result.wage_determination.parity.value.value, "odd")

    def test_hw_matches_national_and_auto_confirms(self):
        hw = self.result.wage_determination.hw_fringe_rate
        self.assertEqual(hw.value, Decimal("5.55"))
        self.assertTrue(hw.meta.cross_checked)
        self.assertEqual(hw.meta.level(), ConfidenceLevel.AUTO_CONFIRM)
        # Auto-confirmed field must NOT be in the confirmation queue.
        paths = {c.path for c in self.result.confirmation_queue}
        self.assertNotIn("wage_determination.hw_fringe_rate", paths)

    def test_uncrosschecked_rates_are_soft_confirm(self):
        # Clean but not SAM-cross-checked -> soft confirm, so still queued.
        rate = self.result.wage_determination.occupations[0].rate
        self.assertEqual(rate.meta.level(), ConfidenceLevel.SOFT_CONFIRM)
        paths = {c.path for c in self.result.confirmation_queue}
        self.assertIn("occupations[0].rate", paths)

    def test_serialises_to_json_without_floats(self):
        payload = self.result.to_dict()
        json.dumps(payload, sort_keys=True)  # must be JSON-serialisable, no TypeError

        # Rate value serialised as an exact string, never a float.
        rate_node = payload["wage_determination"]["occupations"][0]["rate"]["value"]
        self.assertEqual(rate_node, "18.42")
        self.assertIsInstance(rate_node, str)

        def assert_no_floats(node):
            if isinstance(node, float):
                self.fail(f"float leaked into output: {node!r}")
            if isinstance(node, dict):
                for v in node.values():
                    assert_no_floats(v)
            elif isinstance(node, list):
                for v in node:
                    assert_no_floats(v)

        assert_no_floats(payload)

    def test_deterministic_output(self):
        again = extract_from_pages(
            load_pages("clean_textlayer.txt"), "clean.txt", is_ocr=False
        )
        self.assertEqual(
            json.dumps(self.result.to_dict(), sort_keys=True),
            json.dumps(again.to_dict(), sort_keys=True),
        )


class TestExtractOCRCorrupted(unittest.TestCase):
    def setUp(self):
        self.result = extract_from_pages(
            load_pages("ocr_corrupted.txt"), "ocr.txt", is_ocr=True
        )

    def test_corrupt_codes_are_corrected(self):
        occ = self.result.wage_determination.occupations
        self.assertEqual(occ[0].code.value, "01311")  # @1311 -> 01311
        self.assertIn("code_corrected", occ[0].code.meta.flags)
        self.assertEqual(occ[1].code.value, "01313")  # 61313
        self.assertIn("code_corrected", occ[1].code.meta.flags)

    def test_roman_numeral_title_repaired(self):
        title = self.result.wage_determination.occupations[1].title
        self.assertEqual(title.value, "Secretary III")
        self.assertIn("title_roman_corrected", title.meta.flags)

    def test_corrected_codes_require_confirmation(self):
        paths = {c.path for c in self.result.confirmation_queue}
        self.assertIn("occupations[0].code", paths)


class TestOrphanRate(unittest.TestCase):
    def test_orphaned_rate_flagged_low_confidence(self):
        result = extract_from_pages(
            load_pages("two_column_orphan.txt"), "orphan.txt", is_ocr=True
        )
        rate = result.wage_determination.occupations[0].rate
        self.assertEqual(rate.value, Decimal("18.42"))
        self.assertIn("rate_orphaned", rate.meta.flags)
        self.assertTrue(rate.meta.requires_confirmation())


class TestCrossCheck(unittest.TestCase):
    def _clean(self):
        return extract_from_pages(
            load_pages("clean_textlayer.txt"), "clean.txt", is_ocr=False
        )

    def test_unavailable_provider_claims_no_crosscheck(self):
        result = reconcile(self._clean(), unavailable_provider)
        self.assertTrue(result.cross_check.performed)
        self.assertFalse(result.cross_check.available)
        # No occupation rate should be marked cross_checked.
        for occ in result.wage_determination.occupations:
            self.assertFalse(occ.rate.meta.cross_checked)

    def test_matching_provider_auto_confirms_rate(self):
        rates = {
            "01011": Decimal("18.42"),
            "01012": Decimal("20.67"),
            "01013": Decimal("23.11"),
            "01311": Decimal("22.05"),
            "01313": Decimal("27.88"),
            "11150": Decimal("17.34"),
            "27101": Decimal("19.90"),
        }
        sam = FakeSam("2015-4281", "24", Decimal("5.55"), rates)
        result = reconcile(self._clean(), lambda n, r: sam)
        self.assertTrue(result.cross_check.available)
        rate0 = result.wage_determination.occupations[0].rate
        self.assertTrue(rate0.meta.cross_checked)
        self.assertEqual(rate0.meta.level(), ConfidenceLevel.AUTO_CONFIRM)
        paths = {c.path for c in result.confirmation_queue}
        self.assertNotIn("occupations[0].rate", paths)

    def test_divergence_surfaces_both_and_penalises(self):
        rates = {"01011": Decimal("99.99")}  # SAM disagrees with document's 18.42
        sam = FakeSam("2015-4281", "24", Decimal("5.55"), rates)
        result = reconcile(self._clean(), lambda n, r: sam)
        rate0 = result.wage_determination.occupations[0].rate
        self.assertIn("cross_check_divergence", rate0.meta.flags)
        # Local value is preserved (never silently overwritten).
        self.assertEqual(rate0.value, Decimal("18.42"))
        self.assertIn("cross-check divergence", " ".join(rate0.meta.notes))
        self.assertEqual(result.cross_check.diverged_fields, ["occupations[0].rate"])


if __name__ == "__main__":
    unittest.main()
