import { test } from "node:test";
import assert from "node:assert/strict";
import {
  findLanguageViolations,
  isLanguageSafe,
  assertLanguageSafe,
} from "../src/compliance/language.ts";

// PRD §5.1 — banned assertion vocabulary must be caught.
test("banned: 'compliant' / 'non-compliant'", () => {
  assert.ok(!isLanguageSafe("You are compliant."));
  assert.ok(!isLanguageSafe("This worker is non-compliant."));
});

test("banned: 'you are safe' / 'this is legal' / 'certified'", () => {
  assert.ok(!isLanguageSafe("You are safe."));
  assert.ok(!isLanguageSafe("This is legal."));
  assert.ok(!isLanguageSafe("Your payroll is certified."));
});

test("required observation language passes", () => {
  assert.ok(isLanguageSafe("Mismatch detected against WD 2015-5657 rev. 24."));
  assert.ok(isLanguageSafe("No mismatch found against WD 2015-5657 rev. 24."));
  assert.ok(isLanguageSafe("Risk flagged: review recommended."));
  assert.ok(isLanguageSafe("Prepared for your certification."));
});

test("'compliance' as a noun is allowed (not an assertion)", () => {
  assert.ok(isLanguageSafe("This is your SCA compliance record for your review."));
});

test("assertLanguageSafe throws with actionable guidance", () => {
  assert.throws(
    () => assertLanguageSafe("You are compliant.", "test copy"),
    /Banned assertion vocabulary in test copy/,
  );
});

test("violations report position and replacement", () => {
  const v = findLanguageViolations("All good — you are safe now.");
  assert.equal(v.length, 1);
  assert.equal(v[0].banned, "you are safe");
  assert.match(v[0].useInstead, /No mismatch found/);
});
