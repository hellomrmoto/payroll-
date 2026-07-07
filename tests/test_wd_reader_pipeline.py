"""End-to-end engine behavior on realistic (corrupted) documents, and the
absolute Phase 0 gate: zero silent wrong rates."""

from decimal import Decimal

import pytest

from wd_reader import (
    ContractMetadata,
    Disposition,
    Flag,
    InMemorySamGov,
    StructuredWd,
    WdType,
    DocumentRejected,
    read_document,
)
from wd_reader.confidence import disposition
from wd_reader.schema import SourceType
from wd_reader.sources import Document, TextLayerExtractor

from wd_reader_fixtures import (
    WD_2015_5657_OCR,
    WD_ORPHANED_RATE_OCR,
    WD_OUT_OF_BAND_OCR,
    WD_TEXTLAYER_CLEAN,
)


def _ocr_doc(text: str) -> Document:
    doc = TextLayerExtractor.from_text(text)
    doc.source_type = SourceType.OCR  # treat fixture as an OCR reading
    doc.ocr_dpi = 300
    return doc


# --------------------------------------------------------------------------- #
# Header / structural parse
# --------------------------------------------------------------------------- #
def test_reference_header_parsed():
    res = read_document(_ocr_doc(WD_2015_5657_OCR))
    wd = res.wage_determination
    assert wd.wd_number == "2015-5657"
    assert wd.revision == 24
    assert wd.revision_date == "2025-07-07"
    assert wd.locality.state == "CA"
    assert wd.locality.counties == ["Tulare"]
    assert wd.wd_type == WdType.ODD  # "paid per employee"


def test_reference_classifications_recovered():
    res = read_document(_ocr_doc(WD_2015_5657_OCR))
    by_code = {c.code: c for c in res.wage_determination.classifications}
    # Corrupted codes recovered to ground truth.
    assert "01311" in by_code
    assert by_code["01311"].base_rate_per_hour == Decimal("19.73")
    assert "01313" in by_code
    assert by_code["01313"].base_rate_per_hour == Decimal("24.60")
    assert "11150" in by_code
    assert by_code["11150"].base_rate_per_hour == Decimal("17.56")


def test_corrected_codes_carry_flag_and_citation():
    res = read_document(_ocr_doc(WD_2015_5657_OCR))
    sec1 = next(c for c in res.wage_determination.classifications if c.code == "01311")
    assert Flag.CODE_OCR_CORRECTED in sec1._meta.flags
    assert sec1._meta.citation is not None
    assert sec1._meta.citation.page == 1


# --------------------------------------------------------------------------- #
# THE gate: zero silent wrong rates (spec Section 9, criterion 1)
# --------------------------------------------------------------------------- #
def test_no_silent_wrong_rates_without_crosscheck():
    """Without a cross-check, NOTHING auto-confirms -- every rate is either
    correct-and-queued or correct-and-soft. A wrong rate passing as confirmed
    is an automatic fail; assert no auto-confirmations exist here at all."""
    res = read_document(_ocr_doc(WD_2015_5657_OCR))
    for c in res.wage_determination.classifications:
        disp = disposition(
            c._meta.confidence, cross_checked=c._meta.cross_checked
        )
        assert disp is not Disposition.AUTO_CONFIRMED, (
            f"{c.code} auto-confirmed without a cross-check"
        )


def test_corrected_rate_is_never_auto_confirmed_without_crosscheck():
    res = read_document(_ocr_doc(WD_2015_5657_OCR))
    paths = set(res.wage_determination.extraction_meta.fields_requiring_confirmation)
    # Every OCR-corrected classification code must appear in the queue.
    for i, c in enumerate(res.wage_determination.classifications):
        if Flag.CODE_OCR_CORRECTED in c._meta.flags:
            assert f"classifications[{i}].code" in paths


# --------------------------------------------------------------------------- #
# Cross-check raises confidence to auto-confirm (spec Section 5)
# --------------------------------------------------------------------------- #
def test_crosscheck_enables_autoconfirm_on_agreement():
    samgov = InMemorySamGov({
        "2015-5657": StructuredWd(
            wd_number="2015-5657",
            revision=24,
            rates_by_code={
                "01311": Decimal("19.73"),
                "01313": Decimal("24.60"),
                "11150": Decimal("17.56"),
            },
            hw_rate=Decimal("5.55"),
        )
    })
    res = read_document(_ocr_doc(WD_2015_5657_OCR), samgov=samgov)
    assert res.wage_determination.extraction_meta.cross_checked_against_samgov
    janitor = next(c for c in res.wage_determination.classifications if c.code == "11150")
    assert janitor._meta.cross_checked
    assert disposition(
        janitor._meta.confidence, cross_checked=janitor._meta.cross_checked
    ) is Disposition.AUTO_CONFIRMED


def test_crosscheck_divergence_surfaces_both_and_blocks_autoconfirm():
    # SAM.gov says Janitor is 17.56 but OCR read 99.99 -> divergence.
    text = WD_2015_5657_OCR.replace("11150 - Janitor 17.56", "11150 - Janitor 99.99")
    samgov = InMemorySamGov({
        "2015-5657": StructuredWd(
            wd_number="2015-5657", revision=24,
            rates_by_code={"11150": Decimal("17.56")}, hw_rate=Decimal("5.55"),
        )
    })
    res = read_document(_ocr_doc(text), samgov=samgov)
    janitor = next(c for c in res.wage_determination.classifications if c.code == "11150")
    assert Flag.CROSSCHECK_DIVERGENCE in janitor._meta.flags
    assert disposition(
        janitor._meta.confidence, cross_checked=janitor._meta.cross_checked
    ) is not Disposition.AUTO_CONFIRMED


# --------------------------------------------------------------------------- #
# Conflict resolution (spec Section 6)
# --------------------------------------------------------------------------- #
def test_orphaned_rate_is_flagged_not_guessed():
    res = read_document(_ocr_doc(WD_ORPHANED_RATE_OCR))
    janitor = next(c for c in res.wage_determination.classifications if c.code == "11150")
    # Janitor had no adjacent rate -> orphaned, low confidence, queued.
    assert janitor.base_rate_per_hour is None
    assert Flag.RATE_ORPHANED in janitor._meta.flags or Flag.RATE_MISSING in janitor._meta.flags
    assert janitor._meta.confidence < 0.80


def test_column_separated_rate_is_flagged_orphaned():
    """The two-column failure: a rate present on the code line but resolved
    from a different layout column. The OCR path marks the line
    ``rate_orphaned``; the engine must flag RATE_ORPHANED and refuse to
    auto-confirm the pairing (spec Section 5)."""
    doc = TextLayerExtractor.from_text("11150 - Janitor 17.56")
    doc.source_type = SourceType.OCR
    doc.ocr_dpi = 300
    doc.lines[0].rate_orphaned = True  # OCR detected the column mismatch
    res = read_document(doc)
    janitor = res.wage_determination.classifications[0]
    assert janitor.base_rate_per_hour == Decimal("17.56")
    assert Flag.RATE_ORPHANED in janitor._meta.flags
    assert janitor._meta.confidence < 0.80
    assert disposition(
        janitor._meta.confidence, cross_checked=janitor._meta.cross_checked
    ) is not Disposition.AUTO_CONFIRMED


def test_out_of_band_rate_is_flagged():
    res = read_document(_ocr_doc(WD_OUT_OF_BAND_OCR))
    janitor = next(c for c in res.wage_determination.classifications if c.code == "11150")
    assert janitor.base_rate_per_hour == Decimal("175.60")
    assert Flag.RATE_OUT_OF_BAND in janitor._meta.flags
    assert janitor._meta.confidence < 0.80


def test_locality_mismatch_hard_flag():
    contract = ContractMetadata(pop_state="CA", pop_county="Fresno")  # not Tulare
    res = read_document(_ocr_doc(WD_2015_5657_OCR), contract=contract)
    assert Flag.LOCALITY_MISMATCH in res.wage_determination.locality._meta.flags


def test_indeterminate_wd_type_blocks_and_queues():
    text = WD_2015_5657_OCR.replace(
        "Fringe benefits are paid per employee on all hours.", "Fringe benefits."
    )
    res = read_document(_ocr_doc(text))
    assert res.wage_determination.wd_type is None
    assert "wd_type" in res.wage_determination.extraction_meta.fields_requiring_confirmation


def test_duplicate_title_kept_both_and_flagged():
    text = WD_TEXTLAYER_CLEAN + "\n11240 - Janitor 18.42\n"
    doc = TextLayerExtractor.from_text(text)
    res = read_document(doc)
    janitors = [c for c in res.wage_determination.classifications
                if c.title and c.title.lower() == "janitor"]
    assert len(janitors) == 2
    assert all(Flag.DUPLICATE_TITLE in c._meta.flags for c in janitors)


# --------------------------------------------------------------------------- #
# Failure modes (spec Section 8)
# --------------------------------------------------------------------------- #
def test_empty_document_is_rejected_not_guessed():
    with pytest.raises(DocumentRejected):
        read_document(Document(lines=[]))


def test_hw_rate_matches_known_schedule():
    res = read_document(_ocr_doc(WD_2015_5657_OCR))
    hw = res.wage_determination.health_and_welfare
    assert hw.rate_per_hour == Decimal("5.55")
    assert hw._meta.confidence >= 0.95  # matches published national rate
