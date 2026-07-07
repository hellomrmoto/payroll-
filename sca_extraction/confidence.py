"""Confidence scoring and threshold classification.

Confidence is an exact :class:`~decimal.Decimal` in ``[0, 1]``.  We keep it a
decimal (not a float) so scores are reproducible and comparisons against the
threshold constants are exact — a rate that lands *precisely* on 0.95 must
resolve the same way on every machine.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .schema import (
    AUTO_CONFIRM_THRESHOLD,
    SOFT_CONFIRM_THRESHOLD,
    ConfidenceLevel,
)

ZERO = Decimal("0")
ONE = Decimal("1")


def clamp(score: Decimal) -> Decimal:
    """Clamp a raw score into ``[0, 1]`` and quantise to 2 d.p."""
    if score < ZERO:
        score = ZERO
    elif score > ONE:
        score = ONE
    return score.quantize(Decimal("0.01"))


def combine(base: Decimal, *adjustments: Decimal) -> Decimal:
    """Apply additive penalties/boosts to a base score, then clamp.

    Additive (not multiplicative) so a single hard failure — e.g. an orphaned
    rate at ``-0.40`` — can by itself drop a field below the hard-confirm line,
    which is the behaviour the skill wants.
    """
    total = base
    for adj in adjustments:
        total += adj
    return clamp(total)


def classify(
    confidence: Decimal,
    cross_checked: bool,
    human_confirmed: bool = False,
) -> ConfidenceLevel:
    """Map a (confidence, cross_checked) pair to a :class:`ConfidenceLevel`.

    Note the asymmetry required by the skill: a score can be >=0.95 yet still
    *not* auto-confirm, because auto-confirm additionally requires the value to
    have been cross-checked against an external structured source.  A human
    confirmation short-circuits to auto-confirm regardless of score.
    """
    if human_confirmed:
        return ConfidenceLevel.AUTO_CONFIRM
    if confidence >= AUTO_CONFIRM_THRESHOLD and cross_checked:
        return ConfidenceLevel.AUTO_CONFIRM
    if confidence >= SOFT_CONFIRM_THRESHOLD:
        return ConfidenceLevel.SOFT_CONFIRM
    return ConfidenceLevel.HARD_CONFIRM


# --- Named adjustment magnitudes -------------------------------------------
# Centralised so scoring is consistent and tunable in one place.

class Adjust:
    CODE_CORRECTED = Decimal("-0.20")          # OCR-corrupt code repaired via directory
    CODE_AMBIGUOUS = Decimal("-0.45")          # multiple directory candidates
    CODE_NOT_IN_DIRECTORY = Decimal("-0.35")   # 5 clean digits, unknown code
    RATE_ORPHANED = Decimal("-0.40")           # rate with no clean adjacent code/title
    RATE_OUT_OF_BAND = Decimal("-0.30")        # outside $10-$100 plausibility band
    RATE_UNPARSEABLE = Decimal("-0.60")
    HW_MATCH = Decimal("+0.10")                # matches national H&W schedule
    HW_MISMATCH = Decimal("-0.25")
    CROSS_CHECK_MATCH = Decimal("+0.08")
    CROSS_CHECK_DIVERGE = Decimal("-0.30")
    OCR_SOURCE = Decimal("-0.10")              # value came from OCR, not a text layer
    CLEAN_TEXT_LAYER = Decimal("+0.05")


def base_for_ocr(is_ocr: bool) -> Decimal:
    """Starting confidence before field-specific adjustments."""
    return Decimal("0.90") if is_ocr else Decimal("0.98")


def min_confidence(scores: Iterable[Decimal]) -> Decimal:
    """Lowest score in an iterable, or 1 if empty (used to roll a row up)."""
    scores = list(scores)
    return min(scores) if scores else ONE
