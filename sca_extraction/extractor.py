"""Orchestrate a :class:`RawExtraction` into a scored :class:`ExtractionResult`.

This is where the pieces meet: header/fringe fields and every occupational row
are scored via :mod:`sca_extraction.validation`, rolled into the product schema,
and then a single pass over the field metadata builds the confirmation queue
(everything not auto-confirmable). Cross-checking (SAM.gov) is a separate,
optional pass applied afterward by :func:`sca_extraction.crosscheck.reconcile`,
which rebuilds the queue from the same function — so the queue can never drift
from the field metadata.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from . import confidence as conf
from . import validation as V
from .occupations import Directory, default_directory
from .ocr_corrections import repair_title_roman
from .parsing import RawExtraction, RawField, parse_document
from .schema import (
    Citation,
    ConfirmationItem,
    ExtractionResult,
    FieldMeta,
    IngestMode,
    Occupation,
    TracedValue,
    WageDetermination,
)

_WD_NUMBER_RE = re.compile(r"^[0-9]{4}-[0-9]{3,5}$")


def _citation(rf: Optional[RawField]) -> Citation:
    if rf is None:
        return Citation(page=0)
    return Citation(page=rf.page, char_span=rf.char_span, source_line=rf.source_line)


def _score_text_field(
    rf: Optional[RawField],
    is_ocr: bool,
    *,
    pattern: Optional[re.Pattern] = None,
    optional: bool = False,
) -> TracedValue:
    """Score a plain header/fringe text field: presence + optional format check."""
    citation = _citation(rf)
    flags: set[str] = set()
    notes: list[str] = []

    if rf is None or rf.raw is None or not str(rf.raw).strip():
        value = None
        score = Decimal("0.00")
        flags.add("missing")
        notes.append("field not found in document")
    else:
        value = str(rf.raw).strip()
        base = conf.base_for_ocr(is_ocr)
        adjustments = [conf.Adjust.OCR_SOURCE] if is_ocr else [conf.Adjust.CLEAN_TEXT_LAYER]
        if pattern is not None and not pattern.match(value):
            flags.add("format_unexpected")
            notes.append(f"value {value!r} did not match expected format")
            adjustments.append(Decimal("-0.30"))
        score = conf.combine(base, *adjustments)

    meta = FieldMeta(confidence=score, citation=citation, flags=flags, notes=notes, optional=optional)
    return TracedValue(value=value, meta=meta)


def _score_title(
    rf: Optional[RawField],
    is_ocr: bool,
    code_value: Optional[str],
    directory: Directory,
) -> TracedValue:
    """Score an occupation title: repair roman numerals and softly corroborate
    against the directory title for the row's resolved code."""
    citation = _citation(rf)
    flags: set[str] = set()
    notes: list[str] = []

    if rf is None or not rf.raw:
        meta = FieldMeta(confidence=Decimal("0.00"), citation=citation, flags={"missing"})
        return TracedValue(None, meta)

    value, changed = repair_title_roman(rf.raw)
    base = conf.base_for_ocr(is_ocr)
    adjustments = [conf.Adjust.OCR_SOURCE] if is_ocr else [conf.Adjust.CLEAN_TEXT_LAYER]
    if changed:
        flags.add("title_roman_corrected")
        notes.append(f"repaired roman numeral: '{rf.raw}' -> '{value}'")
        adjustments.append(Decimal("-0.10"))

    if code_value is not None:
        canonical = directory.title_for(code_value)
        if canonical and canonical.lower() != value.lower():
            match = directory.best_title_match(value)
            if not (match and match[0] == code_value):
                flags.add("title_code_mismatch")
                notes.append(
                    f"title {value!r} != directory title {canonical!r} for code {code_value}"
                )
                adjustments.append(Decimal("-0.15"))

    score = conf.combine(base, *adjustments)
    meta = FieldMeta(confidence=score, citation=citation, flags=flags, notes=notes)
    return TracedValue(value=value, meta=meta)


def extract(
    raw: RawExtraction,
    source_file: str,
    is_ocr: bool,
    directory: Optional[Directory] = None,
) -> ExtractionResult:
    """Score a parsed document into a full :class:`ExtractionResult`."""
    directory = directory or default_directory()
    mode = IngestMode.OCR if is_ocr else IngestMode.TEXT_LAYER

    wd_number = _score_text_field(raw.wd_number, is_ocr, pattern=_WD_NUMBER_RE)
    revision = _score_text_field(raw.revision, is_ocr)
    revision_date = _score_text_field(raw.revision_date, is_ocr, optional=True)
    locality = _score_text_field(raw.locality, is_ocr)
    hw = V.score_hw(raw.hw_fringe.raw if raw.hw_fringe else None, _citation(raw.hw_fringe), is_ocr)
    vacation = _score_text_field(raw.vacation, is_ocr, optional=True)
    holidays = _score_text_field(raw.holidays, is_ocr, optional=True)
    parity = V.score_parity(wd_number.value, wd_number.meta.citation, wd_number.meta.confidence)

    occupations: list[Occupation] = []
    for row in raw.rows:
        code_tv, _repair = V.score_code(
            row.code.raw if row.code else "", _citation(row.code), is_ocr, directory
        )
        title_tv = _score_title(row.title, is_ocr, code_tv.value, directory)
        rate_tv = V.score_rate(
            row.rate.raw if row.rate else None,
            _citation(row.rate),
            is_ocr,
            orphaned=row.orphaned_rate,
        )
        occupations.append(Occupation(code=code_tv, title=title_tv, rate=rate_tv))

    wd = WageDetermination(
        wd_number=wd_number,
        revision=revision,
        revision_date=revision_date,
        locality=locality,
        parity=parity,
        hw_fringe_rate=hw,
        vacation=vacation,
        holidays=holidays,
        occupations=occupations,
    )

    return ExtractionResult(
        wage_determination=wd,
        source_file=source_file,
        ingest_mode=mode,
        confirmation_queue=build_confirmation_queue(wd),
    )


def build_confirmation_queue(wd: WageDetermination) -> list[ConfirmationItem]:
    """Derive the confirmation queue from live field metadata.

    Single source of truth for "what still needs a human". Called at extraction
    time and again after cross-check reconciliation (when a field's confidence —
    and thus its threshold level — may have shifted). A missing value on an
    ``optional`` field is an acceptable null and is *not* queued; a missing value
    on a required field is.
    """
    queue: list[ConfirmationItem] = []

    def consider(path: str, tv: TracedValue) -> None:
        meta = tv.meta
        if meta.human_confirmed:
            return
        if tv.value is None and meta.optional:
            return  # acceptable null on an optional field
        if not meta.requires_confirmation():
            return
        reason = meta.notes[-1] if meta.notes else f"{path} below confidence threshold"
        queue.append(
            ConfirmationItem(
                path=path,
                reason=reason,
                confidence=meta.confidence,
                current_value=tv.value,
                candidates=list(meta.candidates),
            )
        )

    consider("wage_determination.wd_number", wd.wd_number)
    consider("wage_determination.revision", wd.revision)
    consider("wage_determination.revision_date", wd.revision_date)
    consider("wage_determination.locality", wd.locality)
    consider("wage_determination.hw_fringe_rate", wd.hw_fringe_rate)
    consider("wage_determination.parity", wd.parity)
    consider("wage_determination.vacation", wd.vacation)
    consider("wage_determination.holidays", wd.holidays)
    for idx, occ in enumerate(wd.occupations):
        consider(f"occupations[{idx}].code", occ.code)
        consider(f"occupations[{idx}].title", occ.title)
        consider(f"occupations[{idx}].rate", occ.rate)
    return queue


def extract_from_pages(
    pages: list[tuple[int, str]],
    source_file: str,
    is_ocr: bool,
    directory: Optional[Directory] = None,
) -> ExtractionResult:
    """Convenience: parse page text then score it."""
    raw = parse_document(pages)
    return extract(raw, source_file, is_ocr, directory)
