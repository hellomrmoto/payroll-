"""Test fixtures: representative wage-determination text, including the exact
OCR corruptions observed on the reference document WD 2015-5657 (spec Sec. 1).
"""

# Image-only OCR of WD 2015-5657 with the real observed corruptions.
# @1311 (0->@), 61313 (0->6, III->IIT), e9eee (family header 09000 fully
# corrupted), 11150 (clean). Rates read cleanly here; codes did not.
WD_2015_5657_OCR = """\
WAGE DETERMINATION NO. 2015-5657 Revision No. 24
Date Of Last Revision: 07/07/2025
State: California Counties of Tulare

Fringe benefits are paid per employee on all hours.

OCCUPATION CODE - TITLE                          RATE
01000 - Administrative Support And Clerical Occupations
@1311 - Secretary I 19.73
01312 - Secretary II 22.05
61313 - Secretary IIT 24.60
e9eee - Furniture Maintenance And Repair Occupations
11000 - General Services And Support Occupations
11150 - Janitor 17.56

ALL OCCUPATIONS LISTED ABOVE RECEIVE THE FOLLOWING BENEFITS:
HEALTH & WELFARE: $5.55 per hour or $222.08 per week or $962.08 per month
Vacation: 2 weeks paid vacation after 1 year of service.
11 paid holidays: New Year's Day, Martin Luther King Jr's Birthday.
"""

# A clean text-layer WD (no corruption) for the auto-confirm path.
WD_TEXTLAYER_CLEAN = """\
WAGE DETERMINATION NO. 2015-4567 Revision No. 12
Date Of Last Revision: 07/07/2025
State: Nevada Counties of Clark

Health & Welfare fringe benefits are paid per employee.

11150 - Janitor 18.42
07041 - Cook I 16.90
27101 - Guard I 20.15
HEALTH & WELFARE: $5.55 per hour
Vacation: 2 weeks after 1 year.
10 paid holidays: New Year's Day.
"""

# Two-column separation: a code+title whose rate landed in a different block,
# so the classification line carries no rate (orphaned).
WD_ORPHANED_RATE_OCR = """\
WAGE DETERMINATION NO. 2015-9999 Revision No. 1
State: California Counties of Tulare
Average cost of fringe benefits across all hours worked.
11150 - Janitor
07041 - Cook I 16.90
HEALTH & WELFARE: $5.55 per hour
"""

# An out-of-band rate (implausibly high) that must be flagged, not trusted.
WD_OUT_OF_BAND_OCR = """\
WAGE DETERMINATION NO. 2015-8888 Revision No. 1
State: Texas Counties of Travis
Fringe benefits paid per employee.
11150 - Janitor 175.60
HEALTH & WELFARE: $5.55 per hour
"""
