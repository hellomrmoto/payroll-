# Clean Payroll & Ledger

**A decision-authorization layer over federally regulated payroll execution for small federal service contractors.**

It does not replace your payroll system — it *constrains* it, so the enumerated
ways the Department of Labor ends your company (under the McNamara-O'Hara
**Service Contract Act**) become structurally hard to trigger by accident.

> The moat is **correctness and audit-trust**, not UI and not integrations.
> Two competitors can both integrate Gusto. Only one can prove, clause-by-clause,
> that its flag is right. — [PRD §0](docs/PRD.md)

This repository is the Phase-0 foundation: the correctness core is built first,
as a zero-dependency, fully-tested TypeScript engine.

## What's here

```
docs/
  PRD.md                     Canonical product requirements (v1.0, approved)
  WD_Reader_Build_Spec.md    Build spec for the make-or-break extraction engine
prisma/
  schema.prisma              SCA-native core data model (PRD §7)
src/
  wd/                        WD Reader — deterministic, cited, confidence-scored
    schema.ts                Typed output schema (Field<T> with source + confidence)
    ocr.ts                   OCR occupation-code normalization (2-tier correction)
    reader.ts                Text -> WageDeterminationDoc extraction
    directory.ts             Seed SCA Directory of Occupations (replaced by pipeline)
  compliance/
    language.ts              Enforced liability vocabulary (observation, never assertion)
    regulations.ts           Primary-source citation registry (attorney-reviewable)
    engine.ts                Rule engine -> observations/recommendations, cited
  selfperform/
    engine.ts                50% self-perform + ostensible-sub risk model (ranges, not verdicts)
  audit/
    records.ts               29 CFR 4.6(g) record set + certified-payroll CSV
scripts/
  demo.ts                    End-to-end pipeline demo
test/                        33 tests proving the correctness properties
.claude/skills/              The 3 spun-off skills (PRD Appendix B)
```

## Run it

Requires **Node >= 22.6** (native TypeScript type-stripping — no build step, no deps).

```bash
npm test          # 33 tests: OCR, reader, language guard, rule engine, self-perform, audit
npm run demo      # end-to-end: WD text -> reader -> compliance -> self-perform -> audit record
```

## The correctness guarantees (proven by tests)

- **Deterministic extraction** — identical WD text yields a byte-identical document.
- **OCR corruption is handled, not hidden** — `@1311`->`01311`, `e9eee`->`09000`
  (high confidence); `61313`->`01313` (ambiguous, flagged for review). Nothing
  low-confidence is silently trusted.
- **Every field is cited** — each extracted value points back to its source span.
- **Language is enforced** — no finding can contain "compliant", "certified", or
  "you are safe"; a tripwire (`assertLanguageSafe`) blocks it. Findings are
  `observation | recommendation`, **never** a legal conclusion (enforced in the
  data model too — the Prisma `FlagType` enum has no conclusion member).
- **Wage and fringe stay separate** — a missing fringe record is a finding, never
  zero-filled (29 CFR 4.170, liability event #4).
- **Self-perform is a risk model** — outputs ranges + reasoning + counsel-review
  flags, never a single "you're fine" number.

## Status

- WD Reader **text stage** — implemented and tested (`src/wd/`).
- Compliance rule engine, self-perform risk model, audit records — implemented and tested.
- SCA-native data model — `prisma/schema.prisma`.
- WD Reader **PDF/OCR front end** (stages 1–3) — specified in `WD_Reader_Build_Spec.md`, remaining Phase-0 build.
- Next.js app / dashboard, payroll integrations — Phase 1 (PRD §9).

## Important boundaries

This is **not legal advice** and **not a payroll processor**. It surfaces
requirements and cites primary sources; a human signs the Statement of
Compliance under penalty of perjury. Every compliance fact is cited to primary
source in [PRD Appendix C](docs/PRD.md); the rule-to-citation registry
(`src/compliance/regulations.ts`) is designed for review by a licensed SCA
attorney before launch (PRD §10, non-negotiable).
