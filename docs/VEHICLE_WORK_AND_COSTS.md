# Vehicle work and costs

Development implementation, October 30, 2026. Community MPL 2.0.

Inventory owns vendors, reconditioning tasks and the internal vehicle cost register.
Open a vehicle, then **Work and costs**. Add or edit work (including optional
details, same-dealership staff assignment, and target date), save its status,
record an incurred cost, review and reverse an incorrect cost, export the
vehicle's itemized cost CSV, or open **View vendor invoices** to attach and
download private synthetic vendor invoice PDFs. Vendors can be selected or
created in task/cost forms or managed in the **Vendors** directory with optional
contact details (`contact_name`, `phone`, `email`, `address`, `notes`);
normalized names are reused within one dealership. Completing work does not
automatically mark the vehicle available for sale.

## Record and money boundaries

Existing acquisition and recon amounts are preserved without a data rewrite.
Recon is now labeled **Unitemized reconditioning cost**. Total recorded investment
is purchase amount + unitemized recon + itemized costs − linked cost reversals.
Do not enter the same invoice in both the unitemized field and the itemized
register. The legacy amounts remain editable through the existing revision-checked,
audited vehicle form; they are not retroactively converted into journal entries.

New cost amounts are validated Decimal values converted to positive integer cents.
Each immutable record carries an equal debit/credit control pair: vehicle_cost /
cost_offset, or the opposite pair for a correction. These are internal synthetic
cost controls, **not general-ledger accounts, cash settlement, vendor payments,
accounts payable, customer charges, tax deductions or a determination of inventory
capitalization**. No payment, tax reporting or customer balance behavior changes.
Purchase/fee categories classify internal costs and do not change sales-tax rules.
Optional asking prices are stored on inventory with revision checks and audited
changes. Unknown stays blank, distinct from an explicitly entered $0.00. A vehicle
workspace shows asking price less total recorded investment; a negative difference
has a red **Below recorded costs** label. This is an estimate before overhead,
commissions and unrecorded costs, not net profit or an accounting valuation.
Starting a new deal from a selected, priced vehicle suggests its asking price.
The suggestion is editable; future inventory edits never rewrite existing deals.
Older forms that omit the new field preserve its existing value. Explicit blank
clears it. Asking price also supports shared inventory filters.

The **Work queue** link on Vehicles lists tasks across inventory with Open work,
Completed and All work views, plus target-date filters (`Overdue`, `Due today`,
`Upcoming`, `No target date`), task-age filters (`0–7`, `8–14`, `15–30`, and
`Over 30 days`), earliest-target-date and oldest-vehicle-acquisition sorts, and a
formula-safe filtered CSV export (`recon_queue_export`). Search includes vehicle
identity, job title/details, assignee and vendor contact fields; shared filters,
sorting, pagination and personal saved searches apply. Sold vehicles with open
tasks remain visible and labeled. Opening a job links to that vehicle's work list
with the job highlighted. No automatic vehicle-ready or sale status change is
introduced.

A reversal copies the original amount, category, vendor snapshot, task and
vehicle, retains a reason and actor, and links back to the original. The correction
screen shows the cost and exact negative adjustment before saving. One reversal per
cost; corrections cannot edit or delete original entries. Record a replacement
separately if necessary. Entry dates and effective cost dates remain distinct.
Future incurred-cost dates are rejected; planned work belongs in the task list.

Task states are To do, In progress and Done. Task edits (`title`, `detail`,
`status`, `vendor`, `assigned_to`, `due_on`) and quick status changes retain
actor/time through `AuditEvent` records and use revisions to reject stale updates.
Work is not deleted through the UI. Task completion is an operational staff
assertion, not a safety inspection, repair certification or assurance of
title/document readiness.

## Controls

- Membership scopes every page and selectable vehicle/vendor/task. Owners and
  inventory staff may write; read-only members can inspect the workspace.
- Services recheck current membership and serialize changes using dealership then
  vehicle locks, matching ordinary inventory save ordering.
- Each new cost/task has a per-vehicle unique request key. Identical retries return
  the original; a different cost payload under the same key is rejected.
- Costs and audit events save in the same transaction; a failed audit rolls back
  the entry and any new vendor.
- PostgreSQL and SQLite triggers reject cost updates/deletes, foreign vendors or
  tasks, unauthorized cost actors and inexact/cross-vehicle reversals. Database
  constraints enforce positive bounded amounts, known categories and balanced legs.
- Historical vendor display names are frozen in cost rows. The task's vendor is
  an operational relationship, not an invoice snapshot. Vendor profile edits are
  revision-checked and recorded in `VehicleVendorEvent` without rewriting past
  cost snapshots.
- Private synthetic vendor invoice PDFs (`VehicleInvoice` in `documents`) can be
  uploaded for a vehicle and optionally linked to a same-vehicle cost entry,
  stored in `PrivateMediaStorage` with SHA-256 integrity checks on download and
  audited upload/download events (`VehicleInvoiceEvent`).
- Net itemized totals are aggregated in integer cents. The shared inventory cost
  filter accepts dollars and compares cent totals, including corrected costs.
- Formula-safe, bounded CSV exports are available for the filtered investment
  report (`inventory_investment_report_export`), the filtered reconditioning work
  queue (`recon_queue_export`), and each vehicle's itemized cost register
  (`?export=costs` on `vehicle_recon`). An owner-only module export component
  (`inventory/export.py`) also exports structured inventory records and
  JPEG-checked photo bytes (`digest_basis: calculated_at_export_not_stored_at_upload`).
  None of these exports is a complete dealership backup or accounting statement.
- Workspace/form responses are private/no-store; mutations require CSRF protection.
- Routes and write services require DEBUG-derived RECON_DEMO_ENABLED. No production
  gate is removed. Use invented vehicles, work, vendors and costs only.

## Review and release gates

This increment records internal invented costs, operational tasks, vendor
contacts, and private synthetic PDF attachments, not a newly implemented
regulated payment or tax determination. Existing security, dealership-record
retention, legal-hold, complete export/restore and real-data gates in
RAILET_PLAN.md still apply. There is no delete/purge policy or assertion of
tax/accounting compliance. Before live cost-accounting/AP integration, obtain
accounting review of valuation, capitalization, accrual/payment separation,
vendor records, corrections and cutover reconciliation; review applicable current
authorities for that specific behavior. No vendor tax identifiers or bank/payment
credentials are collected here; uploaded PDFs are stored as synthetic test files
and are not virus-scanned or verified as authentic invoices.

## Verification

Independent reference: $5,000.10 purchase + $100.20 unitemized recon + $250.35
itemized repair = $5,350.65; reversing that repair restores $5,100.30 without
altering either baseline field. Tests cover filtered totals, scoped choices,
permissions/CSRF/development gate, exact corrections, immutable database rows,
audit rollback, stale tasks, invalid money/dates and request retries. PostgreSQL
races verify one entry/vendor per retry and only one reversal per original.
Developer checks are not staff usability validation or production acceptance.

Developer verification on October 30, 2026: full PostgreSQL regression suite
418/418 passed; final inventory/reconditioning PostgreSQL checks 27/27 passed,
including concurrent saves/corrections; SQLite integrity checks 11/11 passed;
Django system check and migration drift check passed. Browser checks exercised
work/vendor entry, status changes, cost entry, correction, replacement, error
preservation and the exact investment filter. Desktop 1440px and narrow 390/320px
layouts had no outer horizontal overflow; the cost table scrolls internally on
small screens. New migrations were applied to the local synthetic preview.

Asking-price migration adds nullable values without backfilling a fictitious price.
On SQLite, dependent vehicle-cost/vendor scope triggers are removed and restored
inside the schema migration transaction around Django's table rebuild. Existing
cost immutability triggers remain installed. PostgreSQL retains its normal CHECK
constraint migration. Prior baselines, cost entries, tasks and revisions are
preserved; verification distinguishes fresh migrations from populated upgrades.

Asking-price/work-queue follow-up verification on October 30, 2026: the full
PostgreSQL suite passed 430 tests. After final form-preservation refinements and
two additional cases, 41 targeted PostgreSQL checks passed; 24 SQLite checks
passed. Populated PostgreSQL upgrade and a separate populated SQLite
upgrade/reverse/forward exercise preserved baseline costs, itemized entries,
tasks and database guards. Existing preview vehicles retained unknown asking
prices until explicitly edited. Browser checks verified $6,995.00 − $5,175.40 =
$1,819.60, a below-cost warning for $4,995.00, the editable new-deal suggestion,
open/completed searches and links to the selected job. Final 1440/390/320px queue
checks verified job identity and mobile status remain visible without outer
horizontal overflow. Additional vendor/date columns remain horizontally scrollable.
These are developer checks; dealership-staff usability validation is still pending.

Acquisition-date follow-up: vehicles now have an optional recorded acquisition
date. Existing rows stay null; legacy submissions that omit the field preserve it.
Future dates are rejected in the form. The investment report offers 0–30,
31–60, 61–90, over-90 and unknown-date filters, with calendar days since the
recorded acquisition date and oldest-acquisition sorting. Future dates from
legacy/direct writes are shown as requiring review, not as negative age. Sold
vehicles show days since acquisition, not days available or days until sale;
accurate time-to-sale requires a separately recorded sale date. Dates are staff
entries and are not independent evidence of ownership.

Developer checks: 20 PostgreSQL tests passed; 20 SQLite tests passed with one
PostgreSQL concurrency case skipped. Boundary dates, unknown/future dates,
legacy preservation and invalid future entry were exercised. Firefox saved an
invented acquisition date and verified its 45-day bucket at desktop/mobile widths.

## November 5, 2026 follow-up verification

- **Task editing, assignment, scheduling, and queue aging:** Added `detail`,
  same-dealership active staff `assigned_to`, and optional `due_on` target dates
  to `ReconTask`, with revision-checked editing (`recon_task_edit`), `AuditEvent`
  change tracking, and queue schedule/task-age filters and sorts.
- **Vendor contact directory and change history:** Added optional `contact_name`,
  `phone`, `email`, `address`, `notes`, `revision`, and `VehicleVendorEvent`
  history to `VehicleVendor`, with dealership-scoped directory/detail/edit views
  that preserve normalized name uniqueness and historical cost vendor-name
  snapshots.
- **Private synthetic vendor invoice PDFs:** Verified `VehicleInvoice` and
  `VehicleInvoiceEvent` upload/download flows, same-vehicle cost linking, SHA-256
  download verification, and reversal preservation (`39` SQLite tests passing, `1`
  backend-specific skip).
- **Filtered operational and cost CSV exports & time-to-sale:** Added formula-safe,
  bounded CSV exports for the investment report, reconditioning work queue, and
  per-vehicle itemized cost history, plus optional staff-entered `sold_on` dates
  and database-side time-to-sale filtering on the investment report (`50` SQLite
  tests passing across `inventory.test_investment_report`,
  `inventory.test_reconditioning`, `inventory.test_pricing_queue`, and
  `inventory.tests`; `18` tests passing in `inventory.test_export` and
  `inventory.test_photos` with `1` PostgreSQL concurrency skip). All checks are
  developer tests on synthetic data, not dealership-staff validation or
  production acceptance.
