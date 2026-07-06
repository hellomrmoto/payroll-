import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { readWageDetermination } from "../src/wd/reader.ts";
import { generateAuditRecordSet, toCertifiedPayrollCsv, RETENTION_YEARS } from "../src/audit/records.ts";
import { type PayrollRecord } from "../src/compliance/engine.ts";
import { isLanguageSafe } from "../src/compliance/language.ts";

const wd = readWageDetermination(
  readFileSync(fileURLToPath(new URL("../fixtures/wd-2015-5657.txt", import.meta.url)), "utf8"),
  "2026-07-06T00:00:00.000Z",
);

const records: PayrollRecord[] = [
  { employeeId: "E1", employeeName: "Pat Doe", classificationCode: "11150", hours: 80, paidBaseRate: 18.0, paidFringeRate: 5.55 },
  { employeeId: "E2", employeeName: "Sam Lee", classificationCode: "11150", hours: 80, paidBaseRate: 17.56, paidFringeRate: null },
];

test("record set keeps wage and fringe separate (29 CFR 4.170)", () => {
  const set = generateAuditRecordSet(wd, records, "2026-07-06T00:00:00.000Z");
  const e1 = set.lines[0];
  assert.equal(e1.hourlyBaseWage, 18.0);
  assert.equal(e1.hourlyFringe, 5.55);
  assert.equal(e1.grossWagePay, 1440.0);
  assert.equal(e1.grossFringePay, 444.0);
  // Missing separate fringe stays null, not zero-filled.
  assert.equal(set.lines[1].hourlyFringe, null);
});

test("record set is labeled advisory / SCA (not WH-347), 3-year retention, cited", () => {
  const set = generateAuditRecordSet(wd, records, "2026-07-06T00:00:00.000Z");
  assert.match(set.footer.disclaimer, /not a WH-347/);
  assert.match(set.header.retainUntilNote, new RegExp(`${RETENTION_YEARS} years`));
  assert.ok(set.footer.citations.some((c) => /4\.6\(g\)/.test(c.label)));
  assert.ok(isLanguageSafe(set.header.label));
  assert.ok(isLanguageSafe(set.footer.disclaimer));
});

test("CSV export is labeled and flags missing separate fringe records", () => {
  const set = generateAuditRecordSet(wd, records, "2026-07-06T00:00:00.000Z");
  const csv = toCertifiedPayrollCsv(set);
  assert.match(csv, /SCA COMPLIANCE RECORD/);
  assert.match(csv, /MISSING-SEPARATE-RECORD/);
  assert.ok(isLanguageSafe(csv));
});
