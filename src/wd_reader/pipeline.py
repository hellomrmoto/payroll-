"""Pipeline orchestrator (spec Section 3).

Wires the stages together: ingest/classify/extract -> structural parse -> field
extraction -> validation + confidence -> conflict resolution -> SAM.gov
cross-check -> emit structured object + confirmation queue.

The engine core (:func:`read_document`) operates on an already-extracted
:class:`~wd_reader.sources.Document`, which is why it is fully deterministic and
testable. :func:`read_pdf` adds the front stage: classify text-layer vs
image-only and choose the extractor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import conflict, crosscheck, extraction
from .confidence import DEFAULT_THRESHOLDS, Thresholds
from .confirmation import ConfirmationItem, build_queue
from .conflict import ContractMetadata
from .crosscheck import SamGovSource
from .schema import (
    ExtractionMeta,
    SourceType,
    WageDetermination,
)
from .sources import (
    Document,
    OcrExtractor,
    SourceUnavailable,
    TextLayerExtractor,
)


@dataclass
class ReadResult:
    wage_determination: WageDetermination
    confirmation_queue: list[ConfirmationItem]
    crosscheck: crosscheck.CrosscheckReport

    @property
    def has_pending_confirmations(self) -> bool:
        return bool(self.confirmation_queue)


class DocumentRejected(RuntimeError):
    """The document cannot be processed at all (spec Section 8). Raised instead
    of emitting partial silent data."""


def read_document(
    doc: Document,
    *,
    contract: Optional[ContractMetadata] = None,
    samgov: Optional[SamGovSource] = None,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> ReadResult:
    """Core engine: normalized Document -> structured, scored, gated result."""
    if not doc.lines or not any(ln.text.strip() for ln in doc.lines):
        raise DocumentRejected(
            "No readable text in document. If this is a scan, provide a higher-"
            "resolution image; the engine will not guess rates."
        )

    parsed = extraction.parse_document(doc)

    wd = WageDetermination(
        wd_number=parsed.wd_number,
        revision=parsed.revision,
        revision_date=parsed.revision_date,
        wd_type=parsed.wd_type,
        locality=parsed.locality,
        health_and_welfare=parsed.health_and_welfare,
        vacation=parsed.vacation,
        holidays=parsed.holidays,
        classifications=parsed.classifications,
        extraction_meta=ExtractionMeta(
            source_type=doc.source_type,
            ocr_dpi=doc.ocr_dpi,
            document_flags=list(doc.document_flags),
        ),
    )

    # Score H&W here (extraction handled classifications inline).
    _score_hw(wd)

    # Conflict resolution (in place), then cross-check, then gate.
    conflict.resolve(wd, contract)
    report = crosscheck.cross_check(wd, samgov)
    queue = build_queue(wd, thresholds)

    return ReadResult(wage_determination=wd, confirmation_queue=queue, crosscheck=report)


def read_pdf(
    pdf_path: str,
    *,
    contract: Optional[ContractMetadata] = None,
    samgov: Optional[SamGovSource] = None,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
    ocr_dpi: int = 300,
) -> ReadResult:
    """Front stage: classify + extract, then run the core engine.

    Attempts the text layer first; if it yields nothing usable, falls back to
    rasterize + OCR. A source backend that is unavailable is surfaced as a
    document-level rejection, never as silent partial data (spec Section 8).
    """
    doc = _extract_pdf(pdf_path, ocr_dpi=ocr_dpi)
    return read_document(
        doc, contract=contract, samgov=samgov, thresholds=thresholds
    )


def _extract_pdf(pdf_path: str, *, ocr_dpi: int) -> Document:
    # [2] classify: try text layer first.
    try:
        text_doc = TextLayerExtractor().extract(pdf_path)
        if _has_usable_text(text_doc):
            return text_doc
    except SourceUnavailable:
        text_doc = None

    # [3b] image-only -> rasterize + OCR.
    try:
        return OcrExtractor(dpi=ocr_dpi).extract(pdf_path)
    except SourceUnavailable as e:
        raise DocumentRejected(str(e)) from e


def _has_usable_text(doc: Document) -> bool:
    """A real text layer has substantive non-whitespace content across lines."""
    non_empty = [ln for ln in doc.lines if ln.text.strip()]
    return len(non_empty) >= 3


def _score_hw(wd: WageDetermination) -> None:
    from .confidence import score_hw_rate

    scored = score_hw_rate(wd.health_and_welfare.rate_per_hour)
    wd.health_and_welfare._meta.confidence = scored.confidence
    for f in scored.flags:
        wd.health_and_welfare._meta.add_flag(f)
