/**
 * Clean Payroll & Ledger — core engine barrel.
 *
 * The "sits-on-top" correctness core (PRD §7). This package is the moat:
 * provable correctness (PRD §2.2). It has zero runtime dependencies and is
 * fully unit-tested so a licensed SCA attorney can review the rule-to-citation
 * mapping directly (PRD §10).
 */

// WD Reader (extraction engine)
export * from "./wd/schema.ts";
export * from "./wd/ocr.ts";
export * from "./wd/directory.ts";
export { readWageDetermination, READER_VERSION } from "./wd/reader.ts";

// Compliance
export * from "./compliance/language.ts";
export * from "./compliance/regulations.ts";
export * from "./compliance/engine.ts";

// 50% self-perform + ostensible-sub risk subsystem
export * from "./selfperform/engine.ts";

// Audit records (29 CFR 4.6(g))
export * from "./audit/records.ts";
