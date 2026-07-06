---
name: sca-wd-extract
description: The SCA wage-determination extraction discipline. Use when reading, parsing, or validating a McNamara-O'Hara Service Contract Act (SCA) wage determination into structured data — enforcing the deterministic schema, confidence scoring, OCR-correction rules, citation traceability, and explicit failure handling. Triggers on "wage determination", "WD reader", "extract WD", "SCA classification codes", "H&W rate parsing", OCR-corrupted occupation codes.
---

# sca-wd-extract — Wage-determination extraction discipline

Spun off from `Clean Payroll and Ledger` PRD §4. This is the make-or-break
extraction discipline: a wrong number here is a debarred customer. Follow it
exactly. Implementation lives in `src/wd/` (`schema.ts`, `ocr.ts`, `reader.ts`).

## Non-negotiable rules

1. **Deterministic, typed output.** Every WD becomes a fixed `WageDeterminationDoc`
   (`src/wd/schema.ts`). Identical input → identical output. No field is optional
   in shape; a missing value is represented explicitly, never omitted.

2. **Every value is a `Field<T>`.** It carries `value`, `confidence` in [0,1],
   a `SourceSpan` (page + line + char span + verbatim raw text), a `corrected`
   flag, the original `raw` token, and `needsReview`. Never emit a bare value.

3. **Confidence scoring, review threshold 0.85.** Anything below is
   `needsReview: true` and goes on the `unresolved[]` worklist. Low-confidence
   fields are surfaced for human confirmation — **never silently trusted**.

4. **OCR correction has two tiers** (`src/wd/ocr.ts`):
   - *Unambiguous glyph fixes* (`@`→`0`, `e`→`0`, `l`→`1`): high confidence.
     Demonstrated: `@1311`→`01311`, `e9eee`→`09000`.
   - *Ambiguous digit swaps* (`6`→`0`): only to reach a known Directory code,
     always flagged, confidence ≈0.6. Demonstrated: `61313`→`01313`.
   - Unresolvable token: low confidence, defer to human.

5. **Citation traceability.** Every field links to where it was read
   (`SourceSpan`). A skeptical user must be able to see the exact source span.

6. **Explicit failure modes.** Cannot read a field → `confidence: 0` + a
   `missing_field` `ExtractionIssue`. Never fabricate a plausible number.
   Duplicate codes → keep both + `duplicate_classification`. Ambiguous
   correction → keep printed token + `ambiguous_correction`.

## Workflow

1. Get the WD as text (OCR front end feeds this; see `WD_Reader_Build_Spec.md`).
2. Call `readWageDetermination(text)` from `src/wd/reader.ts`.
3. Inspect `doc.unresolved[]` — this is the human-review worklist. Do not
   proceed as if unreviewed low-confidence fields are trustworthy.
4. Confirm ambiguous corrections and heuristic parity against the WD itself.

## Do NOT

- Do not default a missing rate to 0 or to a neighboring row's value.
- Do not auto-pick among multiple plausible OCR corrections.
- Do not treat the seed `directory.ts` as authoritative — the production
  Directory is ingested from SAM.gov/DOL (PRD §7).
