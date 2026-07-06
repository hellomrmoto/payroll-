"""SCA Directory of Occupations — the authority for occupation-code validation
and OCR correction (spec Section 5).

SCA occupation codes are exactly 5 digits. The leading two digits identify the
occupational family. This module ships a representative subset of the real
Directory: enough real codes (including every code referenced in the spec's
corruption table) to make correction demonstrable, plus every family header so
family lookup always resolves.

In production this table is loaded from the full published Directory of
Occupations; the shape and API here are what the rest of the engine binds to,
so swapping in the complete list is a data change, not a code change.
"""

from __future__ import annotations

from typing import Optional

# Family header code (leading two digits + "000") -> family name.
FAMILIES: dict[str, str] = {
    "01000": "Administrative Support And Clerical Occupations",
    "03000": "Automatic Data Processing Occupations",
    "05000": "Automotive Service Occupations",
    "07000": "Food Preparation And Service Occupations",
    "09000": "Furniture Maintenance And Repair Occupations",
    "11000": "General Services And Support Occupations",
    "13000": "Health Occupations",
    "15000": "Information And Arts Occupations",
    "19000": "Laundry, Dry-Cleaning, Pressing And Related Occupations",
    "21000": "Materials Handling And Packing Occupations",
    "23000": "Mechanics And Maintenance And Repair Occupations",
    "25000": "Personal Needs Occupations",
    "27000": "Protective Service Occupations",
    "29000": "Stevedoring/Longshoremen Occupational Services",
    "31000": "Technical Occupations",
    "99000": "Miscellaneous Occupations",
}

# code -> canonical title. Representative subset of individual occupations.
_OCCUPATIONS: dict[str, str] = {
    # Administrative Support And Clerical
    "01011": "Accounting Clerk I",
    "01012": "Accounting Clerk II",
    "01013": "Accounting Clerk III",
    "01111": "General Clerk I",
    "01112": "General Clerk II",
    "01113": "General Clerk III",
    "01311": "Secretary I",
    "01312": "Secretary II",
    "01313": "Secretary III",
    "01611": "Word Processor I",
    "01612": "Word Processor II",
    # Automotive Service
    "05005": "Automobile Body Repairer, Fiberglass",
    "05070": "Electrician, Automotive",
    "05110": "Mechanic, Automobile",
    # Food Preparation And Service
    "07010": "Baker",
    "07041": "Cook I",
    "07042": "Cook II",
    "07070": "Dishwasher",
    "07130": "Food Service Worker",
    # Furniture Maintenance And Repair
    "09010": "Electrostatic Spray Painter",
    "09040": "Furniture Handler",
    "09080": "Furniture Refinisher",
    "09090": "Furniture Refinisher Helper",
    # General Services And Support
    "11030": "Cleaner, Vehicles",
    "11060": "Elevator Operator",
    "11090": "Gardener",
    "11122": "Housekeeping Aide",
    "11150": "Janitor",
    "11210": "Laborer, Grounds Maintenance",
    "11240": "Maid or Houseman",
    "11260": "Pruner",
    "11270": "Tractor Operator",
    "11330": "Trail Maintenance Worker",
    "11360": "Window Cleaner",
    # Health
    "13011": "Ambulance Driver",
    "13047": "Licensed Practical Nurse I",
    "13072": "Medical Laboratory Technician",
    "13120": "Nursing Assistant II",
    # Protective Service
    "27101": "Guard I",
    "27102": "Guard II",
    # Technical
    "31361": "Truck Driver, Light",
    "31362": "Truck Driver, Medium",
    "31363": "Truck Driver, Heavy",
}

# Full lookup includes the family headers as valid codes too.
_ALL: dict[str, str] = {**FAMILIES, **_OCCUPATIONS}


def is_valid_code(code: str) -> bool:
    """True if ``code`` is exactly 5 digits and present in the Directory."""
    return is_well_formed(code) and code in _ALL


def is_well_formed(code: str) -> bool:
    """True if ``code`` is syntactically a code: exactly 5 ASCII digits."""
    return len(code) == 5 and code.isdigit()


def title_for(code: str) -> Optional[str]:
    return _ALL.get(code)


def family_for(code: str) -> Optional[str]:
    """Family name for a code, resolved from its leading two digits."""
    if not is_well_formed(code):
        return None
    return FAMILIES.get(code[:2] + "000")


def all_codes() -> frozenset[str]:
    return frozenset(_ALL)
