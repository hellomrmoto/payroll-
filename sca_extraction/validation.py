"""Validation + confidence scoring rules applied to extracted fields.

Each ``score_*`` takes a *raw* parsed value plus context (OCR? code repaired
cleanly?) and returns a scored :class:`~sca_extraction.schema.TracedValue`. The
confirmation queue is derived *separately* from the resulting field metadata
(see :func:`sca_extraction.extractor.build_confirmation_queue`), so these
functions never build queue items themselves — they just score and annotate.

Rules encoded (from the skill):
  * codes: 5 digits, must exist in the directory after correction else confirm;
  * rates: positive decimal in the $10-$100 plausibility band, exact decimal;
  * orphaned rate (no clean adjacent code/title) -> low confidence;
  * H&W: cross-check against the national schedule; match boosts;
  * WD parity: attempt; indeterminate -> None (never guessed).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from . import confidence as conf
from .confidence import Adjust
from .hw_schedule import matches_any_known
from .occupations import Directory, default_directory
from .ocr_corrections import CodeRepair, repair_code
from .schema import Citation, FieldMeta, TracedValue, WDParity

RATE_BAND_LOW = Decimal("10")
RATE_BAND_HIGH = Decimal("100")

_RATE_RE = re.compile(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,4})?|[0-9]+\.[0-9]{1,4})")


def parse_rate(raw: Optional[str]) -> Optional[Decimal]:
    """Extract an exact Decimal from a rate string, or None if unparseable.

    Never returns a float — round-trips through ``Decimal(str)`` so ``18.42``
    stays ``18.42`` exactly.
    """
    if raw is None:
        return None
    m = _RATE_RE.search(raw)
    if not m:
        return None
    token = m.group(1).replace(",", "")
    try:
        return Decimal(token)
    except InvalidOperation:
        return None


def score_code(
    raw_code: str,
    citation: Citation,
    is_ocr: bool,
    directory: Optional[Directory] = None,
) -> tuple[TracedValue, CodeRepair]:
    """Validate/repair an occupation code and score it."""
    directory = directory or default_directory()
    repair = repair_code(raw_code, directory)
    base = conf.base_for_ocr(is_ocr)
    flags: set[str] = set()
    notes: list[str] = []
    adjustments: list[Decimal] = []

    if repair.is_clean_valid:
        value = repair.corrected
    elif repair.resolved:  # corrected uniquely against directory
        value = repair.corrected
        flags.add("code_corrected")
        notes.append(f"corrected '{repair.raw}' -> '{repair.corrected}' via directory")
        adjustments.append(Adjust.CODE_CORRECTED)
    elif repair.ambiguous:
        value = None
        flags.add("code_ambiguous")
        notes.append(
            f"'{repair.raw}' maps to multiple directory codes: {repair.candidates}"
        )
        adjustments.append(Adjust.CODE_AMBIGUOUS)
    else:
        # 5 clean digits but unknown, or unrepairable corruption.
        digits5 = repair.normalized.isdigit() and len(repair.normalized) == 5
        value = repair.normalized if digits5 else None
        flags.add("code_not_in_directory")
        notes.append(f"'{repair.raw}' ({repair.reason}) not found in directory")
        adjustments.append(Adjust.CODE_NOT_IN_DIRECTORY)

    if is_ocr:
        adjustments.append(Adjust.OCR_SOURCE)

    score = conf.combine(base, *adjustments)
    meta = FieldMeta(
        confidence=score,
        citation=citation,
        flags=flags,
        notes=notes,
        candidates=list(repair.candidates),
    )
    return TracedValue(value=value, meta=meta), repair


def score_rate(
    raw_rate: Optional[str],
    citation: Citation,
    is_ocr: bool,
    orphaned: bool = False,
) -> TracedValue:
    """Validate/score a wage rate. ``orphaned`` = no clean adjacent code/title."""
    base = conf.base_for_ocr(is_ocr)
    flags: set[str] = set()
    notes: list[str] = []
    adjustments: list[Decimal] = []

    value = parse_rate(raw_rate)

    if value is None:
        flags.add("rate_unparseable")
        notes.append(f"could not parse a rate from {raw_rate!r}")
        adjustments.append(Adjust.RATE_UNPARSEABLE)
    elif value <= 0:
        flags.add("rate_non_positive")
        notes.append(f"rate {value} is not positive")
        adjustments.append(Adjust.RATE_UNPARSEABLE)
        value = None
    elif not (RATE_BAND_LOW <= value <= RATE_BAND_HIGH):
        flags.add("rate_out_of_band")
        notes.append(
            f"rate {value} outside plausible ${RATE_BAND_LOW}-${RATE_BAND_HIGH}/hr band"
        )
        adjustments.append(Adjust.RATE_OUT_OF_BAND)

    if orphaned:
        flags.add("rate_orphaned")
        notes.append("rate reunited from an orphaned line (two-column split); verify pairing")
        adjustments.append(Adjust.RATE_ORPHANED)

    if is_ocr:
        adjustments.append(Adjust.OCR_SOURCE)

    score = conf.combine(base, *adjustments)
    meta = FieldMeta(confidence=score, citation=citation, flags=flags, notes=notes)
    return TracedValue(value=value, meta=meta)


def score_hw(
    raw_rate: Optional[str],
    citation: Citation,
    is_ocr: bool,
) -> TracedValue:
    """Validate/score the H&W fringe rate, cross-checking the national schedule.

    A match against a published national H&W value boosts confidence and sets
    ``cross_checked`` (a legitimate structured cross-check that does not depend
    on SAM.gov availability). A mismatch penalises but never rewrites the value.
    """
    base = conf.base_for_ocr(is_ocr)
    flags: set[str] = set()
    notes: list[str] = []
    adjustments: list[Decimal] = []
    cross_checked = False

    value = parse_rate(raw_rate)

    if value is None or value <= 0:
        flags.add("hw_unparseable")
        notes.append(f"could not parse H&W rate from {raw_rate!r}")
        adjustments.append(Adjust.RATE_UNPARSEABLE)
        value = None
    elif matches_any_known(value):
        flags.add("hw_matches_national")
        notes.append(f"H&W {value} matches a published national schedule value")
        adjustments.append(Adjust.HW_MATCH)
        cross_checked = True
    else:
        flags.add("hw_mismatch")
        notes.append(f"H&W {value} does not match any known national schedule value")
        adjustments.append(Adjust.HW_MISMATCH)

    if is_ocr:
        adjustments.append(Adjust.OCR_SOURCE)

    score = conf.combine(base, *adjustments)
    meta = FieldMeta(
        confidence=score,
        citation=citation,
        cross_checked=cross_checked,
        flags=flags,
        notes=notes,
    )
    return TracedValue(value=value, meta=meta)


def parse_parity(wd_number: Optional[str]) -> Optional[WDParity]:
    """Derive odd/even parity from a WD number's trailing numeric segment.

    SCA WD numbers look like ``2015-4281``; parity is the last digit's parity.
    Indeterminate input returns ``None`` — the caller must not guess.
    """
    if not wd_number:
        return None
    digits = re.findall(r"\d", wd_number)
    if not digits:
        return None
    last = int(digits[-1])
    return WDParity.ODD if last % 2 == 1 else WDParity.EVEN


def score_parity(
    wd_number_value: Optional[str],
    citation: Citation,
    wd_number_confidence: Decimal,
) -> TracedValue:
    """Score WD parity. Parity can be no more certain than the WD number it is
    derived from, so its confidence is capped by the WD number's confidence."""
    parity = parse_parity(wd_number_value)
    flags: set[str] = set()
    notes: list[str] = []

    if parity is None:
        flags.add("parity_indeterminate")
        notes.append("WD number missing/unreadable; parity left null (not guessed)")
        score = Decimal("0.00")
    else:
        score = conf.clamp(wd_number_confidence)
        notes.append(f"parity {parity.value} derived from WD number last digit")

    meta = FieldMeta(confidence=score, citation=citation, flags=flags, notes=notes)
    return TracedValue(value=parity, meta=meta)
