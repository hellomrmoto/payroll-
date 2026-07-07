"""Human-in-the-loop confirmation queue (spec Section 7) — the trust surface.

The engine surfaces only the fields that failed threshold, each with: the
extracted value, the source citation (so the UI can show the exact image crop
where it was read), the candidate correction(s), and a governing note. Nothing
enters the contract's active WD as authoritative until this queue is cleared.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .confidence import Disposition, Thresholds, DEFAULT_THRESHOLDS, disposition
from .schema import (
    Citation,
    Classification,
    Flag,
    WageDetermination,
)


@dataclass
class ConfirmationItem:
    field_path: str            # e.g. "classifications[3].code"
    value: Any                 # the extracted value (may be None)
    confidence: float
    disposition: str           # soft_confirm | hard_confirm
    citation: Optional[dict]   # page + span + bbox for the visual crop
    candidates: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    note: str = ""             # governing rule shown to the user


# Governing notes keyed by the dominant flag on a field.
_NOTES: dict[Flag, str] = {
    Flag.CODE_OCR_CORRECTED: (
        "Codes are 5 digits per the SCA Directory of Occupations; this one was "
        "auto-corrected from an OCR reading. Confirm the corrected code."
    ),
    Flag.CODE_UNRECOVERABLE: (
        "This code could not be matched to any entry in the SCA Directory of "
        "Occupations. Select the correct code or re-scan."
    ),
    Flag.RATE_ORPHANED: (
        "This rate was not cleanly adjacent to its code/title (common in "
        "two-column scans). Confirm the code<->rate pairing against the source."
    ),
    Flag.RATE_OUT_OF_BAND: (
        "This rate is outside the usual $10-$100/hr band for service "
        "classifications. Confirm it was read correctly."
    ),
    Flag.RATE_MISSING: (
        "No rate was found for this listed classification. A rate is never "
        "inferred; enter it from the source or confirm it is absent."
    ),
    Flag.DUPLICATE_TITLE: (
        "More than one classification shares this title. Select which code/rate "
        "applies to your worker; they are not merged automatically."
    ),
    Flag.LOCALITY_MISMATCH: (
        "The contract's place-of-performance county is not among this WD's "
        "counties. This may be the wrong WD for the contract."
    ),
    Flag.HW_UNKNOWN: (
        "This H&W rate does not match a published national H&W rate. Confirm it "
        "against the source and the applicable AAM."
    ),
    Flag.CROSSCHECK_DIVERGENCE: (
        "This value disagrees with the authoritative SAM.gov structured WD. "
        "Both values are shown; choose the correct one."
    ),
    Flag.WD_TYPE_INDETERMINATE: (
        "Could not determine odd (per-employee) vs even (average-cost) fringe "
        "type. Fringe compliance math is blocked until this is confirmed."
    ),
}


def build_queue(
    wd: WageDetermination, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> list[ConfirmationItem]:
    """Assemble the confirmation queue and populate
    ``extraction_meta.fields_requiring_confirmation`` + ``overall_confidence``.
    """
    items: list[ConfirmationItem] = []

    def consider(path: str, value: Any, meta) -> None:
        disp = disposition(
            meta.confidence, cross_checked=meta.cross_checked, thresholds=thresholds
        )
        if disp is Disposition.AUTO_CONFIRMED:
            return
        items.append(
            ConfirmationItem(
                field_path=path,
                value=_render(value),
                confidence=meta.confidence,
                disposition=disp.value,
                citation=_cite(meta.citation),
                candidates=list(meta.candidates),
                flags=[f.value for f in meta.flags],
                note=_note_for(meta.flags),
            )
        )

    # wd_type is mandatory to attempt; indeterminate -> confirmation.
    if wd.wd_type is None:
        items.append(
            ConfirmationItem(
                field_path="wd_type",
                value=None,
                confidence=0.0,
                disposition=Disposition.HARD_CONFIRM.value,
                citation=None,
                note=_NOTES[Flag.WD_TYPE_INDETERMINATE],
                flags=[Flag.WD_TYPE_INDETERMINATE.value],
            )
        )

    consider("health_and_welfare.rate_per_hour",
             wd.health_and_welfare.rate_per_hour, wd.health_and_welfare._meta)

    # Locality is surfaced only when it mismatches the contract or failed to
    # parse -- a clean locality that matches needs no confirmation (spec Sec 6).
    if (
        Flag.LOCALITY_MISMATCH in wd.locality._meta.flags
        or wd.locality._meta.confidence < thresholds.soft
    ):
        consider("locality", wd.locality.raw_text, wd.locality._meta)

    for i, c in enumerate(wd.classifications):
        consider(f"classifications[{i}].code", c.code, c._meta)

    # Record which field paths need confirmation and roll up overall confidence.
    wd.extraction_meta.fields_requiring_confirmation = [it.field_path for it in items]
    wd.extraction_meta.overall_confidence = _overall_confidence(wd)
    return items


def _overall_confidence(wd: WageDetermination) -> float:
    scores: list[float] = []
    if wd.health_and_welfare.rate_per_hour is not None:
        scores.append(wd.health_and_welfare._meta.confidence)
    scores.extend(c._meta.confidence for c in wd.classifications)
    if not scores:
        return 0.0
    return round(min(scores), 4)  # weakest-link: the document is only as good
    # as its shakiest safety-critical field.


def _note_for(flags: list[Flag]) -> str:
    for f in flags:  # first flag with a note wins; flags are ordered by severity
        if f in _NOTES:
            return _NOTES[f]
    return "Confidence below threshold; confirm against the source."


def _cite(citation: Optional[Citation]) -> Optional[dict]:
    if citation is None:
        return None
    d: dict[str, Any] = {"page": citation.page, "span": citation.span}
    if citation.bbox is not None:
        d["bbox"] = citation.bbox
    return d


def _render(value: Any) -> Any:
    from decimal import Decimal

    if isinstance(value, Decimal):
        return str(value)
    return value
