"""Structural parse + field extraction (spec Section 3, steps 4-5).

Takes a normalized :class:`~wd_reader.sources.Document` and locates the header
block, the occupational listing, and the fringe/vacation/holiday blocks, then
lifts each field into the schema tagging its source citation and running the
correction/confidence machinery.

Every classification line is parsed into (code, title, rate). A line that
carries a code+title but no cleanly adjacent rate produces an *orphaned* rate
-- the two-column separation failure -- which is flagged and never paired by
proximity guess (spec Sections 5, 6, 8).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from . import ocr_correction, sca_directory
from .confidence import score_code, score_rate
from .schema import (
    Citation,
    Classification,
    Flag,
    HealthAndWelfare,
    Holidays,
    Locality,
    TextBlock,
    WdType,
)
from .sources import Document, SourceLine

# A classification line starts with a 5-ish-glyph code token, then a title,
# optionally ending in a decimal rate. The code token allows homoglyphs
# (@, letters) so corrupted codes are still recognized as codes.
_CODE_TOKEN = r"[0-9@eoOQDCliI|!zZEAhsSbGTt?Bgq]{5}"
_RATE = r"\d{1,3}\.\d{2}"

_CLASS_LINE = re.compile(
    rf"^\s*(?P<code>{_CODE_TOKEN})\s*[-–]\s*(?P<title>.+?)(?:\s+(?P<rate>{_RATE}))?\s*$"
)

_WD_NUMBER = re.compile(r"\b(?:WD\s*)?((?:19|20)\d{2}-\d{3,5})\b", re.I)
_REVISION = re.compile(r"Revision\s*(?:No\.?|Number)?\s*[:#]?\s*(\d+)", re.I)
_REV_DATE = re.compile(
    r"(?:Date\s+Of\s+(?:Last\s+)?Revision|Revision\s+Date)\s*[:\-]?\s*"
    r"(\d{2})/(\d{2})/(\d{4})",
    re.I,
)
_HW_RATE = re.compile(
    r"Health\s*&?\s*Welfare.*?\$?\s*(\d{1,2}\.\d{2})", re.I | re.S
)
_HOLIDAY_COUNT = re.compile(r"(\d{1,2})\s+paid\s+holidays", re.I)


def parse_document(doc: Document) -> "ParsedFields":
    parsed = ParsedFields()
    full_text = "\n".join(ln.text for ln in doc.lines)

    parsed.wd_number = _first_group(_WD_NUMBER, full_text)
    rev = _first_group(_REVISION, full_text)
    parsed.revision = int(rev) if rev and rev.isdigit() else None
    parsed.revision_date = _parse_rev_date(full_text)
    parsed.wd_type = _detect_wd_type(full_text)
    parsed.locality = _parse_locality(doc)
    parsed.health_and_welfare = _parse_hw(doc, full_text)
    parsed.holidays = _parse_holidays(doc, full_text)
    parsed.vacation = _parse_vacation(doc)
    parsed.classifications = _parse_classifications(doc)
    return parsed


class ParsedFields:
    def __init__(self) -> None:
        self.wd_number: Optional[str] = None
        self.revision: Optional[int] = None
        self.revision_date: Optional[str] = None
        self.wd_type: Optional[WdType] = None
        self.locality: Locality = Locality()
        self.health_and_welfare: HealthAndWelfare = HealthAndWelfare()
        self.holidays: Holidays = Holidays()
        self.vacation: TextBlock = TextBlock()
        self.classifications: list[Classification] = []


# --------------------------------------------------------------------------- #
# Classification listing
# --------------------------------------------------------------------------- #
def _parse_classifications(doc: Document) -> list[Classification]:
    out: list[Classification] = []
    for ln in doc.lines:
        m = _CLASS_LINE.match(ln.text)
        if not m:
            continue
        raw_code = m.group("code")
        title = m.group("title").strip()
        rate_str = m.group("rate")

        # Reject obvious non-classification lines: a "code" that is 5 letters
        # forming a real word-ish title header, with no digit/homoglyph signal.
        if not _looks_like_code(raw_code):
            continue

        # Skip occupation-family header lines (e.g. "09000 - Furniture
        # Maintenance And Repair Occupations"). They carry no rate and are
        # section context; the family is derived onto each classification from
        # its code prefix. Only skip when the code resolves to a family header
        # AND the title actually matches that family name, so a real occupation
        # misread into a family code is not silently dropped.
        if _is_family_header(raw_code, title):
            continue

        cls = _build_classification(ln, raw_code, title, rate_str)
        out.append(cls)
    return out


def _is_family_header(raw_code: str, title: str) -> bool:
    correction = ocr_correction.correct_code(raw_code, ocr_title=title)
    code = correction.best.code if correction.best else None
    if code not in sca_directory.FAMILIES:
        return False
    fam_name = sca_directory.FAMILIES[code]
    return _similarity(title, fam_name) >= 0.6


def _build_classification(
    ln: SourceLine, raw_code: str, title: str, rate_str: Optional[str]
) -> Classification:
    correction = ocr_correction.correct_code(raw_code, ocr_title=title)
    code_scored = score_code(correction)

    best = correction.best
    resolved_code = best.code if best else None
    citation = Citation(page=ln.page, span=ln.span(), bbox=ln.bbox)

    cls = Classification(
        code=resolved_code,
        title=title,
        occupation_family=(
            sca_directory.family_for(resolved_code) if resolved_code else None
        ),
    )
    cls._meta.citation = citation
    cls._meta.candidates = [c.code for c in correction.candidates[:5]]
    for f in code_scored.flags:
        cls._meta.add_flag(f)

    rate, rate_flag = _parse_rate(rate_str)
    if rate is None:
        # A listed classification with no rate on its line. In a two-column
        # scan this is how the code/rate separation manifests: the code line
        # has no adjacent rate. We emit a null rate + hard-confirm flag and
        # never infer one (spec Sections 5, 6). The column-mismatch variant --
        # a rate present but bound to the wrong code -- is detected on the OCR
        # path via bbox/column metadata and scored with orphaned=True.
        cls.base_rate_per_hour = None
        cls._meta.add_flag(rate_flag or Flag.RATE_MISSING)
        cls._meta.confidence = round(min(code_scored.confidence, 0.2), 4)
        return cls

    orphaned = _rate_column_mismatch(ln)
    cls.base_rate_per_hour = rate
    rate_scored = score_rate(
        rate, orphaned=orphaned, code_confidence=code_scored.confidence
    )
    for f in rate_scored.flags:
        cls._meta.add_flag(f)
    # Field confidence is the weaker of code and rate: a classification is only
    # as trustworthy as its least-certain part.
    cls._meta.confidence = round(
        min(code_scored.confidence, rate_scored.confidence), 4
    )
    return cls


def _parse_rate(rate_str: Optional[str]) -> tuple[Optional[Decimal], Optional[Flag]]:
    if not rate_str:
        return None, None
    try:
        return Decimal(rate_str), None
    except InvalidOperation:
        return None, Flag.RATE_MISSING


def _rate_column_mismatch(ln: SourceLine) -> bool:
    """True when a rate is present but its source column does not agree with the
    code's column -- the two-column separation failure where a rate got paired
    to the wrong code. Only the OCR path carries the column metadata needed to
    detect this (it sets ``SourceLine.rate_orphaned``); on a plain text layer
    there is no column signal, so a rate that shares its code's line is trusted
    as adjacent."""
    return ln.rate_orphaned


def _looks_like_code(token: str) -> bool:
    digits = sum(ch.isdigit() for ch in token)
    homoglyphs = sum(ch in ocr_correction._HOMOGLYPH_TO_DIGIT for ch in token)
    return len(token) == 5 and (digits + homoglyphs) == 5 and digits >= 1


# --------------------------------------------------------------------------- #
# Header / fringe / locality blocks
# --------------------------------------------------------------------------- #
def _detect_wd_type(text: str) -> Optional[WdType]:
    """Odd vs even is never guessed. We only assert it when the document says
    so explicitly; otherwise None -> confirmation (spec Sections 4, 6)."""
    low = text.lower()
    if "average cost" in low or "average-cost" in low:
        return WdType.EVEN
    if "per employee" in low or "per-employee" in low:
        return WdType.ODD
    return None


def _parse_locality(doc: Document) -> Locality:
    loc = Locality()
    for ln in doc.lines:
        m = re.search(
            r"(?P<state>[A-Z][a-z]+)\s+Count(?:y|ies)\s+of\s+(?P<counties>.+)",
            ln.text,
        )
        if m:
            loc.state = _state_abbrev(m.group("state"))
            loc.counties = _split_counties(m.group("counties"))
            loc.raw_text = ln.text.strip()
            loc._meta.citation = Citation(ln.page, ln.span(), ln.bbox)
            # A cleanly parsed locality is high-confidence; it only needs
            # confirmation when it mismatches the contract (flagged later).
            loc._meta.confidence = 0.95 if loc.state and loc.counties else 0.5
            break
    return loc


def _parse_hw(doc: Document, full_text: str) -> HealthAndWelfare:
    hw = HealthAndWelfare()
    m = _HW_RATE.search(full_text)
    if m:
        try:
            hw.rate_per_hour = Decimal(m.group(1))
        except InvalidOperation:
            hw.rate_per_hour = None
        for ln in doc.lines:
            if "health" in ln.text.lower() and "welfare" in ln.text.lower():
                hw._meta.citation = Citation(ln.page, ln.span(), ln.bbox)
                break
    return hw


def _parse_holidays(doc: Document, full_text: str) -> Holidays:
    hol = Holidays()
    m = _HOLIDAY_COUNT.search(full_text)
    if m:
        hol.count = int(m.group(1))
        for ln in doc.lines:
            if "holiday" in ln.text.lower():
                hol._meta.citation = Citation(ln.page, ln.span(), ln.bbox)
                break
    return hol


def _parse_vacation(doc: Document) -> TextBlock:
    tb = TextBlock()
    for ln in doc.lines:
        if "vacation" in ln.text.lower():
            tb.text = ln.text.strip()
            tb._meta.citation = Citation(ln.page, ln.span(), ln.bbox)
            break
    return tb


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _first_group(pattern: re.Pattern, text: str) -> Optional[str]:
    m = pattern.search(text)
    return m.group(1) if m else None


def _parse_rev_date(text: str) -> Optional[str]:
    m = _REV_DATE.search(text)
    if not m:
        return None
    mm, dd, yyyy = m.groups()
    return f"{yyyy}-{mm}-{dd}"


_STATES = {
    "California": "CA", "Texas": "TX", "Florida": "FL", "Nevada": "NV",
    "Arizona": "AZ", "Oregon": "OR", "Washington": "WA", "Colorado": "CO",
    "Virginia": "VA", "Georgia": "GA", "Alabama": "AL", "Ohio": "OH",
}


def _state_abbrev(name: str) -> str:
    return _STATES.get(name, name[:2].upper())


def _split_counties(raw: str) -> list[str]:
    parts = re.split(r",|\band\b", raw)
    return [p.strip() for p in parts if p.strip()]


def _similarity(a: str, b: str) -> float:
    import difflib

    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
