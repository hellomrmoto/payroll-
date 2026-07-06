/**
 * The WD Reader — extraction engine (text stage).
 *
 * PRD §4: "the make-or-break system ... a formally verifiable extraction
 * engine, not a feature." This module is the deterministic text-to-schema
 * stage: given the plain text of a wage determination (the output of the OCR
 * stage on a PDF), it produces the typed `WageDeterminationDoc` with a
 * citation span and confidence for every field.
 *
 * It is deterministic (same text in -> same doc out), it never guesses (a
 * field it cannot read becomes an explicit `ExtractionIssue`), and every
 * classification code passes through the OCR normalizer against the SCA
 * Directory (PRD §4 confidence scoring + failure modes).
 *
 * The PDF/OCR front end is a separate build stage (see WD_Reader_Build_Spec.md);
 * this stage is the trustworthy core and is fully unit-testable offline.
 */

import {
  type WageDeterminationDoc,
  type WageClassification,
  type ExtractionIssue,
  type SourceSpan,
  field,
} from "./schema.ts";
import { normalizeOccupationCode } from "./ocr.ts";
import { DIRECTORY_CODES } from "./directory.ts";

export const READER_VERSION = "0.1.0";

/** A single physical line, retaining its 1-indexed number and page. */
interface Line {
  page: number;
  n: number;
  text: string;
}

/** Split text into lines, tracking page breaks on form-feed (\f). */
function toLines(text: string): Line[] {
  const out: Line[] = [];
  let page = 1;
  let n = 0;
  for (const rawLine of text.split("\n")) {
    // A form feed starts a new page; it may sit at the head of a line.
    if (rawLine.includes("\f")) {
      const parts = rawLine.split("\f");
      // text before the first \f belongs to the current page
      n++;
      out.push({ page, n, text: parts[0] });
      for (let i = 1; i < parts.length; i++) {
        page++;
        n++;
        out.push({ page, n, text: parts[i] });
      }
      continue;
    }
    n++;
    out.push({ page, n, text: rawLine });
  }
  return out;
}

/** Build a SourceSpan covering a matched substring within a line. */
function spanOf(line: Line, matchText: string, charStart: number): SourceSpan {
  return {
    page: line.page,
    lineStart: line.n,
    lineEnd: line.n,
    charStart,
    charEnd: charStart + matchText.length,
    rawText: matchText,
  };
}

/** Find the first line matching `re`, returning the line and match. */
function findLine(lines: Line[], re: RegExp): { line: Line; m: RegExpMatchArray } | undefined {
  for (const line of lines) {
    const m = line.text.match(re);
    if (m) return { line, m };
  }
  return undefined;
}

const MONEY = /\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})|\d+\.\d{2})/;

/** Parse a US money string like "1,234.56" or "17.56" to a number. */
function parseMoney(s: string): number {
  return Number(s.replace(/[$,\s]/g, ""));
}

/** Convert MM/DD/YYYY to ISO YYYY-MM-DD. */
function toIsoDate(mm: string, dd: string, yyyy: string): string {
  return `${yyyy}-${mm.padStart(2, "0")}-${dd.padStart(2, "0")}`;
}

/**
 * Parse a classification row of the form:
 *   `<CODE> - <TITLE> ................ <RATE>`
 * where CODE is a 5-char token (possibly OCR-corrupted). Returns undefined if
 * the line is not a classification row.
 */
function parseClassificationLine(
  line: Line,
  issues: ExtractionIssue[],
): WageClassification | undefined {
  // Leading token of exactly 5 non-space chars, a dash, a title, trailing rate.
  const re = /^\s*([^\s]{5})\s*[-–—]\s*(.+?)\s+\$?(\d+\.\d{2})\s*$/;
  const m = line.text.match(re);
  if (!m) return undefined;

  const rawCode = m[1];
  const rawTitle = m[2].trim();
  const rawRate = m[3];

  // Offsets within the line for citation spans.
  const codeStart = line.text.indexOf(rawCode);
  const titleStart = line.text.indexOf(rawTitle, codeStart + rawCode.length);
  const rateStart = line.text.lastIndexOf(rawRate);

  // --- code: OCR-normalize against the Directory ---
  const corr = normalizeOccupationCode(rawCode, DIRECTORY_CODES);
  const codeField = field(corr.value, corr.confidence, spanOf(line, rawCode, codeStart), {
    corrected: corr.corrected,
    raw: corr.corrected ? corr.raw : undefined,
  });
  if (corr.corrected && corr.ambiguous) {
    issues.push({
      kind: "ambiguous_correction",
      message: `Occupation code "${corr.raw}" corrected to "${corr.value}" via an ambiguous digit swap; confirm before trusting.`,
      source: codeField.source,
    });
  } else if (corr.corrected) {
    issues.push({
      kind: "ocr_corrected",
      message: `Occupation code "${corr.raw}" OCR-corrected to "${corr.value}".`,
      source: codeField.source,
    });
  }
  if (codeField.needsReview) {
    issues.push({
      kind: "low_confidence",
      message: `Occupation code "${corr.value}" extracted at low confidence (${corr.confidence.toFixed(2)}).`,
      source: codeField.source,
    });
  }

  // --- title: high confidence; it is literal text ---
  const titleField = field(rawTitle, 0.98, spanOf(line, rawTitle, Math.max(titleStart, 0)));

  // --- rate: parse money ---
  const rateVal = parseMoney(rawRate);
  const rateField = field(rateVal, 0.97, spanOf(line, rawRate, Math.max(rateStart, 0)));

  return { code: codeField, title: titleField, baseRate: rateField };
}

/**
 * Extract a `WageDeterminationDoc` from the plain text of a wage
 * determination. Deterministic; unresolved fields are surfaced, never guessed.
 *
 * @param text plain text of the WD (one document)
 * @param now  ISO timestamp injected for deterministic tests; defaults to real time
 */
export function readWageDetermination(text: string, now?: string): WageDeterminationDoc {
  const lines = toLines(text);
  const unresolved: ExtractionIssue[] = [];

  // WD number
  const wdHit = findLine(lines, /Wage Determination No\.?:?\s*([0-9]{4}-[0-9]{3,5})/i);
  let wdNumber;
  if (wdHit) {
    const val = wdHit.m[1];
    const at = wdHit.line.text.indexOf(val);
    wdNumber = field(val, 1, spanOf(wdHit.line, val, at));
  } else {
    unresolved.push({ kind: "missing_field", message: "Wage Determination number not found." });
    wdNumber = field("", 0, { page: 1, lineStart: 1, lineEnd: 1, charStart: 0, charEnd: 0, rawText: "" });
  }

  // Revision
  const revHit = findLine(lines, /Revision No\.?:?\s*(\d+)/i);
  let revision;
  if (revHit) {
    const val = Number(revHit.m[1]);
    const at = revHit.line.text.indexOf(revHit.m[1]);
    revision = field(val, 1, spanOf(revHit.line, revHit.m[1], at));
  } else {
    unresolved.push({ kind: "missing_field", message: "Revision number not found." });
    revision = field(0, 0, { page: 1, lineStart: 1, lineEnd: 1, charStart: 0, charEnd: 0, rawText: "" });
  }

  // Effective / revision date
  const dateHit = findLine(lines, /Date Of Revision:?\s*(\d{1,2})\/(\d{1,2})\/(\d{4})/i);
  let effectiveDate;
  if (dateHit) {
    const iso = toIsoDate(dateHit.m[1], dateHit.m[2], dateHit.m[3]);
    const raw = dateHit.m[0].split(":").pop()!.trim();
    const at = dateHit.line.text.indexOf(raw);
    effectiveDate = field(iso, 0.98, spanOf(dateHit.line, raw, at >= 0 ? at : 0));
  } else {
    unresolved.push({ kind: "missing_field", message: "Date of revision not found." });
    effectiveDate = field("", 0, { page: 1, lineStart: 1, lineEnd: 1, charStart: 0, charEnd: 0, rawText: "" });
  }

  // Parity — odd/even numbered determination. Derived from the trailing numeric
  // segment of the WD number. This is a documented heuristic (SCA odd/even
  // mechanic); flagged low-confidence so a human confirms the WD's stated type.
  const trailing = wdNumber.value.split("-").pop() ?? "";
  const lastDigit = trailing.slice(-1);
  const parityVal: "odd" | "even" = Number(lastDigit) % 2 === 0 ? "even" : "odd";
  const parity = field(parityVal, wdNumber.value ? 0.6 : 0, wdNumber.source);
  if (parity.needsReview) {
    unresolved.push({
      kind: "low_confidence",
      message: `Odd/even determination type derived heuristically from WD number (${parityVal}); confirm against the WD's stated type.`,
      source: wdNumber.source,
    });
  }

  // Locality — State + Area lines.
  const stateHit = findLine(lines, /^\s*State:\s*(.+?)\s*$/i);
  const areaHit = findLine(lines, /^\s*Area:\s*(.+?)\s*$/i);
  let locality;
  if (stateHit) {
    const stateVal = stateHit.m[1].trim();
    const areaVal = areaHit ? areaHit.m[1].trim() : "";
    const localityVal = areaVal ? `${stateVal} — ${areaVal}` : stateVal;
    const at = stateHit.line.text.indexOf(stateVal);
    locality = field(localityVal, areaHit ? 0.95 : 0.8, spanOf(stateHit.line, stateVal, at));
  } else {
    unresolved.push({ kind: "missing_field", message: "Locality (State/Area) not found." });
    locality = field("", 0, { page: 1, lineStart: 1, lineEnd: 1, charStart: 0, charEnd: 0, rawText: "" });
  }

  // Health & Welfare per-hour rate.
  const hwHit = findLine(lines, new RegExp(`HEALTH\\s*&?\\s*WELFARE:?.*?${MONEY.source}\\s*per\\s*hour`, "i"));
  let healthAndWelfare;
  if (hwHit) {
    const raw = hwHit.m[1];
    const at = hwHit.line.text.indexOf(raw);
    healthAndWelfare = field(parseMoney(raw), 0.97, spanOf(hwHit.line, raw, at));
  } else {
    unresolved.push({ kind: "missing_field", message: "Health & Welfare per-hour rate not found." });
    healthAndWelfare = field(0, 0, { page: 1, lineStart: 1, lineEnd: 1, charStart: 0, charEnd: 0, rawText: "" });
  }

  // Classification rows.
  const classifications: WageClassification[] = [];
  const seenCodes = new Map<string, WageClassification>();
  for (const line of lines) {
    const c = parseClassificationLine(line, unresolved);
    if (!c) continue;
    const code = c.code.value;
    if (seenCodes.has(code)) {
      unresolved.push({
        kind: "duplicate_classification",
        message: `Classification code "${code}" appears more than once; both rows retained for review.`,
        source: c.code.source,
      });
    }
    seenCodes.set(code, c);
    classifications.push(c);
  }
  if (classifications.length === 0) {
    unresolved.push({ kind: "missing_field", message: "No classification rows parsed." });
  }

  return {
    wdNumber,
    revision,
    effectiveDate,
    parity,
    locality,
    healthAndWelfare,
    classifications,
    extractedAt: now ?? new Date().toISOString(),
    reader: { version: READER_VERSION },
    unresolved,
  };
}
