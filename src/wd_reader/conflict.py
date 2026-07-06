"""Conflict resolution — defined behavior, not guesswork (spec Section 6).

These operate on the assembled :class:`~wd_reader.schema.WageDetermination`
plus the user-supplied contract metadata, attaching flags and never silently
merging, inferring, or proceeding on an assumption.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .schema import Flag, WageDetermination, WdType


@dataclass
class ContractMetadata:
    """Provided by the user on upload (spec Section 2)."""

    contract_number: Optional[str] = None
    pop_state: Optional[str] = None       # place-of-performance state, e.g. "CA"
    pop_county: Optional[str] = None      # e.g. "Tulare"


def resolve(wd: WageDetermination, contract: Optional[ContractMetadata]) -> None:
    """Apply all conflict rules in place."""
    _flag_duplicate_titles(wd)
    _flag_missing_rates(wd)
    _flag_locality_mismatch(wd, contract)
    _flag_indeterminate_wd_type(wd)


def _flag_duplicate_titles(wd: WageDetermination) -> None:
    """Two classifications with the same title: keep both, flag both, surface
    both. Never silently merge (spec Section 6)."""
    seen: dict[str, list[int]] = {}
    for i, c in enumerate(wd.classifications):
        if c.title:
            seen.setdefault(c.title.strip().lower(), []).append(i)
    for _, idxs in seen.items():
        if len(idxs) > 1:
            for i in idxs:
                wd.classifications[i]._meta.add_flag(Flag.DUPLICATE_TITLE)


def _flag_missing_rates(wd: WageDetermination) -> None:
    """A listed classification with no rate is emitted with a null rate and a
    hard-confirmation flag; a rate is never inferred (spec Section 6)."""
    for c in wd.classifications:
        if c.base_rate_per_hour is None:
            c._meta.add_flag(Flag.RATE_MISSING)


def _flag_locality_mismatch(
    wd: WageDetermination, contract: Optional[ContractMetadata]
) -> None:
    """Contract place-of-performance county not among the WD's counties -> hard
    flag: possibly the wrong WD is attached to the contract (spec Section 6)."""
    if not contract or not contract.pop_county:
        return
    wd_counties = {c.strip().lower() for c in wd.locality.counties}
    if not wd_counties:
        return
    if contract.pop_county.strip().lower() not in wd_counties:
        wd.locality._meta.add_flag(Flag.LOCALITY_MISMATCH)
    if (
        contract.pop_state
        and wd.locality.state
        and contract.pop_state.strip().upper() != wd.locality.state.strip().upper()
    ):
        wd.locality._meta.add_flag(Flag.LOCALITY_MISMATCH)


def _flag_indeterminate_wd_type(wd: WageDetermination) -> None:
    """Odd/even indeterminate -> null + confirmation; downstream fringe math is
    blocked until resolved rather than run on an assumption (spec Section 6)."""
    if wd.wd_type is None:
        wd.health_and_welfare._meta.add_flag(Flag.WD_TYPE_INDETERMINATE)
    elif wd.wd_type not in (WdType.ODD, WdType.EVEN):  # defensive
        wd.wd_type = None
        wd.health_and_welfare._meta.add_flag(Flag.WD_TYPE_INDETERMINATE)
