"""National Health & Welfare fringe schedule for cross-checking H&W rates.

The prevailing SCA H&W rate is set nationally and updated periodically. Reading
an H&W value off a document that matches the known national rate for its
effective date is a strong signal; a mismatch is worth surfacing (the rate may
be a locality low-level or a stale/misread figure).

Values are exact decimals. Extend ``SCHEDULE`` as DOL publishes new rates.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

# (effective_from, rate_per_hour). Ordered oldest -> newest.
SCHEDULE: list[tuple[date, Decimal]] = [
    (date(2024, 6, 27), Decimal("4.98")),
    (date(2024, 7, 16), Decimal("5.36")),
    (date(2025, 7, 7), Decimal("5.55")),
]


def national_rate_on(effective: date) -> Optional[Decimal]:
    """Return the national H&W rate in force on ``effective``, or None if the
    date precedes the earliest entry we know about."""
    rate: Optional[Decimal] = None
    for start, value in SCHEDULE:
        if effective >= start:
            rate = value
        else:
            break
    return rate


def matches_any_known(rate: Decimal) -> bool:
    """True if ``rate`` equals any published national H&W value (date-agnostic).

    Used when the document's effective date is itself uncertain — matching *a*
    known national rate is still corroborating.
    """
    return any(rate == value for _, value in SCHEDULE)
