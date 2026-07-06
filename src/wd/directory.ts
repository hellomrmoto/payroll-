/**
 * SEED subset of the SCA Directory of Occupations.
 *
 * ⚠️ NON-AUTHORITATIVE. This is a small starter set so the OCR normalizer and
 * classification mapper have a dictionary to work against in development and
 * tests. The production system ingests the full Directory from the SAM.gov WD
 * library / DOL pipeline (PRD §7, "WD data pipeline ... maintenance IS the
 * ongoing product value"). Do NOT treat titles here as legally authoritative;
 * they exist to exercise the engine. Codes are the SCA 5-digit occupation
 * codes; titles are provided only where well established.
 *
 * The canonical Directory lives at:
 *   https://www.dol.gov/agencies/whd/government-contracts/service-contracts/directory-occupations
 */

/** Map of SCA occupation code -> title (seed subset only). */
export const DIRECTORY_SEED: Readonly<Record<string, string>> = {
  // 01000 series — Administrative Support and Clerical Occupations
  "01311": "Accounting Clerk I",
  "01312": "Accounting Clerk II",
  "01313": "Accounting Clerk III",
  // 09000 — category header code used in WD layouts
  "09000": "Food Preparation and Service Occupations",
  // 11000 series — General Services and Support Occupations (janitorial beachhead)
  "11150": "Janitor",
  "11210": "Laborer, Grounds Maintenance",
  "11240": "Maid or Houseman",
  "11260": "Pest Controller",
  "11270": "Refuse Collector",
  "11300": "Window Cleaner",
};

/** The set of valid codes, for the OCR normalizer's dictionary lookups. */
export const DIRECTORY_CODES: ReadonlySet<string> = new Set(Object.keys(DIRECTORY_SEED));

/** Look up a canonical title for a code, or undefined if not in the seed. */
export function directoryTitle(code: string): string | undefined {
  return DIRECTORY_SEED[code];
}
