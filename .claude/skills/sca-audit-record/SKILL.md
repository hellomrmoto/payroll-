---
name: sca-audit-record
description: The SCA audit-record generation discipline. Use when producing the 29 CFR 4.6(g) record set or certified-payroll-format output for a Service Contract Act contract — enforcing separate wage/fringe records, 3-year retention labeling, correct SCA (not WH-347 Davis-Bacon) labeling, and advisory/non-verdict positioning. Triggers on "audit record", "29 CFR 4.6(g)", "certified payroll export", "SCA recordkeeping", "wage and fringe separate records", "retain 3 years".
---

# sca-audit-record — Audit-record generation discipline

Spun off from `Clean Payroll and Ledger` PRD §3.1(7) and §5.2.
Implementation: `src/audit/records.ts`.

## Non-negotiable rules

1. **Wage and fringe are stored and shown SEPARATELY** (29 CFR 4.170). Fringe
   is never merged into wage. A missing separate fringe stays `null` /
   `MISSING-SEPARATE-RECORD` — never zero-filled. This is the whole point of
   liability event #4.

2. **Correct labeling: SCA record, not WH-347.** WH-347 is a Davis-Bacon /
   Copeland *construction* form and is OPTIONAL for SCA (PRD Appendix C). Every
   generated record set is labeled as a "29 CFR 4.6(g)" SCA record. Producing
   certified-payroll-*format* output is fine; calling it a WH-347 or implying
   it satisfies Davis-Bacon is not.

3. **Advisory positioning — never a verdict.** Outputs carry the disclaimer:
   "prepared for your review and for your certification … not itself an audit
   verdict. The Statement of Compliance must be signed by an authorized
   person." The system does not auto-certify (PRD §3.2). Every generated
   string passes `assertLanguageSafe()` — no "certified", no "compliant".

4. **3-year retention labeling.** Records carry "Retain for 3 years from
   completion of the work (29 CFR 4.6(g)(2))."

5. **Citations attached.** The footer cites 29 CFR 4.6(g), 29 CFR 4.170, and
   FAR 52.222-41, drawn from `src/compliance/regulations.ts`.

## Workflow

1. Have a `WageDeterminationDoc` and the period's `PayrollRecord`s.
2. `generateAuditRecordSet(wd, records)` → structured record set.
3. `toCertifiedPayrollCsv(set)` → labeled CSV when an agency requires
   certified-payroll format.
4. Present as advisory evidence the contractor reviews and certifies — support
   for an audit, not a legal verdict (PRD §5.2).

## Do NOT

- Do not label output "certified" or "audit-certified".
- Do not zero-fill a missing fringe record.
- Do not present the output as a WH-347 or as satisfying Davis-Bacon.
- Do not sign or auto-generate the Statement of Compliance — a human signs it.
