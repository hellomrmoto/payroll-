---
name: sca-compliance-check
description: The SCA compliance rule engine discipline. Use when comparing payroll against a Service Contract Act wage determination to flag issues — enforcing that every output is an OBSERVATION or RECOMMENDATION (never a legal conclusion), is written in the enforced non-asserting vocabulary, and is cited to primary source. Triggers on "compliance check", "below-rate wage", "H&W fringe not recorded separately", "SCA misclassification", "flag payroll against WD", "observation vs assertion".
---

# sca-compliance-check — Compliance rule-engine discipline

Spun off from `Clean Payroll and Ledger` PRD §5. The rule engine is the
company (PRD §2.2 moat #3). Implementation: `src/compliance/`
(`engine.ts`, `language.ts`, `regulations.ts`).

## Non-negotiable rules

1. **Observations and recommendations only — never a legal conclusion.**
   Every finding is `type: "observation" | "recommendation"`. There is no
   `legal_conclusion` type, in code or in the DB (the Prisma `FlagType` enum
   deliberately omits it). The system observes and recommends; a human
   adjudicates.

2. **Enforced vocabulary (PRD §5.1).** BANNED assertion words —
   *compliant / non-compliant / you are safe / this is legal / certified*.
   REQUIRED observation words — *mismatch detected / within determination /
   no mismatch found against WD … / risk flagged: review recommended /
   prepared for your certification*. Every emitted string MUST pass
   `assertLanguageSafe()` (`src/compliance/language.ts`). This is a tripwire
   in `makeCheck()`; do not bypass it.

3. **Every finding is cited to primary source.** Pull citations from
   `src/compliance/regulations.ts` (single reviewable registry). No finding
   ships without at least one `Citation`. A licensed SCA attorney reviews this
   registry before launch (PRD §10).

4. **Observations are specific and reproducible.** State the paid figure, the
   determination figure, the classification, and the WD/revision — e.g.
   "Paid base rate $16.00 is below the determination rate $17.56 for
   classification 11150 Janitor in WD 2015-5657 rev. 24". An accountant must
   be able to re-derive it (PRD §5.2).

## The checks (mapped to PRD §1 liability events)

| Check | Event | Core citation |
|---|---|---|
| Classification not in WD | #1/#2 misclassification | 29 CFR 4.6; FS #67 |
| Paid base < determination rate | #3 below wage | 29 CFR 4.6; FAR 52.222-41 |
| No separate fringe record | #4 fringe not separate | 29 CFR 4.170; 4.177 |
| Fringe < WD H&W rate | below fringe | 29 CFR 4.170; FS #67B |
| At/above rate & fringe | within determination | 29 CFR 4.6 / 4.170 |

## Workflow

1. Have a `WageDeterminationDoc` (from `sca-wd-extract`) and `PayrollRecord`s.
2. Call `checkPayrollRecord(wd, record)` per record.
3. Present findings with the "Show me why" drill-down: message + cited
   regulation + the WD span the number was measured against.

## Do NOT

- Do not write "compliant", "certified", or "you are safe" anywhere.
- Do not emit a finding without a citation.
- Do not coerce a missing fringe to 0 — a null fringe IS the finding (event #4).
