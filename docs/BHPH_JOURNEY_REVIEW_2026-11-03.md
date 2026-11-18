# Synthetic BHPH journey review

Developer walkthrough, November 3, 2026. This is not staff usability validation,
legal review, or authorization to use real dealership records.
The walkthrough, screen observations and test results below record that review;
they are not fresh verification of the current implementation.

## Journey exercised

In Firefox, a developer used the interface to create a synthetic vehicle and
customer while starting a BHPH deal, entered a Florida draft tax estimate and
precomputed financing illustration, saved and edited the deal, and reviewed its
saved figures. Incomplete financing terms stopped the completion rehearsal;
the missing creditor and first payment date were entered through the deal and
the review was repeated. The developer then froze a completion rehearsal,
opened its frozen demo summary, created a synthetic BHPH account through the
preview/confirmation screens, and recorded a synthetic payment. The account
opening and receipt postings were checked in the test database. The account's
opening amount was explicitly entered; it was not carried over as real debt.

The completion warning was updated to identify the missing financing fields. The deal
workspace was changed so it no longer suggested optional demo account setup was the mandatory
next step before review. Screens in this handoff were checked at 1440 and 390
pixels; this does not establish usability for all screen sizes or assistive
technologies. The test data deliberately included incomplete title and trade
facts, and the rehearsal retained its reminders.

An independent review improved the saved-rehearsal handoff and made the packet
link easier to find. Existing accounts were identified as potentially based on an
earlier draft, because their saved context need not match the frozen rehearsal.
The handoff and packet link were rechecked at 1440, 390 and 320 pixels. The
completion, review, packet, packet-export and completed-account test suites
passed 59 PostgreSQL tests; completion, desking and account handoff passed 37.

## What is still needed for real dealership work

1. **Reviewed documents and deal finalization:** Approved, applicable Florida
   forms and disclosures, data completeness controls, generated/finalized
   snapshots, signing and delivery evidence, plus legal and financial review.
   The current frozen summary is a demo artifact, not a contract or sale.
2. **Loan origination and servicing:** Verified contractual terms, calculations,
   schedules, allocations, interest, late treatment, payoff and corrections.
   Current account openings are invented amounts and demo receipts remain
   unapplied; demo due/late status is a limited schedule simulation.
3. **Money movement and reconciliation:** Reviewed payment-provider integration,
   settlement, returns, idempotency and reconciliation before real payments.
   No customer funds are processed in the walkthrough.
4. **Security and operational readiness:** MFA, deployment and secrets controls,
   independent security review, tested backups/restoration, and operational
   incident, access and retention procedures before real customer data.
5. **Validation and migration:** Dealer staff usability testing; independent
   financial reference cases and legal review; reconciled migration and a
   controlled pilot. See `RAILET_PLAN.md` and `REMAINING_WORK.md` for scope,
   compliance research and the broader release gates.
