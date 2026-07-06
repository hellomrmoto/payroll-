"""SAM.gov structured-WD cross-check (spec Sections 2, 3 step 8, 5, 8).

When a machine-readable WD for the same number+revision exists, it is
authoritative: matching fields get their confidence set high; divergences
surface *both* values for a human to decide; the PDF OCR is used only for
citation-span mapping.

The live SAM.gov client is an adapter behind :class:`SamGovSource`. The
deterministic reconciliation logic works against any object satisfying that
protocol, so it is fully testable with an in-memory fixture and does not
require network access. When no source is available the engine proceeds on OCR
+ confidence only and marks ``cross_checked_against_samgov = False`` -- it never
claims a cross-check it did not perform (spec Section 8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Protocol

from .confidence import Scored, apply_crosscheck, score_code, score_rate
from .schema import Flag, WageDetermination


@dataclass
class StructuredWd:
    """Authoritative structured WD as returned by SAM.gov."""

    wd_number: str
    revision: Optional[int]
    # code -> canonical base rate
    rates_by_code: dict[str, Decimal] = field(default_factory=dict)
    hw_rate: Optional[Decimal] = None


class SamGovSource(Protocol):
    def fetch(self, wd_number: str, revision: Optional[int]) -> Optional[StructuredWd]:
        ...


class InMemorySamGov:
    """Test/offline double: a fixed set of structured WDs keyed by number."""

    def __init__(self, records: dict[str, StructuredWd]) -> None:
        self._records = records

    def fetch(self, wd_number: str, revision: Optional[int]) -> Optional[StructuredWd]:
        return self._records.get(wd_number)


@dataclass
class CrosscheckReport:
    performed: bool = False
    divergences: list[str] = field(default_factory=list)  # human-readable


def cross_check(
    wd: WageDetermination, source: Optional[SamGovSource]
) -> CrosscheckReport:
    """Reconcile ``wd`` against SAM.gov in place, updating confidences and
    flags. Returns a report; sets ``extraction_meta.cross_checked_against_samgov``.
    """
    report = CrosscheckReport()
    if source is None or not wd.wd_number:
        wd.extraction_meta.cross_checked_against_samgov = False
        return report

    structured = source.fetch(wd.wd_number, wd.revision)
    if structured is None:
        wd.extraction_meta.cross_checked_against_samgov = False
        return report

    report.performed = True
    wd.extraction_meta.cross_checked_against_samgov = True

    # H&W
    if structured.hw_rate is not None and wd.health_and_welfare.rate_per_hour is not None:
        matches = wd.health_and_welfare.rate_per_hour == structured.hw_rate
        _fold(wd.health_and_welfare._meta, matches)
        if not matches:
            report.divergences.append(
                f"H&W: OCR {wd.health_and_welfare.rate_per_hour} vs "
                f"SAM.gov {structured.hw_rate}"
            )

    # Classifications by resolved code.
    for c in wd.classifications:
        if not c.code:
            continue
        canon = structured.rates_by_code.get(c.code)
        if canon is None:
            continue
        matches = c.base_rate_per_hour == canon
        _fold(c._meta, matches)
        if not matches:
            report.divergences.append(
                f"{c.code} {c.title}: OCR {c.base_rate_per_hour} vs "
                f"SAM.gov {canon}"
            )
    return report


def _fold(meta, matches: bool) -> None:
    meta.cross_checked = True
    folded = apply_crosscheck(Scored(meta.confidence, list(meta.flags)), matches=matches)
    meta.confidence = round(folded.confidence, 4)
    for f in folded.flags:
        meta.add_flag(f)
