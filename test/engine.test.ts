import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { readWageDetermination } from "../src/wd/reader.ts";
import { checkPayrollRecord, type PayrollRecord } from "../src/compliance/engine.ts";
import { isLanguageSafe } from "../src/compliance/language.ts";

const wd = readWageDetermination(
  readFileSync(fileURLToPath(new URL("../fixtures/wd-2015-5657.txt", import.meta.url)), "utf8"),
  "2026-07-06T00:00:00.000Z",
);

// Janitor determination rate is 17.56 base; WD H&W is 5.55.
function rec(overrides: Partial<PayrollRecord> = {}): PayrollRecord {
  return {
    employeeId: "E1",
    employeeName: "Pat Doe",
    classificationCode: "11150",
    hours: 80,
    paidBaseRate: 18.0,
    paidFringeRate: 5.55,
    ...overrides,
  };
}

test("below-rate wage -> observation + recommendation, cited, event #3", () => {
  const checks = checkPayrollRecord(wd, rec({ paidBaseRate: 16.0 }));
  const below = checks.find((c) => c.event === "below_wage" && c.type === "observation");
  assert.ok(below, "expected below_wage observation");
  assert.match(below!.message, /below the determination rate \$17\.56/);
  assert.equal(below!.detail?.shortfallPerHour, 1.56);
  assert.ok(below!.citations.some((c) => c.key === "FAR_52.222-41"));
  assert.ok(checks.some((c) => c.event === "below_wage" && c.type === "recommendation"));
});

test("missing separate fringe -> event #4 observation citing 29 CFR 4.170", () => {
  const checks = checkPayrollRecord(wd, rec({ paidFringeRate: null }));
  const f = checks.find((c) => c.event === "fringe_not_separate" && c.type === "observation");
  assert.ok(f);
  assert.ok(f!.citations.some((c) => c.key === "29_CFR_4.170"));
});

test("below-H&W fringe -> below_fringe observation", () => {
  const checks = checkPayrollRecord(wd, rec({ paidFringeRate: 5.0 }));
  const f = checks.find((c) => c.event === "below_fringe");
  assert.ok(f);
  assert.match(f!.message, /below the determination H&W rate \$5\.55/);
});

test("unknown classification -> misclassification, no rate checks run", () => {
  const checks = checkPayrollRecord(wd, rec({ classificationCode: "99999" }));
  assert.ok(checks.some((c) => c.event === "misclassification"));
  assert.ok(!checks.some((c) => c.event === "below_wage"));
});

test("at/above rate + fringe -> only 'within_determination' observations", () => {
  const checks = checkPayrollRecord(wd, rec({ paidBaseRate: 18.0, paidFringeRate: 6.0 }));
  assert.ok(checks.every((c) => c.event === "within_determination"));
  assert.ok(checks.every((c) => c.type === "observation"));
});

test("no finding ever contains banned assertion language, and none is a conclusion", () => {
  for (const scenario of [
    rec({ paidBaseRate: 10 }),
    rec({ paidFringeRate: null }),
    rec({ classificationCode: "99999" }),
    rec(),
  ]) {
    for (const c of checkPayrollRecord(wd, scenario)) {
      assert.ok(isLanguageSafe(c.message), `unsafe language: ${c.message}`);
      assert.ok(c.type === "observation" || c.type === "recommendation");
      assert.ok(c.citations.length > 0, "every finding must be cited");
    }
  }
});
