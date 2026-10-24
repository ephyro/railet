<!-- SPDX-License-Identifier: MPL-2.0 -->
# Draft trade-ins and inventory intake

Development scope: synthetic data only. The initial workflow supports one active
trade-in per draft. `DraftTradeIn` owns proposed vehicle/title/mileage and lienholder
information; the existing `DraftDeal.trade_allowance` and `trade_payoff` remain the
only current monetary values. No duplicated trade totals or customer profile is
created. Existing monetary-only drafts are retained without inventing a vehicle.

Title brand and mileage status default to Not verified, with blank reading distinct
from zero. Historical VIN formats are accepted. Saving a trade requires a VIN or a
year/make/model identity; intake requires all four. Sale and trade VINs cannot match.
Reported actual/not-actual/exceeds statuses require a reading and explicit unit.
An exemption claim is recorded for review, never inferred from age or treated as an
approved exemption. No odometer certificate, title reassignment, payoff instruction,
tax credit, payment or financial posting is generated.

Inventory intake is an explicit review page, enabled only in development through
`TRADE_INTAKE_DEMO_ENABLED` (defaults to DEBUG). Production remains gated. The page
shows the affected vehicle and proposed amounts, requires an entered acquisition
cost and stock number, and records the user's acquisition-evidence acknowledgement.
That acknowledgement is not a legal ownership determination. Inventory creation
runs through `inventory.intake.create_trade_vehicle`, with copied structured identity,
Acquired status, a private source link and audit event. Customer, lienholder and
payoff notes are not copied into inventory. Cost is not derived from allowance,
payoff or equity; no ledger entry is posted. Existing same-dealer VINs block intake
for review. This is not a global VIN uniqueness guarantee for all inventory entry
paths. Historical/blank VIN handling remains supported in ordinary inventory.

The locked parent and revision protect trade edits, worksheet edits, removal and
intake. Repeated intake returns its existing inventory record; it cannot create a
second vehicle for the same trade. Intake identity is frozen in the original trade;
current inventory may later change independently. Every new deal event includes a
versioned snapshot of retained active and archived trades. Prior events are untouched.
Removal is reviewed before confirmation: it clears allowance/payoff, shows the
resulting draft balance, requires a reason, retains the trade and its history, and
leaves any acquired inventory intact. A negative resulting draft balance blocks
removal. No-op edits create no history event.

## Compliance register

Primary-source review: October 23, 2026. This table records development controls,
not a certification or exhaustive legal analysis.

| Authority | Scope and control implemented | Production gate / effective date |
| --- | --- | --- |
| [49 CFR §580.5](https://www.ecfr.gov/current/title-49/subtitle-B/chapter-V/part-580/section-580.5) | Ownership transfers require an odometer disclosure workflow. These are reported draft facts, without signatures, certification or transfer output. | Approved federal/Florida forms, transfer-date rules, signatures and delivery evidence remain required. Section history includes 2019 amendments; exact applicable effective dates must be reconciled before live disclosure generation. |
| [49 CFR §580.17](https://www.ecfr.gov/current/title-49/subtitle-B/chapter-V/part-580/section-580.17) | Exemptions depend on vehicle and transfer circumstances. An entered exemption claim remains unverified; no age-only rule is coded. | Review the relevant effective provisions and exception evidence before treating any transfer as exempt. The eCFR title was current through October 21, 2026; its title-wide amendment date is not a section effective date. |
| [Florida §319.14, 2026 compilation](https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0300-0399/0319/Sections/0319.14.html) | Retain title brands and carry them into intake. Unknown is explicit. No cleared title, approved disclosure or advertising eligibility is inferred. | Reconcile effective amendments and applicable branding/disclosure evidence before live transfer or advertising output. |
| [Florida §319.22, 2026 compilation](https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0300-0399/0319/Sections/0319.22.html) | A saved proposal cannot establish ownership. Intake requires a separate review and is development-only. | Counsel/FLHSMV review of dealer acquisition, title/reassignment evidence, co-owner authority, liens and transfer requirements; exact effective-date reconciliation remains open. |
| Florida tax and retail installment rules in the main plan | Allowance/payoff are worksheet adjustments only. Sales tax stays manually entered; no trade tax credit or statutory amount-financed calculation is added. | Reviewed DOR rules, transaction-specific tax cases and finance-charge classification before automated tax or financed disclosures. |

The current statutory compilation may include provisions with different effective
dates. Unresolved applicability and section-level effective dates keep live transfer,
title, odometer, tax and payoff behavior disabled. The synthetic intake rehearsal
is a development database operation, not a replacement for those workflows.

## Verification

Tests must cover tenant/role isolation, stale revisions across modules, negative
equity and removal, no-op saves, audit rollback, duplicate/replayed/concurrent intake,
unknown-versus-zero mileage, frozen intake identity, and retained history. Staff
usability testing, production document review and restore drills are separate gates.

Verified on the development VM: all 101 PostgreSQL tests passed, including
simultaneous intake requests producing one vehicle, one inventory audit event and
one deal event. The migration test preserves existing amounts and legacy audit
JSON, creates no fabricated trades and leaves existing mileage unknown. Focused
local SQLite trade/migration checks passed (17 cases, one PostgreSQL-only skip).
Django system and migration-drift checks passed.

Firefox developer checks verified stale-work preservation, exact negative-equity
worksheet totals, unknown defaults, explicit cost entry, carried title/mileage,
intake replay, source links and removal preview. The deal and trade forms had no
horizontal page overflow at 1440, 390 and 320 pixels. A new synthetic deal and
inventory record were used; the owner's existing review deal was not changed.
These checks are not staff usability validation or legal review.
