/**
 * Primary-source citation registry.
 *
 * PRD Risk §10: "One wrong rule = a debarred customer + lawsuit." Every flag
 * the engine emits must drill to a primary source (PRD §5.2). This module is
 * the single place those citations live, so a licensed SCA attorney can
 * review the rule-to-citation mapping in one file (PRD §10 mitigation).
 *
 * Facts are verified, not remembered (PRD §0). Each entry corresponds to a
 * cited fact in PRD Appendix C.
 */

export interface Citation {
  /** Stable key referenced by the rule engine. */
  key: string;
  /** Human-readable citation label, e.g. "29 CFR § 4.170". */
  label: string;
  /** What this authority establishes, in one line. */
  says: string;
  /** Canonical URL to the primary source. */
  url: string;
}

export const CITATIONS = {
  /** SCA applicability, incorporated WD, > $2,500 threshold. */
  "29_CFR_4.6": {
    key: "29_CFR_4.6",
    label: "29 CFR § 4.6",
    says: "SCA contract clauses; the incorporated wage determination sets minimum wage + fringe by classification and locality.",
    url: "https://www.ecfr.gov/current/title-29/subtitle-A/part-4/subpart-A/section-4.6",
  },
  /** Recordkeeping set, retained 3 years. */
  "29_CFR_4.6g": {
    key: "29_CFR_4.6g",
    label: "29 CFR § 4.6(g)",
    says: "Required records for each covered worker, retained 3 years from completion of the work.",
    url: "https://www.ecfr.gov/current/title-29/subtitle-A/part-4/subpart-A/section-4.6#p-4.6(g)",
  },
  /** H&W is separate from and additional to base wage; recorded separately. */
  "29_CFR_4.170": {
    key: "29_CFR_4.170",
    label: "29 CFR § 4.170",
    says: "Health & Welfare fringe is separate from and in addition to the base wage and must be recorded separately; a higher wage does not satisfy it.",
    url: "https://www.ecfr.gov/current/title-29/subtitle-A/part-4/subpart-C/section-4.170",
  },
  /** Discharge of fringe obligations, cash equivalents. */
  "29_CFR_4.177": {
    key: "29_CFR_4.177",
    label: "29 CFR § 4.177",
    says: "How fringe benefit obligations are discharged, including cash-equivalent payments and the separate-record requirement.",
    url: "https://www.ecfr.gov/current/title-29/subtitle-A/part-4/subpart-C/section-4.177",
  },
  /** SCA contract clause. */
  "FAR_52.222-41": {
    key: "FAR_52.222-41",
    label: "FAR 52.222-41",
    says: "Service Contract Labor Standards clause incorporated into covered contracts.",
    url: "https://www.acquisition.gov/far/52.222-41",
  },
  /** Price adjustment on WD revision. */
  "FAR_52.222-43": {
    key: "FAR_52.222-43",
    label: "FAR 52.222-43",
    says: "Fair Labor Standards Act and Service Contract Labor Standards — Price Adjustment (Multiple Year and Option Contracts): entitles the contractor to recover wage/fringe increases from a newly incorporated determination.",
    url: "https://www.acquisition.gov/far/52.222-43",
  },
  /** 50% self-perform limitation on services set-asides. */
  "FAR_52.219-14": {
    key: "FAR_52.219-14",
    label: "FAR 52.219-14",
    says: "Limitations on Subcontracting: for services, the prime must self-perform at least 50% of the cost of contract performance incurred for personnel, measured over the base term and each option period.",
    url: "https://www.acquisition.gov/far/52.219-14",
  },
  /** Ostensible-subcontractor / affiliation rule. */
  "13_CFR_121.103": {
    key: "13_CFR_121.103",
    label: "13 CFR § 121.103(h)(4)",
    says: "Ostensible-subcontractor rule: a subcontractor performing the primary and vital requirements, or on which the prime is unusually reliant, is treated as an affiliate — risking loss of a set-aside on size protest.",
    url: "https://www.ecfr.gov/current/title-13/chapter-I/part-121/subpart-A/section-121.103#p-121.103(h)(4)",
  },
  /** DOL Fact Sheet 67 — SCA overview and penalties. */
  DOL_FS_67: {
    key: "DOL_FS_67",
    label: "DOL WHD Fact Sheet #67",
    says: "SCA overview: coverage over $2,500, penalties include withheld payments, termination, back wages + interest, 3-year debarment, and personal liability for controlling individuals; WH-1313 worksite notice required.",
    url: "https://www.dol.gov/agencies/whd/fact-sheets/67-mcnamara-service-contract-act",
  },
  /** DOL Fact Sheet 67B — Health & Welfare. */
  DOL_FS_67B: {
    key: "DOL_FS_67B",
    label: "DOL WHD Fact Sheet #67B",
    says: "SCA Health & Welfare benefits: current rate $5.55/hr effective July 7, 2025 (from $5.36); EO 13706 contracts $5.09.",
    url: "https://www.dol.gov/agencies/whd/fact-sheets/67b-sca-health-welfare",
  },
} as const satisfies Record<string, Citation>;

export type CitationKey = keyof typeof CITATIONS;

/** Look up a citation by key, throwing if the key is unknown (fail loud). */
export function cite(key: CitationKey): Citation {
  const c = CITATIONS[key];
  if (!c) throw new Error(`Unknown citation key: ${key}`);
  return c;
}
