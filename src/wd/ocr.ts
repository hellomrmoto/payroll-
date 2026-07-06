/**
 * OCR normalization for SCA occupation codes.
 *
 * PRD §4 states the corruption is real and demonstrated in the reference WD:
 *   `01311` OCR'd as `@1311`, `01313` as `61313`, `09000` as `e9eee`.
 *
 * SCA occupation codes are 5-digit numeric codes drawn from the SCA Directory
 * of Occupations. That gives us a dictionary to correct against instead of
 * guessing. The normalizer distinguishes two classes of fix:
 *
 *   1. Unambiguous glyph fixes — a non-digit glyph that can only be a digit
 *      in this context (`@`->`0`, `e`->`0`, `l`->`1`, ...). High confidence.
 *   2. Ambiguous digit-to-digit fixes — a valid digit that was likely a
 *      different digit (`6`->`0`, `1`->`7`). Only applied when it lands the
 *      token on a known Directory code, and always flagged for review.
 *
 * A correction that cannot be resolved to five digits is returned as-is with
 * low confidence and `needsReview` semantics handled by the caller — the
 * engine never silently trusts a token it could not read (PRD §4).
 */

export interface CodeCorrection {
  /** The corrected 5-char code (best effort; may still be non-canonical). */
  value: string;
  /** The original raw token, verbatim. */
  raw: string;
  /** Confidence in [0, 1]. */
  confidence: number;
  /** True when `value` differs from `raw`. */
  corrected: boolean;
  /** True when any ambiguous digit-to-digit swap was needed. */
  ambiguous: boolean;
  /** True when `value` matches a code in the supplied Directory. */
  knownCode: boolean;
}

/**
 * Unambiguous glyph -> digit map. These glyphs are never valid inside a
 * numeric occupation code, so mapping them to a digit does not destroy
 * information. Values chosen from documented OCR confusions.
 */
const GLYPH_TO_DIGIT: Record<string, string> = {
  "@": "0",
  o: "0",
  O: "0",
  e: "0",
  E: "0",
  Q: "0",
  D: "0",
  l: "1",
  I: "1",
  "|": "1",
  Z: "2",
  z: "2",
  A: "4",
  S: "5",
  s: "5",
  G: "6",
  b: "6",
  T: "7",
  B: "8",
  g: "9",
  q: "9",
};

/**
 * Ambiguous digit <-> digit confusions. Each key is a printed digit that is
 * plausibly a misread of the digits in its list. Applied only to reach a
 * known Directory code, and only one swap at a time is preferred.
 */
const DIGIT_CONFUSIONS: Record<string, string[]> = {
  "0": ["6", "8"],
  "6": ["0", "8", "5"],
  "8": ["0", "6"],
  "1": ["7"],
  "7": ["1"],
  "5": ["6", "9"],
  "9": ["5"],
  "2": ["7"],
};

const CODE_LEN = 5;

/** Apply only the unambiguous glyph fixes. Returns the char-fixed token. */
function applyGlyphFixes(raw: string): { fixed: string; changed: number } {
  let changed = 0;
  let fixed = "";
  for (const ch of raw) {
    const repl = GLYPH_TO_DIGIT[ch];
    if (repl !== undefined && repl !== ch) {
      fixed += repl;
      changed++;
    } else {
      fixed += ch;
    }
  }
  return { fixed, changed };
}

/**
 * Enumerate all tokens reachable from `token` by exactly one ambiguous
 * digit-to-digit swap, keeping only those present in `known`.
 */
function knownWithinOneSwap(token: string, known: ReadonlySet<string>): string[] {
  const hits: string[] = [];
  for (let i = 0; i < token.length; i++) {
    const alts = DIGIT_CONFUSIONS[token[i]];
    if (!alts) continue;
    for (const alt of alts) {
      const candidate = token.slice(0, i) + alt + token.slice(i + 1);
      if (known.has(candidate)) hits.push(candidate);
    }
  }
  return hits;
}

/**
 * Normalize a raw OCR'd occupation-code token.
 *
 * @param raw   the token as read from the document
 * @param known the set of valid codes from the SCA Directory of Occupations;
 *              may be empty, in which case only glyph fixes are applied.
 */
export function normalizeOccupationCode(
  raw: string,
  known: ReadonlySet<string> = new Set(),
): CodeCorrection {
  const trimmed = raw.trim();

  // Step 1: unambiguous glyph fixes.
  const { fixed, changed } = applyGlyphFixes(trimmed);
  const allDigits = /^\d+$/.test(fixed);

  // Exact hit after glyph fixes (or no fix needed): highest confidence path.
  if (allDigits && fixed.length === CODE_LEN) {
    const isKnown = known.has(fixed);
    if (isKnown || known.size === 0) {
      // Confidence erodes slightly per glyph fixed but stays high — these
      // fixes are information-preserving.
      const confidence = changed === 0 ? 1 : Math.max(0.9, 1 - 0.02 * changed);
      return {
        value: fixed,
        raw: trimmed,
        confidence: known.size === 0 ? confidence : 1,
        corrected: fixed !== trimmed,
        ambiguous: false,
        knownCode: isKnown,
      };
    }

    // All digits, right length, but not a known code. Try one ambiguous swap
    // to reach a known code.
    const swaps = knownWithinOneSwap(fixed, known);
    if (swaps.length === 1) {
      return {
        value: swaps[0],
        raw: trimmed,
        confidence: 0.6,
        corrected: true,
        ambiguous: true,
        knownCode: true,
      };
    }
    if (swaps.length > 1) {
      // Multiple known codes reachable — genuinely ambiguous. Keep the
      // printed token, low confidence, defer to human.
      return {
        value: fixed,
        raw: trimmed,
        confidence: 0.3,
        corrected: fixed !== trimmed,
        ambiguous: true,
        knownCode: false,
      };
    }
    // Digits but unknown and unreachable — surface as low confidence.
    return {
      value: fixed,
      raw: trimmed,
      confidence: 0.4,
      corrected: fixed !== trimmed,
      ambiguous: false,
      knownCode: false,
    };
  }

  // Step 2: glyph fixes did not yield 5 digits. Best-effort, low confidence.
  return {
    value: fixed,
    raw: trimmed,
    confidence: allDigits ? 0.35 : 0.15,
    corrected: fixed !== trimmed,
    ambiguous: false,
    knownCode: false,
  };
}
