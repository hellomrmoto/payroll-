# WD Reader — Build Specification

**Companion to:** `PRD.md` §4
**Status:** Text stage implemented (`src/wd/`), PDF/OCR front end specified for Phase 0 completion
**One line:** The formally verifiable extraction engine that turns a wage-determination PDF into a deterministic, typed, per-field-cited JSON structure — the make-or-break system on which the whole product's provable-correctness moat rests.

---

## 1. Why this is a spec and not a feature

Per PRD §0, the moat is correctness and audit-trust. The WD Reader is where a wrong number becomes a debarred customer. It is therefore specified with the same discipline as a safety-critical parser: deterministic output, explicit failure modes, and no silent guessing. The engine is a build, not a paragraph — this document is the contract it must satisfy.

## 2. Pipeline stages

```
PDF ──▶ [1. Ingest] ──▶ [2. OCR/Text] ──▶ [3. Layout] ──▶ [4. Extract] ──▶ WageDeterminationDoc
                              │                                  │
                              └── confidence per glyph           └── confidence + citation per field
```

| Stage | Input | Output | Status |
|---|---|---|---|
| 1. Ingest | WD PDF (SAM.gov / uploaded) | normalized pages, page count | spec |
| 2. OCR/Text | page images | text + per-token confidence + bounding boxes | spec (OCR provider) |
| 3. Layout | text + boxes | line/column structure, table regions | spec |
| 4. Extract | structured text | `WageDeterminationDoc` | **implemented** (`src/wd/reader.ts`) |

Stage 4 is the trustworthy core and is fully implemented and unit-tested against a reference WD offline. Stages 1–3 depend on an OCR provider (document-parsing model per PRD §7) and are the remaining Phase-0 build; the OCR-normalization discipline they must feed is already implemented in `src/wd/ocr.ts`.

## 3. Deterministic output schema

The single source of truth is `src/wd/schema.ts`. Every value is a `Field<T>`:

```ts
interface Field<T> {
  value: T;
  confidence: number;     // [0,1]
  source: SourceSpan;     // page + line + char span + verbatim raw text
  corrected: boolean;     // was OCR-corrected
  raw?: string;           // original token before correction
  needsReview: boolean;   // confidence < REVIEW_THRESHOLD (0.85)
}
```

`WageDeterminationDoc` fields: `wdNumber`, `revision`, `effectiveDate`, `parity` (odd/even), `locality`, `healthAndWelfare`, `classifications[]` (`code`, `title`, `baseRate`), plus `unresolved: ExtractionIssue[]`.

**Determinism guarantee:** identical input text (with a fixed clock) produces a byte-identical document. Verified in `test/reader.test.ts`.

## 4. Confidence scoring

Every field carries a confidence. The review threshold is `0.85` (`REVIEW_THRESHOLD`). Below it, `needsReview` is true and the field is surfaced in `unresolved`; it is **never silently trusted** (PRD §4).

### 4.1 OCR normalization of occupation codes (`src/wd/ocr.ts`)

SCA occupation codes are 5-digit numeric codes from the SCA Directory of Occupations, which gives a dictionary to correct against. Two classes of fix:

- **Unambiguous glyph fixes** — a glyph that cannot be valid in a numeric code (`@`→`0`, `e`→`0`, `l`→`1`, …). Information-preserving; high confidence. Demonstrated: `@1311`→`01311`, `e9eee`→`09000`.
- **Ambiguous digit-to-digit fixes** — a valid digit likely misread as another (`6`→`0`). Applied only when it lands on a known Directory code, always flagged, medium confidence (≈0.6). Demonstrated: `61313`→`01313`, surfaced for review.

A token that cannot be resolved to five digits is returned low-confidence for human confirmation.

## 5. Citation traceability

Every `Field` carries a `SourceSpan` (page, line range, char range, verbatim raw text) so a skeptical, non-technical contractor can see exactly where the tool read a number (PRD §5.2). When stages 1–3 land, `SourceSpan` gains the PDF bounding box; the line/char span is the text-stage equivalent and is already populated.

## 6. Conflict resolution

| Situation | Behavior |
|---|---|
| Two classifications, same code | Both rows retained; `duplicate_classification` issue emitted. |
| Missing rate on a row | Row not emitted as a classification; the line is flagged (`unparseable_line`) rather than defaulted. |
| Ambiguous OCR correction (multiple known codes reachable) | Printed token kept, confidence lowered, `ambiguous_correction` issue emitted; never auto-picked. |
| Missing header field (WD number, H&W, date, locality) | Empty value at confidence 0 + `missing_field` issue. Never fabricated. |
| Odd/even parity | Derived heuristically from the WD number's trailing digit at confidence 0.6; flagged for confirmation against the WD's stated type. |

## 7. Failure modes (explicit)

The engine's contract when it cannot read something is to **represent the gap, not fill it**:

- Unreadable field → `Field` with `confidence: 0`, empty/zero value, and a `missing_field` `ExtractionIssue`.
- Low-confidence field → `needsReview: true` and a `low_confidence` issue.
- Corrupted code → best-effort value with `corrected`/`ambiguous` flags and an issue.

Nothing is defaulted to a plausible-looking number. The `unresolved[]` array is the human-review worklist.

## 8. Testing & acceptance

- `test/ocr.test.ts` — the three demonstrated corruptions, ambiguity handling, determinism.
- `test/reader.test.ts` — header extraction, classification parsing, citation spans, surfaced corrections, missing-field behavior, determinism.

**Acceptance for Phase-0 production-grade (per PRD §9 kill-gate):** stages 1–3 integrated with an OCR provider; end-to-end run on the founder's real janitorial WDs; every field either at/above threshold or on the review worklist; zero silently-trusted low-confidence fields.

## 9. Open build items (stages 1–3)

1. OCR provider selection (document-parsing model) with per-token confidence + bounding boxes.
2. Table-region detection for multi-column WD layouts.
3. Bounding-box population of `SourceSpan` for PDF drill-down in the UI.
4. Expansion of `directory.ts` from the seed subset to the full ingested SCA Directory (PRD §7 pipeline).
