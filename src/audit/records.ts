/**
 * Compliance record generator — 29 CFR 4.6(g) record set.
 *
 * PRD §3.1(7) + Appendix B (`sca-audit-record`): generate the required record
 * set, retained 3 years, audit-ready; produce certified-payroll-format output
 * when an agency requires it, CORRECTLY LABELED as an SCA record (not a
 * Davis-Bacon WH-347 — PRD Appendix C: WH-347 is optional for SCA).
 *
 * Honesty boundary (PRD §5.2): outputs are labeled "advisory / for your
 * review," never "audit-certified." The Statement of Compliance is signed
 * under penalty of perjury by a human (PRD §3.2). Every generated string
 * passes the language guard.
 */

import type { WageDeterminationDoc } from "../wd/schema.ts";
import type { PayrollRecord } from "../compliance/engine.ts";
import { assertLanguageSafe } from "../compliance/language.ts";
import { cite } from "../compliance/regulations.ts";

/** Retention period mandated by 29 CFR 4.6(g)(2), in years. */
export const RETENTION_YEARS = 3;

/** One worker's 29 CFR 4.6(g) record line. */
export interface RecordLine {
  employeeId: string;
  name: string;
  classificationCode: string;
  classificationTitle: string;
  hours: number;
  /** Wage and fringe are stored and shown SEPARATELY (29 CFR 4.170). */
  hourlyBaseWage: number;
  hourlyFringe: number | null;
  grossWagePay: number;
  grossFringePay: number | null;
}

export interface AuditRecordSet {
  header: {
    label: string;
    wdNumber: string;
    revision: number;
    locality: string;
    hwDeterminationRate: number;
    generatedAt: string;
    retainUntilNote: string;
  };
  lines: RecordLine[];
  /** Advisory footer + citations, never an assertion of compliance. */
  footer: {
    disclaimer: string;
    citations: { label: string; url: string }[];
  };
}

/**
 * Build the 29 CFR 4.6(g) record set for a set of payroll records against a WD.
 * Wage and fringe are always carried separately.
 */
export function generateAuditRecordSet(
  wd: WageDeterminationDoc,
  records: PayrollRecord[],
  now?: string,
): AuditRecordSet {
  const generatedAt = now ?? new Date().toISOString();

  const lines: RecordLine[] = records.map((r) => {
    const cls = wd.classifications.find((c) => c.code.value === r.classificationCode);
    return {
      employeeId: r.employeeId,
      name: r.employeeName,
      classificationCode: r.classificationCode,
      classificationTitle: cls?.title.value ?? "(not found in determination)",
      hours: r.hours,
      hourlyBaseWage: r.paidBaseRate,
      hourlyFringe: r.paidFringeRate,
      grossWagePay: round2(r.paidBaseRate * r.hours),
      grossFringePay: r.paidFringeRate === null ? null : round2(r.paidFringeRate * r.hours),
    };
  });

  const disclaimer =
    "Advisory record prepared for your review and for your certification. This is an SCA record set under 29 CFR 4.6(g); " +
    "it is not a WH-347 Davis-Bacon form and is not itself an audit verdict. The Statement of Compliance must be signed by an authorized person.";
  assertLanguageSafe(disclaimer, "audit record disclaimer");

  const retainUntilNote = `Retain for ${RETENTION_YEARS} years from completion of the work (29 CFR 4.6(g)(2)).`;

  return {
    header: {
      label: `SCA Compliance Record (29 CFR 4.6(g)) — prepared for your certification`,
      wdNumber: wd.wdNumber.value,
      revision: wd.revision.value,
      locality: wd.locality.value,
      hwDeterminationRate: wd.healthAndWelfare.value,
      generatedAt,
      retainUntilNote,
    },
    lines,
    footer: {
      disclaimer,
      citations: [cite("29_CFR_4.6g"), cite("29_CFR_4.170"), cite("FAR_52.222-41")].map((c) => ({
        label: c.label,
        url: c.url,
      })),
    },
  };
}

/**
 * Render the record set as certified-payroll-format CSV, correctly labeled as
 * an SCA record. Wage and fringe columns are kept separate (29 CFR 4.170).
 */
export function toCertifiedPayrollCsv(set: AuditRecordSet): string {
  const title = `SCA COMPLIANCE RECORD (29 CFR 4.6(g)) - ADVISORY - PREPARED FOR YOUR CERTIFICATION`;
  assertLanguageSafe(title, "csv title");
  const meta = `WD ${set.header.wdNumber} rev. ${set.header.revision} | ${set.header.locality} | Determination H&W ${set.header.hwDeterminationRate.toFixed(2)}/hr`;
  const header = [
    "Employee ID",
    "Name",
    "Class Code",
    "Class Title",
    "Hours",
    "Hourly Base Wage",
    "Hourly Fringe (separate)",
    "Gross Wage Pay",
    "Gross Fringe Pay",
  ].join(",");
  const rows = set.lines.map((l) =>
    [
      l.employeeId,
      csvEscape(l.name),
      l.classificationCode,
      csvEscape(l.classificationTitle),
      l.hours,
      l.hourlyBaseWage.toFixed(2),
      l.hourlyFringe === null ? "MISSING-SEPARATE-RECORD" : l.hourlyFringe.toFixed(2),
      l.grossWagePay.toFixed(2),
      l.grossFringePay === null ? "MISSING-SEPARATE-RECORD" : l.grossFringePay.toFixed(2),
    ].join(","),
  );
  return [`# ${title}`, `# ${meta}`, `# ${set.header.retainUntilNote}`, header, ...rows].join("\n");
}

function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

function csvEscape(s: string): string {
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
