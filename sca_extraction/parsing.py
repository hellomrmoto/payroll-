"""Locate the structural blocks of an SCA wage determination and parse rows.

Input is page text (from a real text layer or from OCR). Output is a
``RawExtraction`` of *raw strings* with citations — deliberately unscored and
uncorrected. All validation, correction and confidence live in
:mod:`sca_extraction.validation`; this module only finds and slices text.

The parser is line-oriented and tolerant. It handles the common single-line
listing row (``CODE - Title .... RATE``) and detects two failure shapes the
skill calls out:
  * an **orphaned rate** — a line that is only a rate, with no code/title, which
    happens when a two-column layout splits the code from its rate;
  * a **rateless row** — a code/title line with no rate on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RawField:
    raw: Optional[str]
    page: int
    char_span: Optional[tuple[int, int]] = None
    source_line: Optional[str] = None


@dataclass
class RawRow:
    code: Optional[RawField]
    title: Optional[RawField]
    rate: Optional[RawField]
    orphaned_rate: bool = False  # rate present but code/title missing on the line


@dataclass
class RawExtraction:
    wd_number: Optional[RawField] = None
    revision: Optional[RawField] = None
    revision_date: Optional[RawField] = None
    locality: Optional[RawField] = None
    hw_fringe: Optional[RawField] = None
    vacation: Optional[RawField] = None
    holidays: Optional[RawField] = None
    rows: list[RawRow] = field(default_factory=list)


# --- Regexes ----------------------------------------------------------------

_WD_NUMBER = re.compile(r"Wage\s+Determination\s+No\.?\s*:?\s*([0-9]{4}-[0-9]{3,5})", re.I)
_REVISION = re.compile(r"Revision\s+No\.?\s*:?\s*([0-9]{1,3})", re.I)
_REV_DATE = re.compile(r"Date\s+Of\s+Revision\s*:?\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})", re.I)
_STATE = re.compile(r"State\s*:?\s*(.+)", re.I)
_AREA = re.compile(r"Area\s*:?\s*(.+)", re.I)
_HW = re.compile(r"HEALTH\s*&?\s*WELFARE\s*:?\s*(.+)", re.I)
_VACATION = re.compile(r"VACATION\s*:?\s*(.+)", re.I)
_HOLIDAYS = re.compile(r"HOLIDAYS?\s*:?\s*(.+)", re.I)

# A standalone monetary amount (used to spot orphaned rates).
_LONE_RATE = re.compile(r"^\s*\$?\s*([0-9]{1,3}(?:\.[0-9]{2})?)\s*$")

# CODE - TITLE ....(2+ spaces).... RATE  — the canonical listing row.
_ROW = re.compile(
    r"^\s*(?P<code>[0-9A-Za-z@|\.\-]{3,8})\s*[-–—]\s*(?P<title>.+?)\s{2,}"
    r"\$?\s*(?P<rate>[0-9]{1,3}\.[0-9]{2})\s*$"
)

# CODE - TITLE with no rate on the line (rate may be orphaned nearby / two-col).
_ROW_NO_RATE = re.compile(
    r"^\s*(?P<code>[0-9A-Za-z@|\.\-]{3,8})\s*[-–—]\s*(?P<title>[A-Za-z].+?)\s*$"
)


def _looks_like_listing(line: str) -> bool:
    return bool(_ROW.match(line) or _ROW_NO_RATE.match(line))


def parse_document(pages: list[tuple[int, str]]) -> RawExtraction:
    """Parse a list of ``(page_number, text)`` into a :class:`RawExtraction`.

    Page numbers are 1-indexed and preserved in citations.
    """
    out = RawExtraction()

    for page_no, text in pages:
        offset = 0
        for line in text.splitlines(keepends=True):
            stripped = line.rstrip("\n")
            start = offset
            offset += len(line)
            span = (start, start + len(stripped))

            _match_header_fields(out, stripped, page_no, span)
            _match_fringe_fields(out, stripped, page_no, span)
            _match_row(out, stripped, page_no, span)

    _link_orphaned_rates(out)
    return out


def _set_once(out: RawExtraction, attr: str, field_obj: RawField) -> None:
    if getattr(out, attr) is None:
        setattr(out, attr, field_obj)


def _match_header_fields(out: RawExtraction, line: str, page: int, span: tuple[int, int]) -> None:
    m = _WD_NUMBER.search(line)
    if m:
        _set_once(out, "wd_number", RawField(m.group(1), page, span, line))
    m = _REVISION.search(line)
    if m:
        _set_once(out, "revision", RawField(m.group(1), page, span, line))
    m = _REV_DATE.search(line)
    if m:
        _set_once(out, "revision_date", RawField(m.group(1), page, span, line))
    m = _STATE.match(line.strip())
    if m and out.locality is None:
        out.locality = RawField(m.group(1).strip(), page, span, line)
    else:
        m = _AREA.match(line.strip())
        if m and out.locality is None:
            out.locality = RawField(m.group(1).strip(), page, span, line)


def _match_fringe_fields(out: RawExtraction, line: str, page: int, span: tuple[int, int]) -> None:
    m = _HW.search(line)
    if m:
        _set_once(out, "hw_fringe", RawField(m.group(1).strip(), page, span, line))
    m = _VACATION.search(line)
    if m:
        _set_once(out, "vacation", RawField(m.group(1).strip(), page, span, line))
    m = _HOLIDAYS.search(line)
    if m:
        _set_once(out, "holidays", RawField(m.group(1).strip(), page, span, line))


def _match_row(out: RawExtraction, line: str, page: int, span: tuple[int, int]) -> None:
    m = _ROW.match(line)
    if m:
        out.rows.append(
            RawRow(
                code=RawField(m.group("code"), page, span, line),
                title=RawField(m.group("title").strip(), page, span, line),
                rate=RawField(m.group("rate"), page, span, line),
            )
        )
        return

    m = _ROW_NO_RATE.match(line)
    if m and not _HW.search(line) and not _VACATION.search(line) and not _HOLIDAYS.search(line):
        out.rows.append(
            RawRow(
                code=RawField(m.group("code"), page, span, line),
                title=RawField(m.group("title").strip(), page, span, line),
                rate=None,
            )
        )
        return

    # A line that is nothing but a monetary amount -> candidate orphaned rate.
    m = _LONE_RATE.match(line)
    if m and "." in m.group(1):
        out.rows.append(
            RawRow(
                code=None,
                title=None,
                rate=RawField(m.group(1), page, span, line),
                orphaned_rate=True,
            )
        )


def _link_orphaned_rates(out: RawExtraction) -> None:
    """Attach a lone orphaned rate to an immediately-preceding rateless row.

    We only link by *strict adjacency* (the orphan directly follows a code/title
    row that itself has no rate). This is not a proximity *guess* about which
    code owns the rate in a wrong-but-plausible way — it is the mechanical
    recomposition of a single logical row that OCR split across two physical
    lines. The reunited rate keeps the ``orphaned`` flag so it is still scored
    down and surfaced for confirmation; we never present it as clean.
    """
    linked: list[RawRow] = []
    i = 0
    rows = out.rows
    while i < len(rows):
        row = rows[i]
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        if (
            row.rate is None
            and row.code is not None
            and nxt is not None
            and nxt.orphaned_rate
            and nxt.code is None
        ):
            row.rate = nxt.rate
            row.orphaned_rate = True  # mark the row: its rate was reunited from an orphan
            linked.append(row)
            i += 2
            continue
        linked.append(row)
        i += 1
    out.rows = linked
