# Separate schedule illustrations: precomputed and daily simple interest

## Research and production boundary

The owner commonly selects precomputed in DealerCenter and wants both methods available. Support them as distinct methods with explicit assumptions; do not infer an existing contract's method from a remembered UI choice or switch posted obligations between methods.

Primary sources checked October 24, 2026:

- [CFPB consumer explanation](https://www.consumerfinance.gov/ask-cfpb/whats-the-difference-between-a-simple-interest-rate-and-precomputed-interest-on-an-auto-loan-en-841/) (page reviewed January 30, 2024): precomputed and simple-interest models differ, especially with extra/early payments. Educational guidance is not a complete contract or allocation algorithm.
- Florida Legislature, **2026** [520.085](https://www.leg.state.fl.us/Statutes/index.cfm?App_mode=Display_Statute&URL=0500-0599/0520/Sections/0520.085.html): simple-interest contracts are treated separately from the general prepayment-credit provision. Applicability and history/effective-date review remain for counsel; no fees, rate limits or deferral rules are activated here.
- Florida Legislature, **2026** [520.09](https://www.leg.state.fl.us/Statutes/index.cfm?App_mode=Display_Statute&URL=0500-0599/0520/Sections/0520.09.html): early payment can involve an unearned-finance-charge credit. A precomputed scheduled balance must not be presented as the early payoff amount. No statutory rebate formula or acquisition charge is hardcoded in this slice.
- The official Florida [69V-50.100 rule page](https://flrules.org/gateway/ruleNo.asp?id=69V-50.100) identifies the payment-allocation rule as **not adopted by FAC yet**. The linked September 24, 2010 development notice contains preliminary language, not an established effective rule. Do not use that draft as a production allocation requirement. The full applicability/alternative authority review remains unresolved.
- Federal precomputed-credit refund requirements, including 15 USC 1615, require current official-text/applicability verification before payoff/refund implementation. Direct official retrieval did not succeed in this research pass. No federal formula, threshold or timeline is coded from secondary compilations.

These uncertainties do not block reversible synthetic schedule comparisons. They **do** keep contractual allocation, rate/charge eligibility, APR disclosure, extra-payment treatment, payoff/refunds, statements and live servicing disabled. Existing manual receipts remain wholly unapplied.

## Planned illustration profiles, not approved contract rules

- **Precomputed / supplied charge v1:** input opening principal and a separately supplied synthetic total finance charge. Divide their sum over explicit due dates; round regular installments to cents with HALF_UP and put the exact residual in the final installment. Show remaining scheduled total, not principal outstanding or payoff. Do not allocate earnings, compute APR, derive a finance charge from APR, or imply that future finance charges are always collectible on early payoff.
- **Daily simple / actual days / fixed 365 v1:** input annual contract rate (not APR), fixed regular installment, explicit term/dates. Forecast each on-time interval's simple interest on the remaining principal using actual elapsed days divided by fixed 365; round interest once per interval with HALF_UP, apply the assumed payment to that interest then principal for the illustration only. The last payment can shrink to clear the balance. Refuse negative-amortizing terms, a balloon greater than the regular payment, or early clearance before the requested count instead of silently changing terms. No fees, compounding, late/partial/extra payments or live allocation. Fixed 365 even in leap years is an explicit **illustration assumption**, not an inferred Florida contractual rule.

Frequency support: weekly means seven days; every two weeks means fourteen; monthly uses the original first-due day with month-end clamping without drift; twice-monthly uses two explicit distinct day anchors between 1 and 28. Do not equate every two weeks with twice a month. No holiday/business-day adjustments are made. All dates must strictly increase after the opening date. Profile limits on term/rate/date range are computational scope, not legal limits.

Saved illustrations belong to the synthetic ledger book, retain inputs/outputs and calculation version, and do not change the book, postings, receipts or customer profile. Multiple alternative illustrations can be compared; none selects or amends an actual contract method. No automatic method is chosen on an existing account.

## Independent arithmetic reference cases

1. Precomputed: principal $1,000.00, supplied finance charge $100.00, three payments. Total $1,100.00; regular payments $366.67, $366.67, final $366.66; exact remaining totals $733.33, $366.66, $0.00. No principal/earned-interest split is asserted.
2. Daily simple: principal $1,000.00, annual contract rate 36.5%, due at 10 and 20 days, regular payment $510.00. First interval interest $10.00, principal $500.00, remaining principal $500.00. Second interval interest $5.00, final payment $505.00, principal $500.00. Total interest $15.00 and payments $1,015.00. The rate is an artificial arithmetic reference, not a legally validated offer.
3. Zero-rate case: $1,000.00 with ten $100.00 on-time installments has $0.00 interest and finishes at zero.
4. Monthly anchoring: January 31, February 28/29, March 31. Weekly/every-two-weeks and twice-monthly must not drift into one another.

## Implemented development controls

The owner selected monthly as the common BHPH frequency. New illustration forms suggest monthly; method selection remains explicit. Other supported cadences remain available.

Draft BHPH and outside-finance proposals now independently record an optional proposed interest method (precomputed or simple). Existing proposals remain unchosen. Omitted fields preserve prior selections; explicit blank clears a proposal selection. This is draft metadata, not an amendment or an instruction to allocate receipts. Simple interest does not automatically select a contractual day basis.

Saved synthetic illustrations retain inputs, outputs, calculation version and a canonical output digest. PostgreSQL and SQLite reject ordinary updates/deletes; PostgreSQL additionally checks insertion ownership and method/version metadata. Saving is transactional and idempotent, with signed actor/dealership-bound previews. Privileged database administrators can bypass database controls; this is not a tamper-proof claim.

Deal history schema 5 includes the proposed method. New demonstration packets use snapshot schema 3 and template demo-summary-v3; retained earlier artifacts remain unchanged. Calculations and schedules do not post interest, reduce principal, allocate receipts or produce payoff quotes.

Developer verification includes independent arithmetic references, cadence anchoring, final cents, invalid mixed methods, authorization/isolation, stale/tampered previews, immutable records and unchanged ledger postings. Synthetic browser checks covered both methods and 1440/390/320-pixel layouts. This is developer verification, not dealership staff or legal validation.
