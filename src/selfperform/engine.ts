/**
 * 50% self-perform + ostensible-subcontractor risk subsystem.
 *
 * PRD §6: treated as a RISK-MODELING subsystem, not a calculator, because it
 * touches bid viability and adversarial SBA protest exposure. Outputs are
 * ranges and risk levels with stated assumptions — never a single "you're
 * fine" number, and never a compliance verdict.
 *
 * Method (PRD §6):
 *  - The 50% limit under FAR 52.219-14 is measured on the COST OF CONTRACT
 *    PERFORMANCE INCURRED FOR PERSONNEL. We compute the ratio of personnel
 *    cost paid to NON-similarly-situated subs over TOTAL personnel cost, per
 *    period (base + each option separately).
 *  - Data-source hierarchy degrades confidence: payroll+invoices > timecards
 *    > contract estimates (flagged).
 *  - Work by a similarly-situated small-business sub counts toward the prime's
 *    self-perform side.
 *  - Ostensible-sub inference flags "primary and vital" reliance (13 CFR
 *    121.103(h)(4)) as an adversarial risk flag with reasoning, not a verdict.
 */

import { type Citation, cite } from "../compliance/regulations.ts";

/** Fidelity of a personnel-cost figure; drives confidence (PRD §6). */
export type CostSource = "payroll_invoice" | "timecard" | "estimate";

const SOURCE_CONFIDENCE: Record<CostSource, number> = {
  payroll_invoice: 0.95,
  timecard: 0.75,
  estimate: 0.45,
};

/** One party's personnel cost on the contract for a period. */
export interface PersonnelCost {
  party: string;
  /** True for the prime itself. */
  isPrime: boolean;
  /**
   * For subcontractors: whether the sub is "similarly situated" (a
   * small-business sub in the same NAICS size standard). Similarly-situated
   * sub work counts toward the prime's self-perform side. Ignored for prime.
   */
  similarlySituated?: boolean;
  /** Personnel cost in dollars for the period. */
  cost: number;
  source: CostSource;
  /** True when this sub performs "primary and vital" contract work. */
  primaryAndVital?: boolean;
}

/** One measurement window: base term or a specific option period. */
export interface ContractPeriod {
  label: string; // e.g. "Base", "Option 1"
  costs: PersonnelCost[];
}

export type RiskLevel = "low" | "elevated" | "high";

export interface SelfPerformResult {
  period: string;
  /** Self-perform cost = prime + similarly-situated subs. */
  selfPerformCost: number;
  /** Non-similarly-situated sub personnel cost. */
  outsideSubCost: number;
  totalPersonnelCost: number;
  /**
   * Self-perform ratio as a RANGE, widened by the confidence of the underlying
   * data sources (PRD §6, "outputs are ranges ... never a single number").
   */
  selfPerformRatio: { low: number; point: number; high: number };
  /** The FAR 52.219-14 floor for services. */
  requiredFloor: number;
  risk: RiskLevel;
  /** Plain-English reasoning, in non-asserting language. */
  reasoning: string[];
  citations: Citation[];
  /** Data-quality notes (which figures came from low-fidelity sources). */
  dataQuality: string[];
}

const SERVICES_FLOOR = 0.5;

/**
 * Compute the confidence-widened ratio band. The point estimate is the plain
 * ratio; the band widens as source confidence drops, reflecting how much the
 * inputs could move the true ratio.
 */
function ratioBand(
  selfPerform: number,
  total: number,
  minConfidence: number,
): { low: number; point: number; high: number } {
  if (total <= 0) return { low: 0, point: 0, high: 0 };
  const point = selfPerform / total;
  // Uncertainty half-width scales inversely with the weakest source's
  // confidence: perfect data -> ±0; estimate-grade data -> a wide band.
  const halfWidth = (1 - minConfidence) * 0.5;
  return {
    low: Math.max(0, point - halfWidth),
    point,
    high: Math.min(1, point + halfWidth),
  };
}

/** Assess one period's self-perform posture and ostensible-sub exposure. */
export function assessPeriod(period: ContractPeriod): SelfPerformResult {
  const reasoning: string[] = [];
  const dataQuality: string[] = [];

  let selfPerformCost = 0;
  let outsideSubCost = 0;
  let minConfidence = 1;

  for (const c of period.costs) {
    minConfidence = Math.min(minConfidence, SOURCE_CONFIDENCE[c.source]);
    if (c.source === "estimate") {
      dataQuality.push(`${c.party}: figure is a contract ESTIMATE (lowest fidelity) — confidence degraded.`);
    } else if (c.source === "timecard") {
      dataQuality.push(`${c.party}: figure from timecards (medium fidelity).`);
    }
    const countsAsSelf = c.isPrime || c.similarlySituated === true;
    if (countsAsSelf) {
      selfPerformCost += c.cost;
      if (!c.isPrime) {
        reasoning.push(`${c.party} is treated as similarly-situated; its personnel cost counts toward the prime's self-perform side.`);
      }
    } else {
      outsideSubCost += c.cost;
    }
  }

  const total = selfPerformCost + outsideSubCost;
  const band = ratioBand(selfPerformCost, total, minConfidence);

  // Risk classification is based on the *low* end of the band vs. the floor —
  // adversarial framing: assume the worst plausible reading (PRD §6).
  let risk: RiskLevel;
  if (band.low >= SERVICES_FLOOR) {
    risk = "low";
    reasoning.push(`Even at the low end of the estimated range (${pct(band.low)}), self-perform is at or above the ${pct(SERVICES_FLOOR)} floor.`);
  } else if (band.point >= SERVICES_FLOOR) {
    risk = "elevated";
    reasoning.push(`Point estimate (${pct(band.point)}) meets the floor, but the low end of the range (${pct(band.low)}) falls below it — data uncertainty leaves protest exposure.`);
  } else {
    risk = "high";
    reasoning.push(`Point estimate (${pct(band.point)}) is below the ${pct(SERVICES_FLOOR)} self-perform floor for services.`);
  }

  // Ostensible-subcontractor inference (adversarial, non-deterministic).
  const vitalSubs = period.costs.filter((c) => !c.isPrime && c.primaryAndVital);
  for (const v of vitalSubs) {
    reasoning.push(
      `Ostensible-subcontractor risk flagged: ${v.party} appears to perform primary and vital contract work — a trigger for affiliation under 13 CFR 121.103(h)(4). This is an adversarial area; counsel review recommended before bidding.`,
    );
    if (risk === "low") risk = "elevated";
  }
  // Unusual reliance on a single outside sub.
  const biggestOutside = period.costs
    .filter((c) => !c.isPrime && c.similarlySituated !== true)
    .sort((a, b) => b.cost - a.cost)[0];
  if (biggestOutside && total > 0 && biggestOutside.cost / total > 0.4) {
    reasoning.push(
      `Ostensible-subcontractor risk flagged: the prime appears unusually reliant on ${biggestOutside.party} (${pct(biggestOutside.cost / total)} of personnel cost). Counsel review recommended before bidding.`,
    );
    if (risk === "low") risk = "elevated";
  }

  return {
    period: period.label,
    selfPerformCost,
    outsideSubCost,
    totalPersonnelCost: total,
    selfPerformRatio: band,
    requiredFloor: SERVICES_FLOOR,
    risk,
    reasoning,
    citations: [cite("FAR_52.219-14"), cite("13_CFR_121.103")],
    dataQuality,
  };
}

/** Assess every period separately (base + each option), per the clause window. */
export function assessContract(periods: ContractPeriod[]): SelfPerformResult[] {
  return periods.map(assessPeriod);
}

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}
