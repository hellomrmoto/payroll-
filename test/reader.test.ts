import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { readWageDetermination } from "../src/wd/reader.ts";

const fixture = readFileSync(
  fileURLToPath(new URL("../fixtures/wd-2015-5657.txt", import.meta.url)),
  "utf8",
);

const FIXED_NOW = "2026-07-06T00:00:00.000Z";

test("extracts header fields with citations", () => {
  const wd = readWageDetermination(fixture, FIXED_NOW);
  assert.equal(wd.wdNumber.value, "2015-5657");
  assert.equal(wd.revision.value, 24);
  assert.equal(wd.effectiveDate.value, "2025-07-07");
  assert.equal(wd.healthAndWelfare.value, 5.55);
  assert.match(wd.locality.value, /Virginia/);
  // Citation traceability: every field points at a real source line.
  assert.ok(wd.wdNumber.source.lineStart > 0);
  assert.equal(wd.wdNumber.source.rawText, "2015-5657");
});

test("parses all classification rows and OCR-corrects the codes", () => {
  const wd = readWageDetermination(fixture, FIXED_NOW);
  const byCode = new Map(wd.classifications.map((c) => [c.code.value, c]));
  assert.ok(byCode.has("01311"), "corrected @1311");
  assert.ok(byCode.has("01313"), "corrected 61313");
  assert.ok(byCode.has("09000"), "corrected e9eee");
  assert.ok(byCode.has("11150"), "clean Janitor");

  const janitor = byCode.get("11150")!;
  assert.equal(janitor.title.value, "Janitor");
  assert.equal(janitor.baseRate.value, 17.56);
});

test("OCR-corrected fields are flagged in unresolved for human review", () => {
  const wd = readWageDetermination(fixture, FIXED_NOW);
  const kinds = wd.unresolved.map((u) => u.kind);
  assert.ok(kinds.includes("ocr_corrected") || kinds.includes("ambiguous_correction"));
  // The ambiguous 61313 -> 01313 fix must be surfaced specifically.
  assert.ok(
    wd.unresolved.some((u) => u.kind === "ambiguous_correction"),
    "ambiguous correction must be surfaced",
  );
});

test("citation spans point at the right raw text for a rate", () => {
  const wd = readWageDetermination(fixture, FIXED_NOW);
  const janitor = wd.classifications.find((c) => c.code.value === "11150")!;
  assert.equal(janitor.baseRate.source.rawText, "17.56");
});

test("deterministic: identical text yields identical doc (with fixed clock)", () => {
  const a = readWageDetermination(fixture, FIXED_NOW);
  const b = readWageDetermination(fixture, FIXED_NOW);
  assert.deepEqual(a, b);
});

test("missing fields are surfaced as issues, not guessed", () => {
  const wd = readWageDetermination("nothing useful here\n", FIXED_NOW);
  assert.equal(wd.wdNumber.value, "");
  assert.equal(wd.wdNumber.confidence, 0);
  assert.ok(wd.unresolved.some((u) => u.kind === "missing_field"));
});
