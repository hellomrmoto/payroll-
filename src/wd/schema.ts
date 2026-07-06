/**
 * Deterministic, typed output schema for the WD Reader.
 *
 * PRD §4: "every wage determination maps to a fixed, typed JSON structure."
 * Every extracted value is wrapped in a `Field<T>` that carries its own
 * confidence, its source location in the original document (citation
 * traceability), and whether it required OCR correction or human review.
 *
 * Nothing in this module guesses. A value the engine could not read is
 * represented explicitly (confidence 0, needsReview true) rather than
 * silently defaulted — PRD §4 "Failure modes".
 */

/** Confidence in an extracted value, in the closed interval [0, 1]. */
export type Confidence = number;

/**
 * A pointer back into the source document so a skeptical, non-technical
 * contractor can see exactly where the tool read a number (PRD §4,
 * "Citation traceability"). Line/char offsets are 1-indexed and inclusive
 * of `lineStart`, exclusive of `charEnd`.
 */
export interface SourceSpan {
  /** 1-indexed page in the source PDF/text. */
  page: number;
  /** 1-indexed first line of the span. */
  lineStart: number;
  /** 1-indexed last line of the span (== lineStart for single-line spans). */
  lineEnd: number;
  /** 0-indexed character offset of the span within `lineStart`. */
  charStart: number;
  /** 0-indexed character offset one past the end of the span. */
  charEnd: number;
  /** The exact raw text the value was read from, verbatim. */
  rawText: string;
}

/**
 * A single extracted value plus everything needed to trust or distrust it.
 * `T` is the parsed, typed value (number, string, enum, ...).
 */
export interface Field<T> {
  value: T;
  confidence: Confidence;
  /** Where in the source this came from. */
  source: SourceSpan;
  /**
   * True when the raw token was altered by the OCR normalizer (e.g. the
   * reference-WD corruption `@1311` -> `01311`). `raw` holds the original.
   */
  corrected: boolean;
  /** The original token before any correction, when `corrected` is true. */
  raw?: string;
  /**
   * True when confidence fell below the review threshold and the value must
   * be confirmed by a human before it is trusted (PRD §4: low-confidence
   * fields "surfaced for human confirmation, never silently trusted").
   */
  needsReview: boolean;
}

/** One wage classification row from the determination. */
export interface WageClassification {
  /** SCA occupation code, e.g. "11150". */
  code: Field<string>;
  /** Occupation title, e.g. "Janitor". */
  title: Field<string>;
  /** Hourly base wage rate in dollars. */
  baseRate: Field<number>;
}

/** How an extraction issue was categorized. */
export type ExtractionIssueKind =
  | "missing_field"
  | "low_confidence"
  | "ocr_corrected"
  | "ambiguous_correction"
  | "duplicate_classification"
  | "unparseable_line";

/**
 * An explicit record of something the engine could not fully resolve.
 * Surfacing these (rather than guessing) is the honesty boundary in PRD §4.
 */
export interface ExtractionIssue {
  kind: ExtractionIssueKind;
  message: string;
  source?: SourceSpan;
}

/**
 * The full deterministic output of a WD extraction. Identical input always
 * produces an identical structure (PRD §4, "Deterministic output schema").
 */
export interface WageDeterminationDoc {
  /** e.g. "2015-5657". */
  wdNumber: Field<string>;
  revision: Field<number>;
  /** ISO-8601 date (YYYY-MM-DD). */
  effectiveDate: Field<string>;
  /** Odd- vs. even-numbered determination (SCA-specific mechanic). */
  parity: Field<"odd" | "even">;
  /** Place-of-performance locality string as printed on the WD. */
  locality: Field<string>;
  /** Per-hour Health & Welfare fringe rate in dollars. */
  healthAndWelfare: Field<number>;
  classifications: WageClassification[];
  /** ISO timestamp the extraction was produced. */
  extractedAt: string;
  reader: { version: string };
  /** Everything the engine could not fully resolve, for human review. */
  unresolved: ExtractionIssue[];
}

/** Confidence at or above this is trusted without mandatory human review. */
export const REVIEW_THRESHOLD = 0.85 as const;

/** Construct a `Field`, deriving `needsReview` from the review threshold. */
export function field<T>(
  value: T,
  confidence: Confidence,
  source: SourceSpan,
  opts: { corrected?: boolean; raw?: string } = {},
): Field<T> {
  const c = clampConfidence(confidence);
  return {
    value,
    confidence: c,
    source,
    corrected: opts.corrected ?? false,
    raw: opts.raw,
    needsReview: c < REVIEW_THRESHOLD,
  };
}

/** Clamp any number into the confidence interval [0, 1]. */
export function clampConfidence(c: number): Confidence {
  if (Number.isNaN(c)) return 0;
  if (c < 0) return 0;
  if (c > 1) return 1;
  return c;
}
