import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizeOccupationCode } from "../src/wd/ocr.ts";
import { DIRECTORY_CODES } from "../src/wd/directory.ts";

// The three demonstrated corruptions from PRD §4.
test("PRD §4: @1311 -> 01311 (unambiguous glyph fix, high confidence)", () => {
  const r = normalizeOccupationCode("@1311", DIRECTORY_CODES);
  assert.equal(r.value, "01311");
  assert.equal(r.corrected, true);
  assert.equal(r.knownCode, true);
  assert.ok(r.confidence >= 0.9, `confidence ${r.confidence}`);
  assert.equal(r.ambiguous, false);
});

test("PRD §4: e9eee -> 09000 (all-glyph fix)", () => {
  const r = normalizeOccupationCode("e9eee", DIRECTORY_CODES);
  assert.equal(r.value, "09000");
  assert.equal(r.corrected, true);
  assert.equal(r.knownCode, true);
});

test("PRD §4: 61313 -> 01313 (ambiguous digit swap, flagged, lower confidence)", () => {
  const r = normalizeOccupationCode("61313", DIRECTORY_CODES);
  assert.equal(r.value, "01313");
  assert.equal(r.corrected, true);
  assert.equal(r.ambiguous, true);
  assert.equal(r.knownCode, true);
  assert.ok(r.confidence < 0.85, `ambiguous fix should need review, got ${r.confidence}`);
});

test("clean code passes through at full confidence", () => {
  const r = normalizeOccupationCode("11150", DIRECTORY_CODES);
  assert.equal(r.value, "11150");
  assert.equal(r.corrected, false);
  assert.equal(r.confidence, 1);
});

test("unresolvable token stays low-confidence, not silently trusted", () => {
  const r = normalizeOccupationCode("xx", DIRECTORY_CODES);
  assert.ok(r.confidence < 0.5);
  assert.equal(r.knownCode, false);
});

test("deterministic: same input yields identical output", () => {
  const a = normalizeOccupationCode("@1311", DIRECTORY_CODES);
  const b = normalizeOccupationCode("@1311", DIRECTORY_CODES);
  assert.deepEqual(a, b);
});
