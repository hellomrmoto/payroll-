"""Core data model for SCA wage-determination extraction.

Every extracted *leaf* value is wrapped in a :class:`TracedValue` that carries a
``confidence`` score and a ``citation`` locating the value in the source
document.  The rule the whole product depends on is: **a wage rate is never
emitted as confirmed unless it passes confidence + cross-check, or a human
confirmed it.**  The schema makes that auditable — you cannot serialise a value
without also serialising where it came from and how sure we are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class ConfidenceLevel(str, Enum):
    """Where a field lands relative to the confidence thresholds.

    Boundaries mirror ``docs``/the skill: ``>=0.95`` *and* cross-checked
    auto-confirms; ``0.80-0.95`` is a one-click soft confirm; ``<0.80`` must be
    hard-confirmed by a human before the value is allowed downstream.
    """

    AUTO_CONFIRM = "auto_confirm"
    SOFT_CONFIRM = "soft_confirm"
    HARD_CONFIRM = "hard_confirm"


# Threshold constants — single source of truth, referenced by confidence.py.
AUTO_CONFIRM_THRESHOLD = Decimal("0.95")
SOFT_CONFIRM_THRESHOLD = Decimal("0.80")


@dataclass(frozen=True)
class Citation:
    """Traceable pointer back into the source document.

    ``page`` is 1-indexed.  A citation carries *either* a character span (for
    text-layer documents) *or* a pixel bounding box (for OCR'd images); both may
    be present when the ingest layer can supply them.
    """

    page: int
    char_span: Optional[tuple[int, int]] = None
    bbox: Optional[tuple[int, int, int, int]] = None  # (x0, y0, x1, y1) in px
    source_line: Optional[str] = None  # the raw line the value was read from

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"page": self.page}
        if self.char_span is not None:
            out["char_span"] = list(self.char_span)
        if self.bbox is not None:
            out["bbox"] = list(self.bbox)
        if self.source_line is not None:
            out["source_line"] = self.source_line
        return out


@dataclass
class FieldMeta:
    """Per-leaf provenance: confidence, citation, cross-check state, notes."""

    confidence: Decimal
    citation: Citation
    cross_checked: bool = False
    human_confirmed: bool = False
    # Machine-readable flags explaining any confidence penalty, e.g.
    # {"code_corrected", "rate_orphaned", "hw_mismatch"}.
    flags: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    # Alternative values worth showing a reviewer (e.g. directory codes an
    # ambiguous OCR read could map to). Carried on the meta so the confirmation
    # queue can be rebuilt losslessly after cross-check.
    candidates: list[Any] = field(default_factory=list)
    # An optional field's missing (None) value is an acceptable outcome and is
    # NOT queued for confirmation; a required field's is.
    optional: bool = False

    def level(self) -> ConfidenceLevel:
        from .confidence import classify  # local import avoids cycle

        return classify(self.confidence, self.cross_checked, self.human_confirmed)

    def requires_confirmation(self) -> bool:
        return self.level() != ConfidenceLevel.AUTO_CONFIRM and not self.human_confirmed

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": str(self.confidence),
            "level": self.level().value,
            "cross_checked": self.cross_checked,
            "human_confirmed": self.human_confirmed,
            "flags": sorted(self.flags),
            "citation": self.citation.to_dict(),
            "notes": list(self.notes),
        }


@dataclass
class TracedValue:
    """A single extracted value plus its :class:`FieldMeta`.

    ``value`` may be ``None`` — an explicitly-unknown field is a *first-class*
    outcome (e.g. WD parity we refuse to guess), never a silent omission.
    """

    value: Any
    meta: FieldMeta

    def to_dict(self) -> dict[str, Any]:
        value = self.value
        if isinstance(value, Decimal):
            value = str(value)  # exact decimal, never a float
        return {"value": value, "_meta": self.meta.to_dict()}


@dataclass
class Occupation:
    """One occupational-listing row: code + title + rate, each traced."""

    code: TracedValue
    title: TracedValue
    rate: TracedValue

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.to_dict(),
            "title": self.title.to_dict(),
            "rate": self.rate.to_dict(),
        }


class WDParity(str, Enum):
    """'Odd' vs 'even' WD numbering changes downstream fringe math, so it is
    mandatory to *attempt* and never guessed — indeterminate becomes ``None``.
    """

    ODD = "odd"
    EVEN = "even"


@dataclass
class WageDetermination:
    """The structured object a wage determination is turned into."""

    wd_number: TracedValue
    revision: TracedValue
    revision_date: TracedValue
    locality: TracedValue
    parity: TracedValue  # value is WDParity | None
    hw_fringe_rate: TracedValue  # value is Decimal | None ($/hr)
    vacation: TracedValue
    holidays: TracedValue
    occupations: list[Occupation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "wd_number": self.wd_number.to_dict(),
            "revision": self.revision.to_dict(),
            "revision_date": self.revision_date.to_dict(),
            "locality": self.locality.to_dict(),
            "parity": self.parity.to_dict(),
            "hw_fringe_rate": self.hw_fringe_rate.to_dict(),
            "vacation": self.vacation.to_dict(),
            "holidays": self.holidays.to_dict(),
            "occupations": [o.to_dict() for o in self.occupations],
        }


@dataclass
class ConfirmationItem:
    """One entry in the confirmation queue surfaced to a human reviewer."""

    path: str  # dotted path into the emitted object, e.g. "occupations[3].rate"
    reason: str
    confidence: Decimal
    current_value: Any
    candidates: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        value = self.current_value
        if isinstance(value, Decimal):
            value = str(value)
        cands = [str(c) if isinstance(c, Decimal) else c for c in self.candidates]
        return {
            "path": self.path,
            "reason": self.reason,
            "confidence": str(self.confidence),
            "current_value": value,
            "candidates": cands,
        }


class IngestMode(str, Enum):
    TEXT_LAYER = "text_layer"
    OCR = "ocr"


@dataclass
class CrossCheckReport:
    """Records whether the SAM.gov structured cross-check actually happened.

    ``performed`` may be ``True`` while ``available`` is ``False`` — meaning we
    tried and the source was down.  We never claim ``cross_checked`` on a field
    when ``available`` is ``False`` (see failure modes in the skill).
    """

    performed: bool = False
    available: bool = False
    source: str = "sam.gov"
    matched_fields: list[str] = field(default_factory=list)
    diverged_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "performed": self.performed,
            "available": self.available,
            "source": self.source,
            "matched_fields": list(self.matched_fields),
            "diverged_fields": list(self.diverged_fields),
        }


@dataclass
class ExtractionResult:
    """Top-level emitted object: the WD plus extraction provenance."""

    wage_determination: WageDetermination
    source_file: str
    ingest_mode: IngestMode
    cross_check: CrossCheckReport = field(default_factory=CrossCheckReport)
    confirmation_queue: list[ConfirmationItem] = field(default_factory=list)
    rejected: bool = False
    rejection_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "wage_determination": self.wage_determination.to_dict(),
            "extraction_meta": {
                "source_file": self.source_file,
                "ingest_mode": self.ingest_mode.value,
                "cross_check": self.cross_check.to_dict(),
                "rejected": self.rejected,
                "rejection_reason": self.rejection_reason,
                "fields_requiring_confirmation": [
                    c.to_dict() for c in self.confirmation_queue
                ],
            },
        }
