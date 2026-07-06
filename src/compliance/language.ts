/**
 * Liability-language enforcement.
 *
 * PRD §5.1: "Language is legal classification, not cosmetics." The product
 * NEVER asserts compliance. Assertions transfer legal responsibility to us;
 * observations and recommendations leave it with the contractor. This module
 * makes that boundary mechanical: any user-facing string produced by the
 * system can be guarded, and every flag is typed `observation | recommendation`
 * — never `legal_conclusion`.
 */

/** The two flag types the system is permitted to emit. Never a conclusion. */
export type FlagType = "observation" | "recommendation";

/**
 * Banned assertion vocabulary from PRD §5.1, expressed as case-insensitive
 * patterns. Each carries the required observation/recommendation phrasing to
 * use instead, so violations are actionable rather than merely blocked.
 */
interface BannedTerm {
  pattern: RegExp;
  banned: string;
  useInstead: string;
}

export const BANNED_TERMS: readonly BannedTerm[] = [
  {
    pattern: /\bnon-?compliant\b/i,
    banned: "non-compliant",
    useInstead: '"Mismatch detected"',
  },
  {
    // "compliant" but not the allowed compound "non-compliant" handling above;
    // also avoid matching "compliance" (a permitted noun, e.g. "for your
    // certification"/"compliance record").
    pattern: /\bcompliant\b/i,
    banned: "compliant",
    useInstead: '"Within determination"',
  },
  {
    pattern: /\byou(?:'re| are)\s+safe\b/i,
    banned: "you are safe",
    useInstead: '"No mismatch found against WD <number> rev. <n>"',
  },
  {
    pattern: /\bthis is legal\b/i,
    banned: "this is legal",
    useInstead: '"Risk flagged: review recommended"',
  },
  {
    pattern: /\bcertified\b/i,
    banned: "certified",
    useInstead: '"Prepared for your certification"',
  },
  {
    pattern: /\blegal(?:ly)?\s+(?:compliant|safe|clear|fine)\b/i,
    banned: "legally compliant / legally safe",
    useInstead: '"Risk flagged: review recommended"',
  },
] as const;

export interface LanguageViolation {
  banned: string;
  useInstead: string;
  /** Character index where the banned term begins. */
  index: number;
  /** The exact substring that matched. */
  match: string;
}

/**
 * Scan a user-facing string for banned assertion vocabulary. Returns every
 * violation found (empty array == safe). Deterministic and dependency-free so
 * it can run in copy tests, export generation, and CI alike.
 */
export function findLanguageViolations(text: string): LanguageViolation[] {
  const out: LanguageViolation[] = [];
  for (const term of BANNED_TERMS) {
    // Fresh regex per scan to avoid lastIndex state on the shared literal.
    const re = new RegExp(term.pattern.source, term.pattern.flags.includes("g") ? term.pattern.flags : term.pattern.flags + "g");
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      out.push({
        banned: term.banned,
        useInstead: term.useInstead,
        index: m.index,
        match: m[0],
      });
      if (m.index === re.lastIndex) re.lastIndex++; // guard zero-width
    }
  }
  return out.sort((a, b) => a.index - b.index);
}

/** True when the string contains no banned assertion vocabulary. */
export function isLanguageSafe(text: string): boolean {
  return findLanguageViolations(text).length === 0;
}

/**
 * Assert a string is safe to show a user or write to an export. Throws with a
 * precise message on the first violation. Use this as a tripwire around any
 * generated copy so a banned assertion can never reach a contractor.
 */
export function assertLanguageSafe(text: string, context = "output"): void {
  const violations = findLanguageViolations(text);
  if (violations.length === 0) return;
  const v = violations[0];
  throw new Error(
    `Banned assertion vocabulary in ${context}: "${v.match}" (banned: ${v.banned}). ` +
      `Use ${v.useInstead} instead. This system makes observations and recommendations, never legal conclusions (PRD §5.1).`,
  );
}
