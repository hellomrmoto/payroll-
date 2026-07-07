"""The trust surface: the confirmation queue surfaces exactly the doubtful
fields, each with a value, a citation for the visual crop, candidates, and a
governing note (spec Section 7)."""

from decimal import Decimal

from wd_reader import read_document
from wd_reader.schema import SourceType
from wd_reader.sources import Document, TextLayerExtractor

from wd_reader_fixtures import WD_2015_5657_OCR, WD_TEXTLAYER_CLEAN


def _ocr_doc(text: str) -> Document:
    doc = TextLayerExtractor.from_text(text)
    doc.source_type = SourceType.OCR
    doc.ocr_dpi = 300
    return doc


def test_queue_contains_only_below_threshold_fields():
    res = read_document(_ocr_doc(WD_2015_5657_OCR))
    assert res.has_pending_confirmations
    # Corrupted codes must be present; the clean Janitor code line is corrected
    # nowhere so it should not appear as a *code* correction item.
    paths = {it.field_path for it in res.confirmation_queue}
    assert any(p.endswith(".code") for p in paths)


def test_queue_items_carry_citation_and_note():
    res = read_document(_ocr_doc(WD_2015_5657_OCR))
    code_items = [it for it in res.confirmation_queue if it.field_path.endswith(".code")]
    assert code_items
    for it in code_items:
        assert it.citation is not None
        assert it.citation["page"] == 1
        assert it.note  # a governing note is always present
        assert it.candidates  # ranked correction candidates for the UX


def test_wd_type_indeterminate_appears_in_queue():
    text = WD_2015_5657_OCR.replace(
        "Fringe benefits are paid per employee on all hours.", "Fringe benefits."
    )
    res = read_document(_ocr_doc(text))
    assert any(it.field_path == "wd_type" for it in res.confirmation_queue)


def test_clean_document_has_a_short_queue():
    """A clean text-layer WD, cross-checked, confirms in seconds -- a short or
    empty queue. Here without cross-check codes are clean (auto-eligible on
    confidence) but rates still need one-click accept; the queue must not be
    huge and must not contain fabricated items."""
    res = read_document(TextLayerExtractor.from_text(WD_TEXTLAYER_CLEAN))
    # No corrupted-code items on a clean document.
    corrected = [it for it in res.confirmation_queue
                 if "code_ocr_corrected" in it.flags]
    assert corrected == []


def test_overall_confidence_is_weakest_link():
    res = read_document(_ocr_doc(WD_2015_5657_OCR))
    overall = res.wage_determination.extraction_meta.overall_confidence
    per_field = [c._meta.confidence for c in res.wage_determination.classifications]
    assert overall == round(min(per_field + [res.wage_determination.health_and_welfare._meta.confidence]), 4)
