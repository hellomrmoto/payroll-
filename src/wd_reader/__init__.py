"""WD Reader — the make-or-break engine of Clean Payroll and Ledger.

Turns a government wage determination PDF (including scanned, image-only,
two-column ones) into a deterministic, typed, citation-traceable data structure
with per-field confidence and a human-confirmation queue for anything the
machine is not sure about.

Cardinal rule (spec Section 3): a rate is only emitted downstream as
*confirmed* if it is either (a) above threshold AND cross-checked, or (b)
human-confirmed. Everything else lands in the confirmation queue. Confidence
scoring and human confirmation are the safety system, not features.

Public API
----------
    read_document(doc, ...)   -> ReadResult    # deterministic core
    read_pdf(path, ...)       -> ReadResult    # + front-stage extraction

See the schema module for the fixed output shape.
"""

from __future__ import annotations

from .conflict import ContractMetadata
from .confidence import DEFAULT_THRESHOLDS, Disposition, Thresholds
from .confirmation import ConfirmationItem
from .crosscheck import InMemorySamGov, SamGovSource, StructuredWd
from .pipeline import (
    DocumentRejected,
    ReadResult,
    read_document,
    read_pdf,
)
from .schema import (
    Basis,
    Classification,
    Flag,
    HealthAndWelfare,
    Holidays,
    Locality,
    SourceType,
    WageDetermination,
    WdType,
)
from .sources import (
    Document,
    OcrExtractor,
    SourceLine,
    SourceUnavailable,
    TextLayerExtractor,
)

__version__ = "1.0.0"

__all__ = [
    "read_document",
    "read_pdf",
    "ReadResult",
    "DocumentRejected",
    "ContractMetadata",
    "Thresholds",
    "DEFAULT_THRESHOLDS",
    "Disposition",
    "ConfirmationItem",
    "SamGovSource",
    "StructuredWd",
    "InMemorySamGov",
    "WageDetermination",
    "Classification",
    "HealthAndWelfare",
    "Holidays",
    "Locality",
    "Flag",
    "WdType",
    "Basis",
    "SourceType",
    "Document",
    "SourceLine",
    "TextLayerExtractor",
    "OcrExtractor",
    "SourceUnavailable",
]
