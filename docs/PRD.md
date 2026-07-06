# Clean Payroll and Ledger — Product Requirements Document

**Version:** 1.0
**Date:** July 6, 2026
**Status:** Approved for Phase 0 build
**One line:** A decision-authorization layer over federally regulated payroll execution for small service contractors. It does not replace your payroll system — it constrains it, so the six ways the Department of Labor ends your company become structurally impossible to do by accident.

---

## 0. Framing (read before anything else)

This is not "compliance SaaS." Compliance SaaS optimizes for documentation and loses. This targets **liability events**: debarment triggers, wage misclassification, fringe misallocation, option-year failures. It is failure-prevention logic for regulated payroll execution.

The strategic truth, and it dictates every decision below: **the moat is correctness and audit-trust, not UI and not integrations.** Two competitors can both integrate Gusto. Only one can prove, clause-by-clause, that its flag is right. That provability is the entire company. Every requirement in this document serves it.

Every compliance claim in this document is cited to primary source (DOL / eCFR / FAR) in Appendix C. In this category a wrong fact is not a bug — it is a customer getting debarred and suing us. Facts are verified, not remembered.

---

## 1. The problem (verified)

Small federal **service** contractors — janitorial, grounds, security, food service, maintenance — operate under the **McNamara-O'Hara Service Contract Act (SCA)**, which applies to any federal service contract over $2,500. It forces them to pay a government-dictated wage PLUS a separate per-hour Health & Welfare (H&W) fringe, by job classification, by county, per the wage determination incorporated into the contract.

**Penalties for getting it wrong** (verified, Appendix C): withheld contract payments, contract termination, back wages with interest, **3-year debarment from ALL federal contracts**, and **personal liability** — the individual controlling performance can be personally liable and personally debarred. The LLC does not shield the human.

**Enforcement is not rare.** DOL found violations in **68% of SCA cases** FY2014–2019, recovered ~**$224M** in back wages, debarred **60 contractors**. Most small contractors in this space are non-compliant and don't know it.

**The eight liability events the product exists to prevent** (DOL's enumerated list plus set-aside exposure):
1. Misclassifying a worker into the wrong wage classification
2. Treating a covered worker as exempt when they aren't
3. Late payment of wages or H&W contributions
4. Cash-fringe payments with no separate records
5. Failing to post the WH-1313 worksite notice / notify workers
6. Not implementing a new wage determination's rate increase at option year
7. Not segregating contract vs. non-contract hours for split workers
8. Blowing the 50% self-perform limit (FAR 52.219-14) or tripping the ostensible-subcontractor rule — losing the award on a size protest

**The buyer:** owner-operator or office manager of a small federal service contractor running 1–10 contracts, no compliance officer, no in-house counsel, doing this in a spreadsheet at 11pm. Fear-driven, not efficiency-driven. Highly liability-averse. Non-technical.

---

## 2. The wedge — empirically confirmed, not asserted

### 2.1 The market discontinuity

Every incumbent is **Davis-Bacon-first** (construction prevailing wage). SCA is a bolt-on. See the teardown in Appendix A for the evidence, not the assertion.

| Vendor | Built for | SCA posture | Go-to-market | Small-contractor fit |
|---|---|---|---|---|
| SkillSmart InSight IQ | Construction / MWBE diversity tracking on large capital projects | Blog-post bolt-on; flagship output is WH-347 (a construction form) | "Request a demo," enterprise sales, no public pricing | Poor — sells to owners/developers & diversity directors |
| eBacon | Construction certified payroll / Davis-Bacon | Secondary | Demo-gated | Poor |
| LCPTracker | Construction prevailing wage, agency-mandated portal | Secondary | Enterprise | Poor |
| Points North / EMARS / Miter | Construction / payroll add-ons | Secondary | Enterprise / partner-led | Poor |

**The confirmed whitespace:** nobody has built the **SCA-native, self-serve, small-service-contractor** product. The incumbents cannot easily come down-market without cannibalizing their enterprise motion and rebuilding their Davis-Bacon-centric data model around SCA's genuinely different mechanics (per-hour H&W fringe, odd vs. even-numbered determinations, cash-equivalent fringe rules, 4(c) CBA successorship, the SCA Directory of Occupations).

### 2.2 The three moats
1. **SCA-native data model.** Built for the Service Contract Act's real rules, not Davis-Bacon's retrofitted.
2. **Self-serve down-market.** A janitorial owner signs up and uploads a wage determination without a sales call. Structurally hard for incumbents to match.
3. **Provable correctness (the real moat).** Every flag drills to the clause. Every calculation exports for an accountant. This is Section 5 and it is the company.

### 2.3 "Swing wide" — architected wide, landed narrow
Data model and rule engine are built SCA-wide from day one (all service categories). Go-to-market beachhead is janitorial/custodial: highest volume, lowest complexity, and the category the founder can personally run to generate real-world test data. Wide architecture, focused first marketing.

---

## 3. Scope

### 3.1 v1 IS
1. **Contract vault** — per contract: wage determination, revision number, option-year dates, contract value, agency, place-of-performance county, applicable clauses (52.219-14, 52.222-41, 52.222-43).
2. **WD Reader** — the extraction engine. Its own build spec (`WD_Reader_Build_Spec.md`). See Section 4.
3. **Worker classification mapper** — assign each employee to an SCA classification against the SCA Directory of Occupations; flag mismatches. Attacks events #1, #2.
4. **Rate + fringe calculator** — per worker, correct base wage + separately-recorded H&W fringe; flags below-rate. Forces separate wage/fringe records, attacking #3, #4.
5. **WD-increase + option-year watchdog** — tracks annual H&W adjustment (verified: $5.36 → $5.55 eff. July 7, 2025) and option-year anniversaries; alerts before an option period; surfaces FAR 52.222-43 price-adjustment entitlement so the increase is recovered from the government. Attacks #6.
6. **50% self-perform + ostensible-sub risk subsystem** — see Section 6. Attacks #8.
7. **Compliance record generator** — the 29 CFR 4.6(g) record set, retained 3 years, audit-ready; generates certified-payroll-format output when an agency requires it, correctly labeled as an SCA record.
8. **WH-1313 worksite-notice generator** — pre-filled poster. Kills #5.
9. **The mismatch dashboard** — one screen per contract, status: all workers at/above rate; fringe current; option year requiring WD refresh; records complete; 50% line position. Language per Section 5.

### 3.2 v1 IS NOT (protect the build)
- **NOT a payroll processor.** No tax withholding, no 941s, no check-cutting. Sits on top of Gusto/QuickBooks/ADP/Paychex.
- **NOT a bid-finder / SAM.gov search.** Rejected front-end bloodbath.
- **NOT Davis-Bacon construction.** Incumbents' turf. Roadmap adjacency only.
- **NOT auto-certifying payroll.** The Statement of Compliance is signed under penalty of perjury by a human.
- **NOT legal advice.** Surfaces requirements, cites sources; does not adjudicate compliance.

---

## 4. The WD Reader (summary — full spec in `WD_Reader_Build_Spec.md`)

This is the make-or-break system. It is specified as a **formally verifiable extraction engine**, not a feature. Summary of the requirements that make it trustworthy:

- **Deterministic output schema** — every wage determination maps to a fixed, typed JSON structure (WD number, revision, effective date, odd/even type, locality, per-classification code/title/base-rate, H&W rate, vacation/holiday terms).
- **Confidence scoring** — every extracted field carries a confidence value. The OCR corruption is real and demonstrated: in the reference WD, `01311` OCR'd as `@1311`, `01313` as `61313`, `09000` as `e9eee`. Low-confidence fields are surfaced for human confirmation, never silently trusted.
- **Citation traceability** — every extracted number links back to its source location (page + text span / bounding box) in the original PDF, so a skeptical user can see exactly where the tool read it.
- **Conflict resolution** — defined behavior for two classifications mapping to one role, missing rates, ambiguous locality.
- **Failure modes** — explicit: what the engine does when it cannot read a field, rather than guessing.

**Honesty boundary:** this document specifies the engine. The engine is a build, not a paragraph. The reference-WD parsing done during this project is a proof the corruption is real, not a finished parser.

---

## 5. Liability language + trust bootstrapping (the moat, made operational)

### 5.1 Language is legal classification, not cosmetics
The UI **never** asserts compliance. Enforced vocabulary:

| Banned (assertion — transfers legal responsibility to us) | Required (observation — leaves responsibility with contractor) |
|---|---|
| "Compliant" / "Non-compliant" | "Mismatch detected" / "Within determination" |
| "You are safe" | "No mismatch found against WD 2015-5657 rev. X" |
| "This is legal" | "Risk flagged: review recommended" |
| "Certified" | "Prepared for your certification" |

**System recommendation vs. system assertion:** the product makes *observations* ("paid rate $16.00 is below determination rate $17.56 for classification 11150 Janitor") and *recommendations* ("review recommended"). It never makes *assertions of legal status*. This distinction is enforced in copy, in exports, and in the data model (every flag record carries a `type: observation | recommendation`, never `type: legal_conclusion`).

### 5.2 Trust bootstrapping
1. **Clause-level drill-down on every flag.** Every mismatch shows "Show me why" → the exact WD classification/rate it was measured against + the citation to the source span in the PDF + the governing regulation (e.g., 29 CFR 4.170 for separate fringe).
2. **Reproducible, exportable calculations.** One click produces a PDF an accountant or SCA attorney can independently verify: inputs, the determination applied, the math, the source citations.
3. **Audit-evidence positioning.** Outputs are labeled "advisory / for your review," not "audit-certified."

---

## 6. 50% self-perform + ostensible-subcontractor risk subsystem

Treated as a **risk-modeling subsystem, not a calculator**, because it is the most legally dangerous surface.

- **Personnel-cost methodology:** the 50% limit under FAR 52.219-14 is measured on the **cost of contract performance incurred for personnel**. The subsystem computes the ratio of (personnel cost paid to non-similarly-situated subcontractors) to (total personnel cost), across the base term and each option period separately.
- **Data-source hierarchy:** actual payroll + sub-invoices (highest fidelity) → timecards → contract estimates (lowest, flagged as estimate).
- **Similarly-situated handling:** work performed by a similarly-situated small-business sub counts toward the prime's self-perform side.
- **Ostensible-subcontractor inference:** flags when a sub is performing the "primary and vital" work of the contract or when the prime appears unusually reliant on one sub — the two triggers for affiliation under 13 CFR 121.103(h)(4). Outputs a *risk flag with reasoning*, explicitly not a compliance verdict.
- **Uncertainty handling:** outputs are ranges and risk-levels with stated assumptions, never a single "you're fine" number.

---

## 7. Architecture (sits-on-top)

- **Frontend:** Next.js + TypeScript.
- **Backend/DB:** PostgreSQL + Prisma. Supabase recommended for v1 speed.
- **Payroll integration:** read-only pulls from Gusto/QuickBooks/ADP via API or CSV. CSV import is the always-works fallback.
- **AI layer:** document-parsing model for WD extraction (OCR + structured output + confidence); LLM for classification-mapping suggestions and plain-English explanation. Human confirmation on every AI output.
- **WD data pipeline:** ingest from SAM.gov WD library + DOL All Agency Memoranda. This pipeline's maintenance IS the ongoing product value.
- **Auth/roles:** owner, admin, bookkeeper (read-only). Design for SOC 2; not v1.

**Core data model:**
`Contract` → `WageDetermination` → `Classification` → `Employee` → `WorkerAssignment` → `Timecard` (contract-segregated) → `PayrollRecord` (wage + fringe stored SEPARATELY) → `ComplianceCheck` (type: observation|recommendation) → `AuditLog` (immutable).

See `prisma/schema.prisma` for the implemented model.

---

## 8. Pricing
- Fear-priced, not spreadsheet-priced. Published, self-serve.
- **$99–$199 / active contract / month**, tiered by contract count. Free tier: 1 contract, read-only dashboard.

---

## 9. Roadmap

**Phase 0 — Validation (weeks 1–3). Kill-gate.** Build the WD Reader to production-grade per its spec. Dogfood on founder's own janitorial contract data. Put it in front of 5–10 real small service contractors. No Phase 1 until this gate passes.

**Phase 1 — MVP (weeks 4–12).** Contract vault + WD reader + classification mapper + rate/fringe calculator + mismatch dashboard + one payroll integration.

**Phase 2 — Watchdogs (months 4–6).** WD-increase/option-year watchdog + FAR 52.222-43 surfacing + 50%/ostensible-sub subsystem + WH-1313 + full 4.6(g) audit export.

**Phase 3 — Widen (months 6–12).** Classification libraries beyond janitorial. More payroll integrations. SOC 2 Type II.

**Phase 4 — Adjacent (12+ months, only if earned).** Davis-Bacon construction. Bid-side tooling as upsell.

---

## 10. Risks (raw)

- **Funded incumbents.** Mitigation: never fight on construction turf; own the SCA small-contractor niche.
- **Compliance-fact risk.** One wrong rule = a debarred customer + lawsuit. Mitigation: every rule cited to primary source (Appendix C); a licensed SCA attorney reviews the rule engine before launch. Non-negotiable.
- **Integration dependency.** Payroll APIs change. Mitigation: CSV fallback.
- **Regulatory drift.** H&W changes annually. Mitigation: the WD-data pipeline must be actively maintained.
- **Founder-pattern risk.** Documented history of strong builds that stall pre-revenue. Mitigation: Phase 0 is a hard 3-week kill-gate tied to real contractors reaching for cards.

---

## Appendix B — Skills spun off from this PRD
Delivered as working SKILL.md artifacts under `.claude/skills/`:
1. **`sca-wd-extract`** — the WD extraction discipline: schema, confidence rules, citation traceability, failure handling.
2. **`sca-compliance-check`** — the rule engine: given a WD + payroll record, produce observations/recommendations (never legal conclusions), each cited to regulation.
3. **`sca-audit-record`** — generate the 29 CFR 4.6(g) record set + certified-payroll-format output, correctly labeled.

## Appendix C — Compliance facts, cited to primary source
- SCA applies to federal service contracts > $2,500; prevailing wage + fringe by classification/locality per incorporated WD. *(DOL Fact Sheet #67; 29 CFR §4.6)*
- H&W is separate from and in addition to base wage; cannot be satisfied by a higher wage; recorded separately. *(DOL Fact Sheet #67B; 29 CFR §4.170)*
- Current H&W: **$5.55/hr eff. July 7, 2025** (from $5.36); EO 13706 contracts $5.09. *(DOL WHD; PilieroMazza, Nov 2025)*
- Penalties: withheld payments, termination, back wages + interest, **3-year debarment**, **personal liability for controlling individuals**. *(DOL Fact Sheet #67; SCA FAQ; 29 CFR)*
- Enforcement: 68% violation rate FY2014–19; ~$224M back wages; 60 debarments. *(USFCR citing DOL)*
- Recordkeeping: **29 CFR §4.6(g)**, retained **3 years** from completion. *(DOL SCA Compliance Principles)*
- WD-increase applies at anniversary/option period after the Contracting Officer incorporates it by modification; price adjustment likely under **FAR 52.222-43**. *(PilieroMazza; DOL)*
- 50% self-perform on services set-asides, measured on personnel cost, base + each option period. *(FAR 52.219-14, acquisition.gov + eCFR)*
- Ostensible-subcontractor rule: sub performing "primary and vital" work or prime unusually reliant → affiliation → possible loss of set-aside on protest. *(13 CFR 121.103(h)(4); SBA precedent)*
- WH-347 is a Davis-Bacon/Copeland construction form, **OPTIONAL for SCA** unless the agency requires it. *(DOL; eBacon/SkillSmart compliance guides)*
- WH-1313 "Notice to Employees Working on Government Contracts" must be posted at the worksite. *(DOL Fact Sheet #67)*
