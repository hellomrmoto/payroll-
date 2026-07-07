"""Validation + confidence scoring (spec Section 5).

Confidence for each field is built from stacked signals, then bucketed against
tunable thresholds into auto-confirm / soft-confirm / hard-confirm. The scoring
is deterministic and side-effect free: it reads a field's current state and
returns a score plus any flags to attach.

The cardinal rule the whole product rests on: a value only reaches downstream
as *confirmed* if it is (a) >= AUTO threshold AND cross-checked, or (b)
human-confirmed. Everything else is queued. That policy lives in
:func:`disposition`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

from . import hw_schedule
from .ocr_correction import CorrectionResult
from .schema import Flag


# --------------------------------------------------------------------------- #
# Tunable thresholds (spec Section 5). Configuration, not constants of nature.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Thresholds:
    auto: float = 0.95          # >= auto AND cross-checked -> auto-confirmed
    soft: float = 0.80          # [soft, auto) -> one-click accept
    # < soft -> hard confirmation required


DEFAULT_THRESHOLDS = Thresholds()

# Plausible band for standard service-classification base rates ($/hr).
RATE_BAND_MIN = Decimal("10.00")
RATE_BAND_MAX = Decimal("100.00")


class Disposition(str, Enum):
    AUTO_CONFIRMED = "auto_confirmed"
    SOFT_CONFIRM = "soft_confirm"
    HARD_CONFIRM = "hard_confirm"


@dataclass
class Scored:
    confidence: float
    flags: list[Flag]


def score_code(correction: CorrectionResult) -> Scored:
    """Confidence for an occupation code from its correction result."""
    flags: list[Flag] = []
    if not correction.recoverable:
        # No real Directory code matched -> unrecoverable, hard confirm.
        return Scored(0.10, [Flag.CODE_UNRECOVERABLE])

    best = correction.best
    assert best is not None
    if not correction.was_corrupted and best.edit_distance == 0:
        # Clean, valid, uncorrupted code read verbatim.
        return Scored(0.99, [])

    # Corrupted but recovered. Confidence reflects how decisive the recovery
    # was: small edit distance + strong title agreement -> high; ambiguity
    # (multiple close candidates) -> lower.
    flags.append(Flag.CODE_OCR_CORRECTED)
    base = best.score  # already in (0, 1]
    margin = 1.0
    if len(correction.candidates) > 1:
        second = correction.candidates[1].score
        margin = _safe_ratio(base - second, base)
    conf = 0.55 + 0.4 * base * (0.5 + 0.5 * margin)
    return Scored(round(min(conf, 0.94), 4), flags)


def score_rate(
    rate: Optional[Decimal],
    *,
    orphaned: bool,
    code_confidence: float,
) -> Scored:
    """Confidence for a base rate. Orphaned or out-of-band rates are capped low
    regardless of how clean the digits looked -- this is the two-column
    separation defense (spec Section 5)."""
    flags: list[Flag] = []
    if rate is None:
        return Scored(0.0, [Flag.RATE_MISSING])

    in_band = RATE_BAND_MIN <= rate <= RATE_BAND_MAX
    if not in_band:
        flags.append(Flag.RATE_OUT_OF_BAND)
    if orphaned:
        flags.append(Flag.RATE_ORPHANED)

    if orphaned:
        # Extracted without a cleanly adjacent code/title -> cannot trust the
        # pairing. Hard-confirm territory no matter what.
        return Scored(0.45 if in_band else 0.25, flags)
    if not in_band:
        return Scored(0.50, flags)

    # A well-paired, in-band rate inherits confidence from its code: a rate is
    # only as trustworthy as the classification it is bound to.
    conf = 0.85 + 0.13 * min(code_confidence, 1.0)
    return Scored(round(min(conf, 0.98), 4), flags)


def score_hw_rate(rate: Optional[Decimal]) -> Scored:
    if rate is None:
        return Scored(0.0, [Flag.RATE_MISSING])
    if hw_schedule.is_known_hw_rate(rate):
        return Scored(0.97, [])  # matches a published national rate
    return Scored(0.55, [Flag.HW_UNKNOWN])


def apply_crosscheck(scored: Scored, *, matches: Optional[bool]) -> Scored:
    """Fold a SAM.gov cross-check outcome into a score (spec Section 5).

    matches is True (agrees), False (diverges), or None (not available).
    """
    if matches is True:
        return Scored(max(scored.confidence, 0.97), list(scored.flags))
    if matches is False:
        flags = list(scored.flags)
        if Flag.CROSSCHECK_DIVERGENCE not in flags:
            flags.append(Flag.CROSSCHECK_DIVERGENCE)
        # Divergence never auto-confirms; both values must be surfaced.
        return Scored(min(scored.confidence, 0.60), flags)
    return scored


def disposition(
    confidence: float,
    *,
    cross_checked: bool,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> Disposition:
    """The cardinal gate. Auto-confirm requires BOTH high confidence AND a
    cross-check; without a cross-check the bar is raised (spec Sections 3, 5, 8).
    """
    if confidence >= thresholds.auto and cross_checked:
        return Disposition.AUTO_CONFIRMED
    if confidence >= thresholds.soft:
        return Disposition.SOFT_CONFIRM
    return Disposition.HARD_CONFIRM


def _safe_ratio(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return max(0.0, min(1.0, num / den))
