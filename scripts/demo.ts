/**
 * End-to-end demo: WD text -> reader -> compliance engine -> audit record.
 *
 * Run with:  node scripts/demo.ts   (Node >= 22.6, native TS type-stripping)
 *
 * This is the "sits-on-top" pipeline in miniature (PRD §7) and doubles as a
 * smoke test that the modules connect. It prints observations/recommendations
 * in the enforced non-asserting language (PRD §5.1) with primary-source
 * citations (PRD §5.2).
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { readWageDetermination } from "../src/wd/reader.ts";
import { checkPayrollRecord, type PayrollRecord } from "../src/compliance/engine.ts";
import { assessPeriod } from "../src/selfperform/engine.ts";
import { generateAuditRecordSet, toCertifiedPayrollCsv } from "../src/audit/records.ts";

const text = readFileSync(
  fileURLToPath(new URL("../fixtures/wd-2015-5657.txt", import.meta.url)),
  "utf8",
);

const wd = readWageDetermination(text);

console.log("=".repeat(78));
console.log("WD READER — extraction");
console.log("=".repeat(78));
console.log(`WD ${wd.wdNumber.value} rev. ${wd.revision.value}  (${wd.parity.value}-numbered, conf ${wd.parity.confidence})`);
console.log(`Effective ${wd.effectiveDate.value} | ${wd.locality.value}`);
console.log(`Health & Welfare: $${wd.healthAndWelfare.value.toFixed(2)}/hr`);
console.log("\nClassifications (code shown with OCR provenance):");
for (const c of wd.classifications) {
  const flag = c.code.corrected ? `  [OCR ${c.code.raw} -> ${c.code.value}, conf ${c.code.confidence.toFixed(2)}${c.code.needsReview ? ", REVIEW" : ""}]` : "";
  console.log(`  ${c.code.value}  ${c.title.value.padEnd(32)} $${c.baseRate.value.toFixed(2)}${flag}`);
}
console.log(`\nUnresolved items surfaced for human review: ${wd.unresolved.length}`);
for (const u of wd.unresolved) console.log(`  - [${u.kind}] ${u.message}`);

console.log("\n" + "=".repeat(78));
console.log("COMPLIANCE ENGINE — observations & recommendations (never conclusions)");
console.log("=".repeat(78));

const payroll: PayrollRecord[] = [
  { employeeId: "E1", employeeName: "Pat Doe", classificationCode: "11150", hours: 80, paidBaseRate: 16.0, paidFringeRate: 5.55 },
  { employeeId: "E2", employeeName: "Sam Lee", classificationCode: "11150", hours: 80, paidBaseRate: 17.56, paidFringeRate: null },
  { employeeId: "E3", employeeName: "Jo Kim", classificationCode: "99999", hours: 40, paidBaseRate: 20.0, paidFringeRate: 6.0 },
];

for (const rec of payroll) {
  console.log(`\n${rec.employeeName} (class ${rec.classificationCode}):`);
  for (const chk of checkPayrollRecord(wd, rec)) {
    const tag = chk.type === "observation" ? "OBSERVATION" : "RECOMMENDATION";
    console.log(`  [${tag}] ${chk.message}`);
    console.log(`     ↳ ${chk.citations.map((c) => c.label).join("; ")}`);
  }
}

console.log("\n" + "=".repeat(78));
console.log("50% SELF-PERFORM — risk model (ranges, not verdicts)");
console.log("=".repeat(78));
const sp = assessPeriod({
  label: "Base",
  costs: [
    { party: "Prime", isPrime: true, cost: 520_000, source: "estimate" },
    { party: "Sub A", isPrime: false, similarlySituated: false, cost: 480_000, source: "estimate", primaryAndVital: true },
  ],
});
console.log(`Period ${sp.period}: self-perform ratio ${(sp.selfPerformRatio.low * 100).toFixed(1)}%–${(sp.selfPerformRatio.high * 100).toFixed(1)}% (point ${(sp.selfPerformRatio.point * 100).toFixed(1)}%), floor ${(sp.requiredFloor * 100).toFixed(0)}% -> RISK: ${sp.risk.toUpperCase()}`);
for (const r of sp.reasoning) console.log(`  - ${r}`);

console.log("\n" + "=".repeat(78));
console.log("AUDIT RECORD — 29 CFR 4.6(g), advisory, SCA-labeled");
console.log("=".repeat(78));
const set = generateAuditRecordSet(wd, payroll.slice(0, 2));
console.log(toCertifiedPayrollCsv(set));
console.log(`\n${set.footer.disclaimer}`);
