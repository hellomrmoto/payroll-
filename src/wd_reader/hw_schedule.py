"""Known national Health & Welfare rate schedule (spec Section 5).

A value matching a published rate is a strong confidence signal; a value
matching nothing is flagged. These are the standard (non-Hawaii) SCA H&W rates
by effective date. Update as DOL publishes new AAM rates.
"""

from __future__ import annotations

from decimal import Decimal

# effective date (YYYY-MM-DD) -> rate per hour, most recent last.
NATIONAL_HW_RATES: dict[str, Decimal] = {
    "2023-06-27": Decimal("4.98"),
    "2024-06-27": Decimal("5.36"),
    "2025-07-07": Decimal("5.55"),
}

# EO 13706 (paid sick leave) reduced H&W rates that pair with the above.
EO13706_HW_RATES: dict[str, Decimal] = {
    "2023-06-27": Decimal("4.57"),
    "2024-06-27": Decimal("4.93"),
    "2025-07-07": Decimal("5.09"),
}


def is_known_hw_rate(rate: Decimal) -> bool:
    return rate in set(NATIONAL_HW_RATES.values()) | set(EO13706_HW_RATES.values())
