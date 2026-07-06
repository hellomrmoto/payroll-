import { test } from "node:test";
import assert from "node:assert/strict";
import { assessPeriod, type ContractPeriod } from "../src/selfperform/engine.ts";

test("clear self-perform majority from payroll data -> low risk", () => {
  const period: ContractPeriod = {
    label: "Base",
    costs: [
      { party: "Prime", isPrime: true, cost: 700_000, source: "payroll_invoice" },
      { party: "Sub A", isPrime: false, similarlySituated: false, cost: 300_000, source: "payroll_invoice" },
    ],
  };
  const r = assessPeriod(period);
  assert.equal(r.risk, "low");
  assert.ok(r.selfPerformRatio.point >= 0.5);
  assert.ok(r.selfPerformRatio.low <= r.selfPerformRatio.point);
});

test("below-floor point estimate -> high risk", () => {
  const period: ContractPeriod = {
    label: "Base",
    costs: [
      { party: "Prime", isPrime: true, cost: 300_000, source: "payroll_invoice" },
      { party: "Sub A", isPrime: false, similarlySituated: false, cost: 700_000, source: "payroll_invoice" },
    ],
  };
  const r = assessPeriod(period);
  assert.equal(r.risk, "high");
  assert.ok(r.citations.some((c) => c.key === "FAR_52.219-14"));
});

test("similarly-situated sub counts toward the prime's self-perform side", () => {
  const period: ContractPeriod = {
    label: "Base",
    costs: [
      { party: "Prime", isPrime: true, cost: 300_000, source: "payroll_invoice" },
      { party: "SB Sub", isPrime: false, similarlySituated: true, cost: 400_000, source: "payroll_invoice" },
      { party: "Big Sub", isPrime: false, similarlySituated: false, cost: 300_000, source: "payroll_invoice" },
    ],
  };
  const r = assessPeriod(period);
  // 700k self-perform / 1M total = 70% -> low
  assert.equal(r.selfPerformCost, 700_000);
  assert.equal(r.risk, "low");
});

test("estimate-grade data widens the band and can pull a borderline case to elevated", () => {
  const period: ContractPeriod = {
    label: "Option 1",
    costs: [
      { party: "Prime", isPrime: true, cost: 520_000, source: "estimate" },
      { party: "Sub A", isPrime: false, similarlySituated: false, cost: 480_000, source: "estimate" },
    ],
  };
  const r = assessPeriod(period);
  assert.ok(r.selfPerformRatio.high - r.selfPerformRatio.low > 0.2, "band should be wide for estimates");
  assert.notEqual(r.risk, "low");
  assert.ok(r.dataQuality.some((d) => /ESTIMATE/.test(d)));
});

test("ostensible-sub: primary-and-vital sub raises risk and flags counsel review", () => {
  const period: ContractPeriod = {
    label: "Base",
    costs: [
      { party: "Prime", isPrime: true, cost: 800_000, source: "payroll_invoice" },
      { party: "Vital Sub", isPrime: false, similarlySituated: false, cost: 200_000, source: "payroll_invoice", primaryAndVital: true },
    ],
  };
  const r = assessPeriod(period);
  assert.equal(r.risk, "elevated"); // would be low on ratio alone
  assert.ok(r.reasoning.some((x) => /primary and vital/i.test(x)));
  assert.ok(r.citations.some((c) => c.key === "13_CFR_121.103"));
});

test("output is a range with reasoning, never a single verdict", () => {
  const r = assessPeriod({
    label: "Base",
    costs: [{ party: "Prime", isPrime: true, cost: 100, source: "timecard" }],
  });
  assert.ok("low" in r.selfPerformRatio && "high" in r.selfPerformRatio);
  assert.ok(r.reasoning.length > 0);
});
