<!-- SPDX-License-Identifier: MPL-2.0 -->
# Draft deal types and financing proposals

Development scope: synthetic data only. Cash, outside financing and BHPH are
classifications on the existing draft, using its authoritative vehicle and customer
links. Existing drafts migrate to `undecided`; no cash status is inferred.

Each financed kind has its own optional proposal, unique per draft and kind.
Switching type preserves both proposals. Saving includes submitted edits to inactive
proposals, while omitted proposal forms preserve stored values. Invalid inactive
entries are revealed and block the entire save. Unknown values stay blank; an
explicit zero contract rate remains zero. Biweekly and semimonthly are distinct.
The creditor legal name is entered, never inferred from a dealership display name.

The parent row lock and revision protect proposal, worksheet and party edits.
Server-owned parent/kind determine ownership, never submitted IDs. Deal and proposal
changes plus one versioned audit snapshot commit atomically. Snapshots include all
retained proposals; previous event JSON is untouched. No-op saves add no event.
Database constraints enforce valid kinds, unique proposals, positive payment counts,
nonnegative rates and known frequencies. Decimal rate precision and field storage
bounds are technical constraints, not statutory limits. No legal rate limit is
inferred from these fields. No APR, payment amount, amortization, accrual or
origination is calculated. Saving cannot create a contract, loan or payment.

## Compliance register and production gates

Primary sources reviewed October 23, 2026, for this development scope:

| Authority | Applicability and implemented control | Outstanding gate |
| --- | --- | --- |
| [Regulation Z §1026.18](https://www.consumerfinance.gov/rules-policy/regulations/1026/18/) and [§1026.22](https://www.consumerfinance.gov/rules-policy/regulations/1026/22/) | Closed-end disclosures distinguish amount financed, finance charge, APR and payment schedule. The worksheet remains “draft balance”; proposed annual contract rate is explicitly distinct from APR. No disclosures are generated. | Verify transaction coverage, section effective dates, complete fee classification and independent calculation cases before calculations or consummation. |
| [Florida §520.07, 2026 compilation](https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0500-0599/0520/Sections/0520.07.html) | Retail installment contract completion, execution, delivery, and financial disclosures require a separate reviewed workflow. Partial drafts cannot be signed or finalized. | Review applicable amendments, effective dates, forms, licensing and delivery controls before live contracts. |
| [Florida §520.08, 2026 compilation](https://www.flsenate.gov/Laws/Statutes/2026/520.08) | Vehicle-class finance-charge provisions must not be treated as a universal APR cap. No statutory cap or financing calculation is implemented here. | Resolve applicable vehicle class, method, dates and limits with counsel and independent reference cases. |
| [Regulation B §1002.2](https://www.consumerfinance.gov/rules-policy/regulations/1002/2/) | Calling a record a draft does not determine application status; actual practices matter. No live credit application, decision or adverse-action workflow is enabled. | Review application/inquiry handling, notices, retention and decision controls before live credit workflows. |

The eCFR title 12 compilation consulted was current through October 21, 2026;
its title-wide amendment date is not a section effective date. The 2026 Florida
compilation likewise does not establish that every provision is effective for a
given transaction date. Section-level amendment/effective-date reconciliation and
legal/financial review remain unresolved production gates. These records establish
safe synthetic development controls, not legal certification or production readiness.

## Verification

Automated cases cover blank versus zero, separate proposals retained through type
switches, invalid inactive input preserving work without partial writes, stale
revisions, no-op saves, audit failure rollback, server-owned proposal identity and
viewer restrictions. Existing authorization, migration, decimal worksheet and
PostgreSQL concurrency checks remain required. Browser checks are developer checks;
dealership staff usability validation remains pending.

Verified on the development VM: all 85 PostgreSQL tests passed, including existing
concurrent-create and dealership isolation checks. Local SQLite suite: 85 tests,
83 passed and two PostgreSQL-specific checks skipped. Migration drift and Django
system checks passed. Firefox verified separate unsaved proposals surviving a cash
save/reload, explicit zero versus unknown rate, invalid inactive proposal recovery,
and no horizontal page overflow at 1440, 390 and 320 pixels. A separate synthetic
draft was used; the owner's existing review deal was not edited.
