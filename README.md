# WD Reader

**The make-or-break engine of Clean Payroll and Ledger.** It turns a government
wage-determination PDF — including a scanned, image-only, two-column one — into
a **deterministic, typed, citation-traceable** data structure with **per-field
confidence** and a **human-confirmation queue** for anything the machine is not
sure about.

This repository implements the WD Reader Production Build Spec (v1.0, Phase 0).

---

## The cardinal rule

> A rate is only emitted downstream as **confirmed** if it is either
> **(a)** above the confidence threshold **AND** cross-checked against the
> authoritative SAM.gov structured WD, or **(b)** human-confirmed.
> Everything else lands in the confirmation queue.

Confidence scoring and human confirmation are not features — they are the safety
system. A wrong wage rate that passes as "confirmed" is the exact liability
event this product exists to prevent, so the correctness gate is absolute.

---

## What is in this repository (and the honesty boundary)

The correctness-critical core is built **and proven with tests**, using only the
Python standard library:

| Capability | Module | Status |
|---|---|---|
| Deterministic typed output schema, exact decimals | `schema.py` | **Implemented + tested** |
| SCA Directory of Occupations (code authority) | `sca_directory.py` | **Implemented** (representative subset; full list is a data swap) |
| OCR corruption detection + correction | `ocr_correction.py` | **Implemented + tested** |
| Validation + confidence scoring + thresholds | `confidence.py` | **Implemented + tested** |
| Structural parse / field extraction | `extraction.py` | **Implemented + tested** |
| Conflict resolution | `conflict.py` | **Implemented + tested** |
| SAM.gov cross-check reconciliation | `crosscheck.py` | **Implemented + tested** (live client is an adapter; offline double provided) |
| Human-confirmation queue | `confirmation.py` | **Implemented + tested** |
| Pipeline orchestration | `pipeline.py` | **Implemented + tested** |

The parts that depend on external systems are **clean, documented adapter
seams** — the engine core never depends on them directly:

- **`sources.OcrExtractor`** shells out to Poppler (`pdftoppm`) + Tesseract at
  ≥ 300 DPI with a layout-aware page-segmentation mode (PSM 6) — exactly what
  fixed the two-column code/rate separation on the reference document. It
  requires those binaries; where they are absent it raises `SourceUnavailable`
  rather than degrading silently. It is **not claimed to be exercised** in an
  environment without them.
- **`crosscheck.SamGovSource`** is a protocol; the live SAM.gov client plugs in
  behind it. The deterministic reconciliation logic is tested against an
  in-memory double (`InMemorySamGov`), so no network is required to prove it.

This mirrors the spec's own honesty boundary: this is the engine, built to the
blueprint, with the correctness gate provable offline. The OCR of a specific
real scanned PDF and the live SAM.gov fetch are integration points, wired but
gated on their external dependencies.

---

## Quick start

```bash
# Run the built-in reference example (hostile OCR of WD 2015-5657, no SAM.gov)
PYTHONPATH=src python3 -m wd_reader demo

# Read a real PDF (needs Poppler + Tesseract for image-only scans)
PYTHONPATH=src python3 -m wd_reader read path/to/wd.pdf --state CA --county Tulare

# Run the test suite
python3 -m pip install pytest
python3 -m pytest -q
```

### As a library

```python
from decimal import Decimal
from wd_reader import read_pdf, ContractMetadata, InMemorySamGov, StructuredWd

samgov = InMemorySamGov({
    "2015-5657": StructuredWd(
        wd_number="2015-5657", revision=24,
        rates_by_code={"11150": Decimal("17.56")}, hw_rate=Decimal("5.55"),
    )
})
result = read_pdf(
    "wd.pdf",
    contract=ContractMetadata(pop_state="CA", pop_county="Tulare"),
    samgov=samgov,
)
print(result.wage_determination.to_json())
for item in result.confirmation_queue:      # only the doubtful fields
    print(item.field_path, item.value, item.disposition, item.note)
```

---

## Why this is hard (grounded in a real document)

The reference document, **WD 2015-5657** (Tulare County, CA), is a scanned image
PDF. Text extraction returns nothing; it requires OCR, and the OCR is
corruptible. The corruptions below are real observations, and the engine
recovers every one to ground truth (see `tests/test_ocr_correction.py`):

| Ground truth | OCR output | Recovered to |
|---|---|---|
| `01311 - Secretary I` | `@1311 - Secretary I` | `01311` |
| `01313 - Secretary III` | `61313 - Secretary IIT` | `01313` |
| `09000 - Furniture…` | `e9eee - Furniture…` | `09000` (family header) |
| `11150 - Janitor` | `11150 - Janitor` | `11150` (clean) |

Recovery uses three independent signals — homoglyph mapping, bounded digit
confusions, and **title match against the SCA Directory** (the title is the
primary key; it is what disambiguates `61313 → 01313`). Candidates are **only
ever real Directory codes**: the engine never invents a code.

Run `python3 -m wd_reader demo` and observe: with no SAM.gov cross-check,
**nothing auto-confirms** — the two corrupted codes surface (the badly-mangled
one as a *hard* confirmation), and every clean value is a one-click soft accept.
With a cross-check that agrees, the queue empties and overall confidence is
high. That is the safety system doing its job.

---

## Output schema

Every wage determination produces the same fixed, typed shape (`schema.py`).
Every leaf value carries `_meta.confidence` (0.0–1.0) and `_meta.citation`
(page + span/bbox). Rates are exact `Decimal`s that never drift. `wd_type`
(odd = per-employee fringe vs. even = average-cost — it changes the downstream
29 CFR 4.52 / 4.175 compliance math) is attempted but **never guessed**: if
indeterminate it is `null` and goes to confirmation. See the spec, Section 4,
for the full shape; `wage_determination.to_json()` emits it.

---

## Confidence thresholds (tunable)

| Band | Disposition |
|---|---|
| ≥ 0.95 **and** cross-checked | auto-confirmed |
| 0.80 – 0.95 | soft-confirm (one-click accept) |
| < 0.80 | hard confirmation required before flowing downstream |

Thresholds live in `confidence.Thresholds` and are configuration, tunable after
Phase 0 dogfooding.

---

## Failure modes (spec Section 8)

The engine refuses to emit partial silent data. Unreadable file →
`DocumentRejected`. Image too low-res to OCR → document-level low-confidence
flag, request a better scan. Unrecoverable code → `null` + hard confirm, never
invented. Orphaned rate → queued with its source crop, never paired by
proximity guess. Locality ≠ contract county → hard flag (possible wrong WD).
SAM.gov unavailable → proceed on OCR + confidence, mark
`cross_checked_against_samgov: false`, and raise the confirmation bar — never
claim a cross-check that did not happen.

---

## Testing

```bash
python3 -m pytest -q
```

The suite covers: every reference corruption → correct recovery; the
**zero-silent-wrong-rates** gate (Phase 0 acceptance criterion 1); cross-check
enabling auto-confirm on agreement and blocking it on divergence; orphaned /
out-of-band / missing rates; locality mismatch; indeterminate `wd_type`;
duplicate titles; document rejection; and schema faithfulness (exact decimals,
stable JSON shape).

---

## Layout

```
src/wd_reader/
  schema.py         # typed output schema, exact-decimal serialization
  sca_directory.py  # SCA Directory of Occupations (code authority)
  ocr_correction.py # corruption detection + correction (never invents a code)
  hw_schedule.py    # known national H&W rates
  confidence.py     # validation, confidence scoring, thresholds, the gate
  extraction.py     # structural parse + field extraction with citations
  conflict.py       # conflict resolution (defined behavior, not guesswork)
  crosscheck.py     # SAM.gov reconciliation (adapter + offline double)
  confirmation.py   # human-confirmation queue (the trust surface)
  sources.py        # PDF text-layer / OCR extraction adapters
  pipeline.py       # orchestration; read_document (core) and read_pdf (front)
  cli.py            # `python -m wd_reader`
tests/              # pytest suite proving the correctness gates
```
