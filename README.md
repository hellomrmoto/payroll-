# payroll-

## SCA Wage Determination Extraction (`sca_extraction`)

Turn a government **Service Contract Act (SCA) wage determination** — including
scanned/image-only and two-column documents — into a deterministic,
citation-traceable data object with per-field confidence and a human
confirmation queue, ready for downstream payroll and ledger use.

> **Core principle.** A silently-wrong wage rate causes a contractor to underpay
> a worker, which causes a DOL finding and possible debarment. So this library's
> job is **not** "extract fast" — it is *never emit a wrong number as if it were
> right.* When unsure, it queues for human confirmation. **Uncertainty surfaced
> is success; false confidence is failure.**

This is the engineering implementation of the `sca-wd-extract` skill.

### What it produces

A deterministic JSON object where **every leaf value carries `_meta`** with its
confidence, the confidence *level*, whether it was cross-checked, and a
**citation** (page + character span / bbox) back into the source document — plus
an `extraction_meta.fields_requiring_confirmation` queue.

```jsonc
{
  "wage_determination": {
    "wd_number": { "value": "2015-4281", "_meta": { "confidence": "1.00", "level": "soft_confirm", "citation": {"page": 1} } },
    "hw_fringe_rate": { "value": "5.55", "_meta": { "confidence": "1.00", "level": "auto_confirm", "cross_checked": true, "flags": ["hw_matches_national"] } },
    "parity": { "value": "odd", "_meta": {} },
    "occupations": [
      { "code":  { "value": "01311", "_meta": { "flags": ["code_corrected"] } },
        "title": { "value": "Secretary I", "_meta": {} },
        "rate":  { "value": "22.05", "_meta": {} } }
    ]
  },
  "extraction_meta": {
    "ingest_mode": "ocr",
    "cross_check": { "performed": true, "available": false, "source": "sam.gov" },
    "fields_requiring_confirmation": [ { "path": "occupations[0].code", "reason": "...", "candidates": [] } ]
  }
}
```

### Confidence model

| Level          | Condition                                   | Meaning                               |
|----------------|---------------------------------------------|---------------------------------------|
| `auto_confirm` | confidence ≥ 0.95 **and** cross-checked     | flows downstream automatically        |
| `soft_confirm` | 0.80 ≤ confidence < 0.95                     | one-click human accept                |
| `hard_confirm` | confidence < 0.80                            | must be confirmed before use          |

Two consequences worth calling out, both intentional:

- **Auto-confirm requires a cross-check.** A field can be read with 1.00
  confidence off a pristine text layer and still be `soft_confirm`, because
  nothing external corroborated it yet. Wire up a SAM.gov provider (below) to
  let matching fields reach `auto_confirm`.
- **The 0↔6 / 0↔8 OCR confusion makes some codes genuinely ambiguous.** e.g. a
  scanned `@1011` could be `01011` (Accounting Clerk I) *or* `01611` (Word
  Processor I). The extractor refuses to pick one and queues it with both
  candidates rather than guessing. This is the safety property, not a bug.

Values are stored as exact `Decimal` and serialised as **strings** — never
floats — so `18.42` stays `18.42` on every machine.

### Usage

```python
from sca_extraction import extract_wage_determination

# Full pipeline from a PDF (auto-detects text-layer vs image-only + OCR):
result = extract_wage_determination("WD_2015-4281.pdf")
print(result.to_dict())
for item in result.confirmation_queue:
    print(item.path, item.reason, item.candidates)
```

Cross-check against a structured SAM.gov record (matches boost & auto-confirm,
divergences surface **both** values and are penalised):

```python
def sam_provider(wd_number, revision):
    # return an object with .hw_fringe_rate and .rates_by_code, or None if
    # SAM.gov was unavailable (we never claim "cross-checked" on an unavailable
    # source).
    ...

result = extract_wage_determination("WD.pdf", sam_provider=sam_provider)
```

Score already-extracted page text (no PDF tooling needed):

```python
from sca_extraction import extract_from_pages
result = extract_from_pages([(1, page_text)], source_file="WD.txt", is_ocr=True)
```

CLI:

```bash
python -m sca_extraction WD.pdf --pretty            # from a PDF
python -m sca_extraction --text page1.txt --pretty  # from raw text pages
# exit 0 = clean, 2 = items need confirmation, 3 = ingest/extract failed
```

### Architecture

The scoring **core is pure Python with no third-party dependencies** and is
fully unit-tested without any PDF tooling. PDF ingestion is isolated so it can
degrade gracefully.

| Module               | Responsibility                                                             |
|----------------------|----------------------------------------------------------------------------|
| `schema.py`          | Data model: `TracedValue`/`FieldMeta`/`Citation`, WD schema, result object |
| `confidence.py`      | Thresholds, additive penalty/boost scoring, level classification           |
| `occupations.py`     | SCA Directory of Occupations lookup (bundled subset + fuzzy title match)   |
| `ocr_corrections.py` | Directory-constrained code repair; roman-numeral repair                    |
| `hw_schedule.py`     | National H&W fringe schedule for cross-checking                            |
| `validation.py`      | Code/rate/H&W/parity validation + confidence scoring rules                 |
| `parsing.py`         | Locate header/fringe/listing blocks; reunite orphaned two-column rates     |
| `extractor.py`       | Orchestrate raw → scored result; build the confirmation queue              |
| `crosscheck.py`      | SAM.gov reconciliation (honest availability handling)                      |
| `ingest.py`          | PDF classify (text-layer vs image-only) + OCR (poppler/tesseract)          |

### Failure modes it refuses to commit

- Never pairs a code to a rate by proximity guess. Orphaned two-column rates are
  only reunited by strict adjacency, and stay flagged `rate_orphaned`.
- Never invents or infers a missing rate or code.
- Never claims `cross_checked` when the SAM.gov source was unavailable.
- Never emits partial silent data from a corrupt file — ingestion rejects a
  document that yields no usable text and asks for re-upload.
- WD odd/even parity is attempted but left `null` (never guessed) when the WD
  number is unreadable.

### Optional runtime dependencies (PDF ingest only)

The core has none. PDF ingestion shells out to, and requires when used:

- `pdftotext` and `pdftoppm` (from **poppler-utils**)
- `tesseract` (**tesseract-ocr**) for image-only pages, rasterised at ≥300 DPI
  with page-segmentation mode 6

If they are missing, `ingest_pdf` raises a clear `IngestError` rather than
returning silent empty text.

### Scope & limitations

- The bundled `data/sca_directory.json` is a **curated subset** of the SCA
  Directory of Occupations for validation/correction. Supply the full official
  directory via `load_directory(path)` for production.
- No SAM.gov network client is bundled (environments may be offline); inject a
  provider to enable cross-checking.
- This is for **SCA** wage determinations. It is **not** for Davis-Bacon
  construction wage determinations (different structure), and it does **not**
  certify compliance.

### Tests

```bash
python -m unittest discover -s tests
```
