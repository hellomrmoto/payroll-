"""Deterministic output schema for the WD Reader (spec Section 4).

Every wage determination produces exactly this shape. Rates are stored as
``decimal.Decimal`` so they never drift through binary float rounding, and
serialize back to JSON numbers with their exact written form.

The types here are intentionally plain dataclasses (no third-party runtime
dependency) so the correctness-critical core has nothing between it and the
standard library.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Enums / flags
# --------------------------------------------------------------------------- #
class WdType(str, Enum):
    """Odd = per-employee fringe; even = average-cost. Drives fringe math
    (29 CFR 4.52 / 4.175). Never guessed -- ``None`` goes to confirmation."""

    ODD = "odd"
    EVEN = "even"


class Basis(str, Enum):
    PER_HOUR_UP_TO_40 = "per_hour_up_to_40"
    AVERAGE_COST_ALL_HOURS = "average_cost_all_hours"


class SourceType(str, Enum):
    TEXT_LAYER = "text_layer"
    OCR = "ocr"


class Flag(str, Enum):
    """Per-field diagnostic flags (spec Sections 4-6)."""

    CODE_OCR_CORRECTED = "code_ocr_corrected"
    CODE_UNRECOVERABLE = "code_unrecoverable"
    RATE_ORPHANED = "rate_orphaned"
    RATE_OUT_OF_BAND = "rate_out_of_band"
    RATE_MISSING = "rate_missing"
    DUPLICATE_TITLE = "duplicate_title"
    LOCALITY_MISMATCH = "locality_mismatch"
    HW_UNKNOWN = "hw_unknown"
    CROSSCHECK_DIVERGENCE = "crosscheck_divergence"
    WD_TYPE_INDETERMINATE = "wd_type_indeterminate"


# --------------------------------------------------------------------------- #
# Metadata attached to every leaf value
# --------------------------------------------------------------------------- #
@dataclass
class Citation:
    """Where a value was read from. Makes the citation visual downstream."""

    page: int
    span: str  # e.g. "line 54 / bbox[x0,y0,x1,y1]" or char-range for text layer
    bbox: Optional[list[float]] = None  # [x0, y0, x1, y1] in PDF points, if OCR


@dataclass
class FieldMeta:
    confidence: float = 0.0  # 0.0-1.0
    citation: Optional[Citation] = None
    flags: list[Flag] = field(default_factory=list)
    # Ranked correction candidates surfaced to the confirmation UX, if any.
    candidates: list[str] = field(default_factory=list)
    cross_checked: bool = False

    def add_flag(self, flag: Optional[Flag]) -> None:
        if flag is not None and flag not in self.flags:
            self.flags.append(flag)


# --------------------------------------------------------------------------- #
# Domain objects
# --------------------------------------------------------------------------- #
@dataclass
class Locality:
    state: Optional[str] = None
    counties: list[str] = field(default_factory=list)
    raw_text: str = ""
    _meta: FieldMeta = field(default_factory=FieldMeta)


@dataclass
class HealthAndWelfare:
    rate_per_hour: Optional[Decimal] = None
    eo13706_rate_per_hour: Optional[Decimal] = None
    basis: Optional[Basis] = None
    weekly: Optional[Decimal] = None
    monthly: Optional[Decimal] = None
    _meta: FieldMeta = field(default_factory=FieldMeta)


@dataclass
class TextBlock:
    """Free-text field (vacation) carried verbatim with its citation."""

    text: str = ""
    _meta: FieldMeta = field(default_factory=FieldMeta)


@dataclass
class Holidays:
    count: Optional[int] = None
    named: list[str] = field(default_factory=list)
    _meta: FieldMeta = field(default_factory=FieldMeta)


@dataclass
class Classification:
    code: Optional[str] = None
    title: Optional[str] = None
    base_rate_per_hour: Optional[Decimal] = None
    occupation_family: Optional[str] = None
    _meta: FieldMeta = field(default_factory=FieldMeta)


@dataclass
class ExtractionMeta:
    source_type: SourceType = SourceType.OCR
    ocr_dpi: Optional[int] = None
    cross_checked_against_samgov: bool = False
    overall_confidence: float = 0.0
    fields_requiring_confirmation: list[str] = field(default_factory=list)
    # Document-level rejection / low-confidence reasons (spec Section 8).
    document_flags: list[str] = field(default_factory=list)


@dataclass
class WageDetermination:
    wd_number: Optional[str] = None
    revision: Optional[int] = None
    revision_date: Optional[str] = None  # YYYY-MM-DD
    wd_type: Optional[WdType] = None
    locality: Locality = field(default_factory=Locality)
    health_and_welfare: HealthAndWelfare = field(default_factory=HealthAndWelfare)
    vacation: TextBlock = field(default_factory=TextBlock)
    holidays: Holidays = field(default_factory=Holidays)
    classifications: list[Classification] = field(default_factory=list)
    extraction_meta: ExtractionMeta = field(default_factory=ExtractionMeta)

    def to_dict(self) -> dict[str, Any]:
        """Native tree with Decimals preserved exactly (for programmatic use)."""
        return _encode(self)

    def to_json(self, *, indent: Optional[int] = 2) -> str:
        """JSON text. Decimals are emitted as JSON numbers using Python's
        shortest round-trip repr, which is textually exact for monetary
        values (e.g. Decimal('17.56') -> ``17.56``). Exact-decimal arithmetic
        happens on the ``Decimal`` objects in :meth:`to_dict`; drift is
        impossible there. JSON number text is inherently decimal, so the
        rendered form is faithful."""
        return json.dumps(
            _encode(self), indent=indent, ensure_ascii=False, cls=_DecimalEncoder
        )


# --------------------------------------------------------------------------- #
# Serialization: enums -> their values, Citation -> compact dict, dataclasses
# -> dicts. Decimals are left intact so to_dict() stays exact; to_json()
# renders them via _DecimalEncoder.
# --------------------------------------------------------------------------- #
def _encode(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Citation):
        d: dict[str, Any] = {"page": obj.page, "span": obj.span}
        if obj.bbox is not None:
            d["bbox"] = obj.bbox
        return d
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _encode(getattr(obj, k)) for k in _dataclass_fields(obj)}
    if isinstance(obj, list):
        return [_encode(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _encode(v) for k, v in obj.items()}
    return obj


def _dataclass_fields(obj: Any) -> list[str]:
    return list(asdict(obj).keys())


class _DecimalEncoder(json.JSONEncoder):
    """Renders Decimal as a JSON number. ``float()`` of a monetary Decimal
    round-trips to its shortest exact repr in Python 3, so the emitted text
    matches the stored value."""

    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)
