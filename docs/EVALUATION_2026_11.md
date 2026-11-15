# Developer browser evaluation — November 2026

Scope: local synthetic preview; invented records only. This is a developer
assessment, not dealership-staff testing, a security audit, legal review or
production acceptance.

## Exercised

- Firefox: 14 main routes at 1440, 390 and 320 pixels. Automated inspection
  found no outer page overflow or visible unlabeled form inputs; this does not
  establish full accessibility or inspect every conditional state.
- Deal desk: inline invented vehicle/customer, tax estimate, financing estimate,
  save, price change, tax recalculation and preservation of original history.
- Reconditioning: task/vendor, status, cost entry, reversal, replacement, exact
  investment filter and responsive page bounds.
- Completion: cash rehearsal, retained reminders, frozen buyer/vehicle facts,
  edit blocking, completed list, synthetic summary and incomplete-deal blockers.
- Customer activity: create, search in queue and complete an invented follow-up.
- Completed BHPH rehearsal → synthetic account: explicit $1,000.25 opening and
  reviewed $75.50 test receipt; one receipt was recorded and opening principal
  remained $1,000.25. Receipt remains unapplied; no real payment or loan exists.
- Documents: generated synthetic PDF uploaded to a new synthetic deal and
  downloaded with private/no-store headers.

## Findings and changes

- Account-opening review used “draft” for a completed rehearsal. The labels now
  identify the source accurately.
- Customer change history rendered empty detail disclosures for new activity
  events. It now names added/completed activity. Argon identified this; browser
  and tests independently verified the correction.
- Investment report had no specific Acquired filter, although those vehicles
  appeared in Active. Added the filter; verified desktop/mobile. Argon identified
  the gap.
- A customer disappearing between lookup and lock could cause a server error;
  the locked lookup now returns a scoped 404. Argon identified the edge case.

## Remaining evaluation / product gaps

- Inventory aging now uses optional recorded acquisition dates; older records
  remain unknown until entered, and sale-date tracking remains outstanding.
- Customer follow-ups now support assignment, rescheduling and reopening; full
  timeline pagination and richer queue filters remain. No SignalWire exists.
- DocuSeal is an offline request builder, not a running signing integration.
- BHPH servicing and due indicators are simulations; real allocation, contracts,
  delinquency, payoff and regulated financial calculations remain unimplemented.
- Reports do not yet cover sales, aging or full servicing and have no report export.
  The inventory report now has search, cost/price sorting and totals across matching
  vehicles; Argon identified these usability gaps.
- Customer queue now allows marking an activity done in place while preserving
  its filter, search and page (Argon review).
- Full role/isolation, keyboard/screen-reader, restore, concurrency, security and
  legal acceptance require dedicated testing beyond this browser pass.
- Existing status labels and workflows need observation with dealership staff;
  no staff or mother testing is claimed here.

Evidence screenshots, browser scripts and synthetic identifiers are kept in the
ignored `.local/evaluation-2026-11` workspace. Do not publish that directory.

## Verification results

The full PostgreSQL suite passed 466 tests during this evaluation. After the
final customer/report fixes, 12 focused PostgreSQL tests and 12 focused SQLite
tests passed. Firefox independently confirmed the customer-history labels,
Acquired report filter and completing an invented follow-up directly from a
filtered queue without losing the search. The queue action is role checked,
CSRF protected, and returns only to its own validated local route.

Investment report follow-up: filtered totals and pagination were verified using
30 synthetic vehicles on SQLite and PostgreSQL; Firefox checked search, sort and
outer page width at 1440/390/320 pixels. Asking-price totals state how many
vehicles have a price; acquisition aging and report exports remain unimplemented.
