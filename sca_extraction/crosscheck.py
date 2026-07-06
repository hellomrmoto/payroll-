"""Cross-check extracted values against the SAM.gov structured wage
determination for the same number/revision.

Design constraint from the skill: *never claim cross-checked when the SAM.gov
source was unavailable.* So the provider returns a tri-state — a structured WD,
or ``None`` for "unavailable" — and the reconciler only marks fields
``cross_checked`` when a real structured record came back.

No network client is bundled (the environment may be offline); the default
provider reports "unavailable". Inject a real provider to enable cross-checking.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable, Optional, Protocol

from . import confidence as conf
from .confidence import Adjust
from .schema import CrossCheckReport, ExtractionResult, FieldMeta


class SamWageDetermination(Protocol):
    """Minimal shape of a structured SAM.gov WD record used for reconciliation."""

    wd_number: str
    revision: str
    hw_fringe_rate: Optional[Decimal]
    rates_by_code: dict[str, Decimal]  # code -> rate for occupational listings


# A provider takes (wd_number, revision) and returns a structured record, or
# None if the source could not be reached / had no matching record.
SamProvider = Callable[[Optional[str], Optional[str]], Optional["SamWageDetermination"]]


def unavailable_provider(wd_number: Optional[str], revision: Optional[str]):
    """Default provider: SAM.gov not wired up in this environment."""
    return None


def _boost(meta: FieldMeta, source: str) -> None:
    meta.cross_checked = True
    meta.confidence = conf.combine(meta.confidence, Adjust.CROSS_CHECK_MATCH)
    meta.flags.add("cross_check_match")
    meta.notes.append(f"cross-checked and matched against {source}")


def _diverge(meta: FieldMeta, source: str, local_value, other_value) -> None:
    # Surface *both* values; never silently overwrite the local reading.
    meta.confidence = conf.combine(meta.confidence, Adjust.CROSS_CHECK_DIVERGE)
    meta.flags.add("cross_check_divergence")
    meta.notes.append(
        f"cross-check divergence vs {source}: local={local_value} other={other_value}"
    )


def reconcile(
    result: ExtractionResult,
    provider: SamProvider = unavailable_provider,
) -> ExtractionResult:
    """Cross-check ``result`` against SAM.gov via ``provider`` and update meta.

    Mutates and returns ``result``. Only sets ``cross_checked`` on fields when a
    structured record was actually returned. Divergences surface *both* values
    and are recorded in the :class:`CrossCheckReport`. The confirmation queue is
    rebuilt afterwards because cross-checking can move fields across thresholds.
    """
    wd = result.wage_determination
    report = CrossCheckReport(performed=True, available=False)

    record = provider(wd.wd_number.value, wd.revision.value)
    if record is None:
        # Source unavailable — honestly report that nothing was cross-checked.
        result.cross_check = report
        return result

    report.available = True
    source = report.source

    # H&W fringe.
    local_hw = wd.hw_fringe_rate.value
    sam_hw = getattr(record, "hw_fringe_rate", None)
    if local_hw is not None and sam_hw is not None:
        if local_hw == sam_hw:
            _boost(wd.hw_fringe_rate.meta, source)
            report.matched_fields.append("hw_fringe_rate")
        else:
            _diverge(wd.hw_fringe_rate.meta, source, local_hw, sam_hw)
            report.diverged_fields.append("hw_fringe_rate")

    # Occupational rates keyed by (corrected) code.
    rates_by_code = getattr(record, "rates_by_code", {}) or {}
    for idx, occ in enumerate(wd.occupations):
        code = occ.code.value
        local_rate = occ.rate.value
        if code is None or local_rate is None:
            continue
        sam_rate = rates_by_code.get(code)
        if sam_rate is None:
            continue
        field_path = f"occupations[{idx}].rate"
        if local_rate == sam_rate:
            _boost(occ.rate.meta, source)
            report.matched_fields.append(field_path)
        else:
            _diverge(occ.rate.meta, source, local_rate, sam_rate)
            report.diverged_fields.append(field_path)

    result.cross_check = report

    # Thresholds may have shifted for cross-checked fields — rebuild the queue.
    from .extractor import build_confirmation_queue

    result.confirmation_queue = build_confirmation_queue(wd)
    return result
