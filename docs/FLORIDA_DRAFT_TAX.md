# Florida draft vehicle tax estimates

Research date: October 29, 2026. Development estimates only; no tax filing,
collection, legal form, contract finalization or production gate is enabled.

Primary authorities reviewed:

- [2026 §212.05(1)(a)](https://www.flsenate.gov/Laws/Statutes/2026/212.05): general 6% retail tax.
- [2026 §212.02(16)](https://www.flsenate.gov/Laws/Statutes/2026/212.02): sales-price scope and qualifying same-transaction trade allowance. Dealer fees are included; loan payoff and down payment are financing movements, not automatic trade-credit deductions.
- [2026 §212.054(2),(3)](https://www.flsenate.gov/Laws/Statutes/2026/212.054): single-item $5,000 surtax cap and purchaser residence county on title/registration.
- [DOR 2026 DR-15DSS, R.11/25](https://floridarevenue.com/Forms_library/current/dr15dss_26.pdf): 67 county rates for 2026. Inspected both pages and page 1 screenshot. Martin and Palm Beach are 0.5% in this edition; do not reuse the 2025 table or infer a rate from ZIP. Review annual changes before 2027. County expirations/future changes are not automatically extended.
- [DOR TIP 21A01-02](https://floridarevenue.com/taxes/tips/Documents/TIP_21A01-02.pdf): third-decimal half-up cent rounding effective July 1, 2021, transition ended September 30, 2021.
- [DOR tax calculation guidance](https://floridarevenue.com/taxes/taxesfees/Pages/tax_interest_rates.aspx): combined state/local rate and aggregate-invoice rounding. Calculate raw state + capped county tax, round the combined tax once; preserve separately rounded components and any invoice rounding difference so the displayed breakdown ties exactly.
- [DOR TIP 26A01-01, February 11, 2026](https://floridarevenue.com/taxes/tips/Documents/TIP_26A01-01.pdf): nonresident/partial-exemption cases require different evidence. Not implemented automatically.

Rule 12A-1.007 was located through DOR's index/search, including the separately
stated mandated title/tag-fee exclusion and same-transaction/resale trade rule,
but the current official rule page and historical DOR PDF could not be retrieved.
Current rule text/effective-date verification and professional tax/legal review
remain unresolved before live use. Draft estimates require explicit confirmation
before excluding title/tag amounts or applying a trade allowance. Non-government
service charges belong in the taxable dealer-fee bucket. Special exemptions,
nonresidents, leases, multiple taxable products, tax credits, rebates, nonstandard
transactions and dates outside 2026 require manual review rather than a guessed
zero or generic rate. An entered county is a staff assertion about registration
residence, not verified geocoding or address verification.

Implementation profile: one Florida-resident retail vehicle sale delivered in
Florida; taxable price = vehicle price + taxable dealer fee minus confirmed
qualifying trade allowance, floored at zero. Title/tag exclusion requires a
separately stated government-fee confirmation; payoff/down do not reduce the tax
base. No warranties, GAP, accessories or other product taxes are inferred.
Store date, county, table/calculation version, inputs, assumptions, components
and result in the draft/event/packet snapshot. Existing manual drafts retain
their entered tax until explicitly changed. No historical artifact is regenerated.

## Desking implementation and boundaries

Drafts retain tax_context including the selected county/date, source table and
calculation profile, base amounts, qualification assertions, rounding components
and total. Persisting an automatic draft recomputes tax from authoritative prices;
client tax/summary values are not trusted. The server rejects unsupported dates,
unknown counties, unconfirmed exclusions/credits and known non-Florida customer
addresses. Old forms/manual drafts retain their entered amounts; explicit manual
mode records a reason. Existing historical event/packet bytes are never rewritten.
Lifecycle archive/restore preserves prior tax rather than recalculating it.
Trade save/removal recalculates the draft using the saved profile; qualification
can be recorded directly in trade entry, and the after-removal preview uses the
new tax. These are draft effects, not receipts, journal postings or tax filings.

Inline vehicle creation reuses inventory's ModelForm, normalization, duplicate
VIN review and actor audit through an inventory-owned transactional interface.
Dealership locking precedes validation/save; a repeated creation key returns the
original deal without a second vehicle/customer. Validation or audit failure rolls
back all three records. Server checks stock conflicts, active stock and reviewed
matching VIN IDs under the same lock. Unknown title/mileage facts stay unknown.

Desking payment illustrations use exact Decimal arithmetic, a versioned profile,
monthly terms and explicit assumptions. Precomputed divides principal plus an
entered total finance charge with an exact final residual; the contract rate is
not interpreted as an add-on rate. Simple uses a clearly labeled equal-monthly
periodic illustration (annual rate / 12), rounded monthly interest/payments and
an adjusted final payment. It is not the fixed-365 daily-interest engine, APR,
legal amount financed, payoff or a contract schedule. Other payment frequencies
remain valid proposal metadata but do not receive an invented monthly amount.
Terms remain editable draft metadata; no ledger book or payment is created.

New deal events use schema 6; new synthetic packets use schema 5/template v5 and
retain tax provenance and the proposed finance charge. Old artifacts remain in
their original versions. Automatic estimates and the live preview endpoint remain
DEBUG-gated via FL_TAX_ESTIMATES_ENABLED. The estimator returns private/no-store
responses, requires membership, POST and CSRF, and receives only price/tax/term
inputs; it does not fetch or transmit customer profiles. Draft editing still
requires owner/staff permissions and revision checks. No hosting, signing,
production tax, live payment or licensing boundary was changed.

Additional live-review questions: verify current 12A-1.007 treatment of separately
stated credit/finance charges, rebates, tag-agency/service charges and trade-credit
qualification against actual dealer documents. The illustration is separately
identified from the vehicle's draft tax base; the feature does not decide tax
classification of a real credit contract or other taxable products. Professional
approval is still required before any real sale/receipt/document uses this profile.

Current verification includes literal $10,000 Miami-Dade -> $650 and $4,000 ->
$280 references, 2026 Palm Beach/Martin -> $625 at $10,000, confirmed $2,000 trade
and $299 dealer fee -> $547.94, low-value aggregate cent rounding, unknown/year/
exclusion rejection, manual history preservation, atomic rollback, stock/VIN
review and concurrent creation keys. Browser end-to-end used only invented new
records and verified $547.94 saved tax, a $424.87 monthly precomputed illustration,
then repriced the saved draft and verified $607.94 tax while retaining its first
event. A separate simple-monthly browser case verified $332.14 for a $10,000
balance, 12% annual rate and 36 equal monthly periods. This illustration's final
payment is $332.28 and total interest $1,957.18 under its documented rounding.
The precomputed $1,000 + $100 / three reference retains $366.67/$366.67/$366.66.

Final regression result: full PostgreSQL suite **404 tests passed in 123.047s**,
including inline creation races and existing payment/document workflows. Earlier
failures were obsolete expectations that deal type/amounts lived under More deal
details and a concurrency-test barrier placed inside the newly serialized save;
the tests now check the visible desk and race requests before the critical section.
The race still asserts exactly one customer, vehicle, deal and audit/event set.
The local additive migrations preserve old draft tax amounts and default old tax
metadata to empty/manual; no financial postings or retained artifacts were migrated.
A final focused run also exercises fail-closed handling of unverifiable saved tax
metadata after the last guard refinement. Exact results are in the ignored review
folder. Staff usability and professional legal/tax approval remain outstanding.
Final focused verification after the saved-metadata guard and UI expectation
refinements: **21 SQLite tests passed in 5.530s**, no skips. Migration consistency
reports no changes. The development preview is running through the existing
localhost-only persistent tmux session.
