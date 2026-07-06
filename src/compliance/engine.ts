/**
 * SCA compliance rule engine.
 *
 * PRD §5 + Appendix B (`sca-compliance-check`): given a wage determination and
 * a payroll record, produce OBSERVATIONS and RECOMMENDATIONS — each cited to
 * primary source — and NEVER a legal conclusion. The output vocabulary is the
 * enforced language of PRD §5.1; every emitted string is run through the
 * language guard so a banned assertion can never escape.
 *
 * Each check attacks one of the enumerated liability events (PRD §1):
 *   #1/#2 classification mismatch, #3 below-rate wage / late,
 *   #4 fringe not separately recorded, below-H&W fringe.
 *
 * The engine is deterministic and dependency-free.
 */

import type { WageDeterminationDoc } from "../wd/schema.ts";
import { type FlagType, assertLanguageSafe } from "./language.ts";
import { type CitationKey, cite, type Citation } from "./regulations.ts";

/** A worker's pay for one classification over a pay period. */
export interface PayrollRecord {
  employeeId: string;
  employeeName: string;
  /** The classification code the worker was paid under. */
  classificationCode: string;
  /** Hours worked on this contract in the period. */
  hours: number;
  /** Hourly base wage actually paid, in dollars. */
  paidBaseRate: number;
  /**
   * Hourly Health & Welfare fringe recorded SEPARATELY from wage, in dollars.
   * `null` means no separate fringe record exists — itself a finding
   * (PRD event #4; 29 CFR 4.170 separate-record requirement).
   */
  paidFringeRate: number | null;
  /** Pay date, ISO. */
  payDate?: string;
}

/** The liability event a finding maps to (PRD §1 enumeration). */
export type LiabilityEvent =
  | "misclassification"
  | "below_wage"
  | "below_fringe"
  | "fringe_not_separate"
  | "within_determination";

/** A single machine-checkable finding. Never a legal conclusion. */
export interface ComplianceCheck {
  /** PRD §5.1: enforced to `observation | recommendation`, never conclusion. */
  type: FlagType;
  event: LiabilityEvent;
  employeeId: string;
  /** The observation text, in enforced non-asserting language. */
  message: string;
  /** Primary-source citations backing the finding (PRD §5.2 drill-down). */
  citations: Citation[];
  /** Structured detail for exports / accountant verification (PRD §5.2). */
  detail?: Record<string, string | number | null>;
  /** Severity ordering hint for the dashboard; not a legal ranking. */
  severity: "info" | "review";
}

function makeCheck(
  type: FlagType,
  event: LiabilityEvent,
  employeeId: string,
  message: string,
  citationKeys: CitationKey[],
  severity: "info" | "review",
  detail?: Record<string, string | number | null>,
): ComplianceCheck {
  // Tripwire: no emitted finding may contain banned assertion vocabulary.
  assertLanguageSafe(message, `compliance finding (${event})`);
  return { type, event, employeeId, message, citations: citationKeys.map(cite), severity, detail };
}

/** Money formatting for finding text: always two decimals with a $. */
function usd(n: number): string {
  return `$${n.toFixed(2)}`;
}

/**
 * Run every rule for one payroll record against the determination.
 * Returns the findings in a stable order (most actionable first).
 */
export function checkPayrollRecord(
  wd: WageDeterminationDoc,
  rec: PayrollRecord,
): ComplianceCheck[] {
  const out: ComplianceCheck[] = [];
  const wdLabel = `WD ${wd.wdNumber.value} rev. ${wd.revision.value}`;

  // Locate the classification in the determination.
  const cls = wd.classifications.find((c) => c.code.value === rec.classificationCode);

  // --- Event #1/#2: classification not present in the determination ---
  if (!cls) {
    out.push(
      makeCheck(
        "observation",
        "misclassification",
        rec.employeeId,
        `Classification code ${rec.classificationCode} for ${rec.employeeName} was not found in ${wdLabel}. ` +
          `The paid classification does not match any classification in the determination.`,
        ["29_CFR_4.6", "DOL_FS_67"],
        "review",
        { classificationCode: rec.classificationCode, wd: wdLabel },
      ),
    );
    out.push(
      makeCheck(
        "recommendation",
        "misclassification",
        rec.employeeId,
        `Review recommended: confirm ${rec.employeeName}'s SCA occupation code against the SCA Directory of Occupations and the classifications listed in ${wdLabel}.`,
        ["29_CFR_4.6"],
        "review",
      ),
    );
    return out; // Without a matched classification, rate/fringe checks cannot run.
  }

  const detRate = cls.baseRate.value;
  const detTitle = cls.title.value;
  const hwRate = wd.healthAndWelfare.value;

  // --- Event #3: base wage below the determination rate ---
  if (rec.paidBaseRate + 1e-9 < detRate) {
    const shortfall = detRate - rec.paidBaseRate;
    out.push(
      makeCheck(
        "observation",
        "below_wage",
        rec.employeeId,
        `Paid base rate ${usd(rec.paidBaseRate)} is below the determination rate ${usd(detRate)} for ` +
          `classification ${rec.classificationCode} ${detTitle} in ${wdLabel} (short by ${usd(shortfall)}/hr).`,
        ["29_CFR_4.6", "FAR_52.222-41"],
        "review",
        {
          classificationCode: rec.classificationCode,
          title: detTitle,
          paidBaseRate: rec.paidBaseRate,
          determinationRate: detRate,
          shortfallPerHour: Number(shortfall.toFixed(2)),
          hours: rec.hours,
        },
      ),
    );
    out.push(
      makeCheck(
        "recommendation",
        "below_wage",
        rec.employeeId,
        `Review recommended: the recorded base wage is below the rate in ${wdLabel} for this classification.`,
        ["FAR_52.222-41"],
        "review",
      ),
    );
  } else {
    out.push(
      makeCheck(
        "observation",
        "within_determination",
        rec.employeeId,
        `Paid base rate ${usd(rec.paidBaseRate)} is at or above the determination rate ${usd(detRate)} for ` +
          `classification ${rec.classificationCode} ${detTitle}. No mismatch found against ${wdLabel}.`,
        ["29_CFR_4.6"],
        "info",
        { paidBaseRate: rec.paidBaseRate, determinationRate: detRate },
      ),
    );
  }

  // --- Event #4: fringe not recorded separately ---
  if (rec.paidFringeRate === null) {
    out.push(
      makeCheck(
        "observation",
        "fringe_not_separate",
        rec.employeeId,
        `No separate Health & Welfare fringe record was found for ${rec.employeeName}. Health & Welfare ` +
          `is separate from and in addition to the base wage and must be recorded separately; a higher wage does not satisfy it.`,
        ["29_CFR_4.170", "29_CFR_4.177"],
        "review",
        { determinationHWRate: hwRate },
      ),
    );
    out.push(
      makeCheck(
        "recommendation",
        "fringe_not_separate",
        rec.employeeId,
        `Review recommended: record the Health & Welfare fringe separately from the base wage for this worker.`,
        ["29_CFR_4.170"],
        "review",
      ),
    );
  } else if (rec.paidFringeRate + 1e-9 < hwRate) {
    // Below-H&W fringe.
    const shortfall = hwRate - rec.paidFringeRate;
    out.push(
      makeCheck(
        "observation",
        "below_fringe",
        rec.employeeId,
        `Recorded Health & Welfare fringe ${usd(rec.paidFringeRate)}/hr is below the determination H&W rate ` +
          `${usd(hwRate)}/hr in ${wdLabel} (short by ${usd(shortfall)}/hr).`,
        ["29_CFR_4.170", "DOL_FS_67B"],
        "review",
        {
          paidFringeRate: rec.paidFringeRate,
          determinationHWRate: hwRate,
          shortfallPerHour: Number(shortfall.toFixed(2)),
          hours: rec.hours,
        },
      ),
    );
  } else {
    out.push(
      makeCheck(
        "observation",
        "within_determination",
        rec.employeeId,
        `Recorded Health & Welfare fringe ${usd(rec.paidFringeRate)}/hr is at or above the determination H&W ` +
          `rate ${usd(hwRate)}/hr. No mismatch found against ${wdLabel}.`,
        ["29_CFR_4.170"],
        "info",
        { paidFringeRate: rec.paidFringeRate, determinationHWRate: hwRate },
      ),
    );
  }

  // Stable ordering: review-severity findings first, then info.
  return out.sort((a, b) => severityRank(a) - severityRank(b));
}

function severityRank(c: ComplianceCheck): number {
  return c.severity === "review" ? 0 : 1;
}
