# Synthetic BHPH ledger foundation

## Scope and requirements before implementation

This first slice is an explicitly synthetic accounting rehearsal, not a loan account, migration authority, contract, customer receipt, allocation engine or servicing implementation. It links an existing same-dealership customer to a demo book with opening-balance provenance. It never converts draft worksheet amounts into a loan.

Controls planned for this slice: exact integer cents; structurally balanced debit/credit pairs; append-only postings; immutable account identity/provenance; actor, reason/reference, effective date and entry time; explicit version; idempotent keys; serialized concurrent posting/reversal; only linked full receipt reversals; independent reconciliation. No interest/accrual/APR/fees, principal allocation, deferred down treatment, payoff, delinquency, provider processing, collection or credit decision behavior is enabled. Synthetic manual receipts go entirely to an unapplied bucket; they do not reduce principal or prove settlement. A reversal is an accounting correction, not an actual refund.

## Source and applicability register

Primary sources checked October 24, 2026:

- Florida Legislature, 2026 compilation, [520.07](https://www.leg.state.fl.us/Statutes/index.cfm?App_mode=Display_Statute&URL=0500-0599/0520/Sections/0520.07.html): retail installment contract/disclosure requirements. Do not use an internal opening balance or journal as a compliant contract or amount-financed disclosure. Transaction-specific applicability and effective-date/session-law verification remain for legal review; no contract rule is activated here.
- CFPB [12 CFR 1026.18](https://www.consumerfinance.gov/rules-policy/regulations/1026/18/): closed-end disclosure content. No APR, payment schedule or finance-charge disclosure is calculated by this ledger rehearsal. Applicable disclosure/calculation versions and effective dates remain unresolved for live origination; live behavior stays disabled.
- CFPB [12 CFR 1026.25](https://www.consumerfinance.gov/rules-policy/regulations/1026/25/): record-retention framework. Implement no automatic deletion; category-specific retention/holds and applicability review remain outstanding. Do not translate it into a universal retention period.
- [16 CFR 314.4](https://www.ecfr.gov/current/title-16/chapter-I/subchapter-C/part-314/section-314.4): information-security controls. The source displayed Title 16 current through October 22, 2026; that is not an effective date for each provision. Keep real data disabled pending security/MFA/encryption/recovery review; dealership scoping and audited posting are engineering controls, not a compliance certification.

Mortgage-specific 1026.36 and credit-card allocation rules are not assumed to govern independent-dealer auto installments. Allocation/servicing law and contractual methods need their own primary-source and professional review before implementation. No legal receipt language or statutory deadline is invented in this slice.

## Accounting reference cases

USD demo only. Opening $10,000.25 creates debit principal $10,000.25 and credit opening offset $10,000.25. A synthetic manual receipt of $125.50 adds debit cash control $125.50 and credit unapplied $125.50. A second receipt of $74.50 gives cash control/unapplied $200.00; principal remains $10,000.25. Reversing the first receipt adds the exact opposite $125.50 pair: cash control/unapplied become $74.50; principal remains $10,000.25. Total journal debits and credits are each $10,325.75 including the reversal. These fixed values are independently stated test cases, not values derived inside tests using the implementation's calculation function.

A book with no receipt must not show payments, paid principal or a settlement claim. Same-key concurrent retries must create one posting. Two distinct-key attempts to reverse one receipt must leave one linked reversal. All live/production routes and mutation services fail closed outside the explicit development gate. Provider callbacks and payment execution are absent.

## Implemented accounting design

`finance.DemoBook` links a canonical same-dealership customer and opening provenance; it is not a contract or a copy of a customer. Each `DemoPosting` is one structurally balanced pair: the same positive integer-cent amount has exactly one permitted debit and one permitted credit. Database constraints allow only opening principal/offset, receipt cash-control/unapplied, and receipt reversal unapplied/cash-control. USD is explicit. No split allocation or actual external funds are modeled.

Creation and posting services require the development gate and owner/staff membership. UUID keys are validated and checked against the original facts; retries cannot create new postings. Opening locks the dealership; receipts/reversals lock the book. A unique original-reversal relation prevents two corrections of the same receipt. Current opening and receipt dates are bounded to the synthetic rehearsal interval; this is an engineering scope restriction, not a legal deadline. A reversal's effective date cannot precede the original.

Database UPDATE/DELETE triggers protect book identity/provenance and posted entries on PostgreSQL and SQLite. PostgreSQL additionally checks cross-record customer/actor scope, effective opening dates and exact same-book receipt reversal amounts on INSERT. Application routes expose no ordinary edit/delete for posted money. These guards are not tamper-proof storage: a privileged operator can alter/drop triggers, TRUNCATE tables or restore data. Test database flush uses TRUNCATE on PostgreSQL. The SQLite fallback does not supply the PostgreSQL cross-record insert guarantees or row-lock concurrency behavior.

The reconciliation uses one aggregate statement and reports bucket balances, debit/credit totals and exactly one opening entry. The account page holds the same book lock as posting services while assembling the aggregate and journal page, so a concurrent posting cannot appear in only one half of the view. All balances are derived from postings, not an editable cached balance column.

## Evaluation interface

`/ledger-demo/` is an isolated development area. It supports existing synthetic-customer selection, explicit opening amount/source, synthetic manual receipts, exact linked full corrections and paginated append-only journal inspection. Read-only members may inspect same-dealership books; only owner/staff may prepare/confirm postings. Every mutation uses a signed 30-minute actor/dealership-bound preview, explicit synthetic-data acknowledgement, and a posting-key retry check. The preview states debit/credit effects and distinguishes unapplied cash control from principal reduction or bank settlement. Editing before posting preserves input; invalid/expired previews do not post. Corrections preserve the original and explain that they are not refunds.

No automatic promotion from a draft deal, live payment provider, real receipt artifact, allocation, interest, fee, delinquency, statement, collections or loan origination exists. The gate follows DEBUG and fails closed outside the development setting at both routes and mutation services. This is community MPL code, not a paid financial-integrity feature. The demo is linked from development documentation rather than presented as production BHPH servicing in everyday navigation.

## Verification and remaining gates

The finance suite passed 21 PostgreSQL tests covering exact cents, invalid/nonfinite/fractional values, fixed independent reference figures, idempotent openings/receipts, correction retries/double-reversal rejection, provenance/effective dates, actor/dealership boundaries, disabled gates, append-only writes/deletes, balanced-pair constraints, rollback, signed preview/edit/CSRF/read roles and three real concurrency races. Direct PostgreSQL insertion of an incorrect reversal amount is rejected. Full DMS PostgreSQL suite: 237 tests, no skips. SQLite finance fallback: 21 tests with four PostgreSQL-only checks skipped; the final journal-read refinement passed the complete 21-test finance suite again on PostgreSQL (no skips).

The browser reference case confirms opening $10,000.25, receipts $125.50/$74.50 and reversal of $125.50: opening principal remains $10,000.25; unapplied/cash control are $74.50; total debits and credits are $10,325.75. The local synthetic restore preserved all four entries and the append-only database guard. See [POSTGRES_INTEGRATION.md](POSTGRES_INTEGRATION.md).

Professional review of accounting mappings, allocation methods, finance/APR calculations, approved contracts, opening-balance migration reconciliation and legal applicability/effective dates is still required before live BHPH servicing. Full provider event idempotency, settlement reconciliation, partial corrections, authority/cutover, account adjustments, production security and operational recovery are not implemented by this rehearsal. No legal compliance or production readiness is claimed.


Separate synthetic schedule illustrations are now available (SCHEDULE_METHODS.md). They never allocate receipts or post interest to this ledger; the financial posting boundary described here remains in place.
