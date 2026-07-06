"""SCA wage-determination extraction.

Turn a government Service Contract Act (SCA) wage determination — including
scanned/image-only and two-column documents — into a deterministic,
citation-traceable data object with per-field confidence and a human
confirmation queue.

Core principle: never emit a wage rate as confirmed unless it passes
confidence + cross-check, or a human confirmed it. Uncertainty surfaced is
success; false confidence is failure.

High-level entry points:
    extract_from_pages(pages, ...)   -> score already-extracted page text
    extract_wage_determination(path) -> full pipeline from a PDF on disk
"""

from __future__ import annotations

from typing import Optional

from .crosscheck import SamProvider, reconcile, unavailable_provider
from .extractor import build_confirmation_queue, extract, extract_from_pages
from .occupations import Directory, default_directory, load_directory
from .parsing import parse_document
from .schema import (
    ConfidenceLevel,
    ConfirmationItem,
    CrossCheckReport,
    ExtractionResult,
    IngestMode,
    Occupation,
    WageDetermination,
    WDParity,
)

__all__ = [
    "extract_from_pages",
    "extract",
    "extract_wage_determination",
    "build_confirmation_queue",
    "reconcile",
    "unavailable_provider",
    "SamProvider",
    "parse_document",
    "Directory",
    "default_directory",
    "load_directory",
    "ExtractionResult",
    "WageDetermination",
    "Occupation",
    "ConfirmationItem",
    "CrossCheckReport",
    "ConfidenceLevel",
    "IngestMode",
    "WDParity",
]

__version__ = "0.1.0"


def extract_wage_determination(
    pdf_path: str,
    *,
    force_ocr: bool = False,
    sam_provider: Optional[SamProvider] = None,
    directory: Optional[Directory] = None,
) -> ExtractionResult:
    """Full pipeline: ingest a PDF, parse, score, and (optionally) cross-check.

    ``ingest`` is imported lazily so the scoring core stays importable without
    any PDF tooling installed.
    """
    from .ingest import ingest_pdf

    doc = ingest_pdf(pdf_path, force_ocr=force_ocr)
    result = extract(
        parse_document(doc.pages),
        source_file=doc.source_file,
        is_ocr=doc.is_ocr,
        directory=directory,
    )
    if sam_provider is not None:
        result = reconcile(result, sam_provider)
    return result
