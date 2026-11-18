<!-- SPDX-License-Identifier: MPL-2.0 -->
# Accounting mappings and reconciliation design (synthetic stage)

Design date: November 7, 2026. Community MPL 2.0.

This document specifies how Railet's internal vehicle cost register
(`inventory.VehicleCostEntry`) and synthetic BHPH subledger
(`finance.DemoBook` / `finance.DemoPosting`) will map to a configurable
dealership chart of accounts and reconcile against external general-ledger (GL)
exports. **This is an engineering design only.** It does not prescribe tax or
GAAP capitalization rules, enable QuickBooks or live accounting sync, allocate
customer payments, or treat existing synthetic controls as a general ledger.
The chart/mapping models, external GL export and reconciliation workflows in
sections 2–6 are proposals, not implemented controls or a completed cutover.

---

## 1. Current persisted models and strict separation of concerns

Railet currently maintains three distinct money representations that must never
be conflated:

1. **Legacy vehicle baseline fields (`inventory.Vehicle.acquisition_cost`, `recon_cost`, `asking_price`):**
   - Editable `Decimal(12, 2)` fields on `Vehicle`, protected by revision checks
     and `AuditEvent` history. They are **not** journal postings.
   - `asking_less_cost` (`asking_price - total_cost`) is a pre-overhead,
     pre-commission operational estimate, **never net profit or an accounting
     valuation**.
2. **Itemized vehicle cost register (`inventory.VehicleCostEntry`):**
   - Append-only integer-cent rows (`amount_cents > 0`) with `kind in ('cost', 'reversal')`,
     `category in ('purchase', 'auction', 'transport', 'repair', 'parts', 'detail', 'other')`,
     `debit`/`credit` control labels (`vehicle_cost` / `cost_offset`, reversed on
     corrections), `vendor` FK + frozen `vendor_name` snapshot, optional `task`
     FK, `reverses` OneToOne FK, `reason`, `effective_on`, `entered_at`,
     `request_key`, and `actor`.
   - **Boundary:** `vehicle_cost` and `cost_offset` are internal synthetic
     cost-control legs. Recording a cost does **not** create an accounts-payable
     (AP) liability, pay a vendor, settle cash, or determine tax capitalization
     vs. period expense.
3. **Synthetic BHPH subledger (`finance.DemoBook`, `finance.DemoPosting`):**
   - Append-only integer-cent rows (`amount_cents > 0`, `posting_version = 'demo-unapplied-v1'`)
     with `kind in ('opening', 'receipt', 'reversal')`, `payment_method in ('unspecified', 'cash', 'check', 'other')`,
     and balanced bucket pairs:
     - `opening`: debit `principal`, credit `opening_offset`
     - `receipt`: debit `cash_control`, credit `unapplied`
     - `reversal`: debit `unapplied`, credit `cash_control` (linked via `reverses`)
   - **Boundary:** `cash_control` is an internal receipt control bucket, **not**
     a reconciled bank deposit or cash-drawer count. `unapplied` is unallocated
     customer receipt liability/clearing, **not** principal reduction, earned
     interest, or fee income.

---

## 2. Versioned configurable GL mapping model

Each dealership's CPA/accountant structures their general-ledger chart of
accounts differently. Railet must never hardcode account numbers or force a
single capitalization policy.

### Proposed schema (future implementation, gated on CPA review)

- **`AccountingChartAccount`:**
  - `dealership` (FK), `code` (e.g., `"1200"`, `"2150"`), `name` (e.g.,
    `"Vehicle Inventory — Cost"`), `classification` (`asset`, `liability`,
    `equity`, `revenue`, `expense`, `clearing`), `is_active`, `revision`.
  - Unique per `(dealership, code)`.
- **`AccountingMappingVersion`:**
  - `dealership` (FK), `version_number` (positive integer), `effective_from`
    (date), `status` (`draft`, `active`, `superseded`), `approved_by` (owner FK),
    `approved_at`, `notes`, `rules_sha256`.
  - Immutable once activated; changing a rule creates a new
    `AccountingMappingVersion` so historical subledger-to-GL translations remain
    reproducible under the exact mapping version in effect when exported.
- **`AccountingMappingRule`:**
  - `mapping_version` (FK), `source_domain` (`vehicle_cost` or `bhph_posting`),
    `source_kind` (`cost`, `opening`, `receipt`, `reversal`), `source_category`
    (for vehicle costs: `purchase`..`other`, or `''` for BHPH),
    `payment_method` (for BHPH receipts/reversals: `cash`, `check`, `other`,
    `unspecified`, or `''`), `debit_account` (FK to `AccountingChartAccount`),
    `credit_account` (FK to `AccountingChartAccount`).
  - Reversal rules must always invert the exact `debit_account` and
    `credit_account` resolved for the original source entry (`reverses_id`),
    even if a later mapping version is active on the reversal's date.

---

## 3. Illustrative balanced journal mappings (invented amounts only)

The examples below use invented figures to illustrate how internal control legs
translate into candidate GL journal lines under a dealership-configured mapping
version. **Account codes and capitalization choices below are illustrative
examples, not tax or GAAP advice.**

### Example A — Itemized vehicle repair cost and linked reversal

- **Source event 1 (`VehicleCostEntry #401`):**
  - `kind='cost'`, `category='repair'`, `amount_cents=25035` (`$250.35`),
    `effective_on=2026-11-01`, `entered_at=2026-11-01T14:10:00Z`,
    `vendor_name='Practice Garage'`, `request_key=UUID(...)`, `actor_id=7`.
  - Internal control legs: debit `vehicle_cost` `$250.35`, credit `cost_offset` `$250.35`.
  - **Mapped GL journal candidate (under `mapping_version=1`):**
    - Debit `1210 · Vehicle Inventory — Reconditioning (or dealer-selected Repair Expense)` `$250.35` (`25035` cents)
    - Credit `2190 · Vehicle Cost Clearing / Unvouchered Recon Offset` `$250.35` (`25035` cents)
    - *Note:* `2190` is a clearing/offset account, **not** settled cash or a
      paid vendor invoice. Turning `2190` into a vendor payable or bank
      disbursement happens in the dealership's AP/accounting system when the
      actual bill is vouchered/paid.
- **Source event 2 (`VehicleCostEntry #402`, reversing `#401`):**
  - `kind='reversal'`, `reverses_id=401`, `category='repair'`,
    `amount_cents=25035` (`$250.35`), `effective_on=2026-11-05`,
    `reason='Duplicate synthetic invoice'`, `actor_id=7`.
  - **Mapped GL journal candidate (inverted from `#401`'s mapping):**
    - Debit `2190 · Vehicle Cost Clearing / Unvouchered Recon Offset` `$250.35` (`25035` cents)
    - Credit `1210 · Vehicle Inventory — Reconditioning` `$250.35` (`25035` cents)

### Example B — BHPH unapplied receipt, reversal, and separate bank settlement

- **Source event 1 (`DemoPosting #801`):**
  - `kind='receipt'`, `payment_method='cash'`, `amount_cents=12550` (`$125.50`),
    `effective_on=2026-11-02`, `entered_at=2026-11-02T16:20:00Z`, `book_id=12`,
    `actor_id=5`.
  - Internal control legs: debit `cash_control` `$125.50`, credit `unapplied` `$125.50`.
  - **Mapped GL journal candidate (`mapping_version=1`):**
    - Debit `1090 · Undeposited Receipts / Cash Clearing (Cash)` `$125.50` (`12550` cents)
    - Credit `2310 · Unapplied Customer Receipts Clearing` `$125.50` (`12550` cents)
    - *Boundary:* Neither `1090` nor `2310` is bank-settled cash or contractual
      principal/interest reduction.
- **Source event 2 (`DemoPosting #802`, reversing `#801`):**
  - `kind='reversal'`, `reverses_id=801`, `payment_method='cash'`,
    `amount_cents=12550` (`$125.50`), `effective_on=2026-11-03`,
    `reason='Posted to wrong synthetic account'`.
  - **Mapped GL journal candidate (inverted from `#801`):**
    - Debit `2310 · Unapplied Customer Receipts Clearing` `$125.50` (`12550` cents)
    - Credit `1090 · Undeposited Receipts / Cash Clearing (Cash)` `$125.50` (`12550` cents)
- **Future allocation & settlement stages (currently gated/unimplemented):**
  - **Contractual allocation** (splitting `2310 · Unapplied Customer Receipts`
    into BHPH Contracts Receivable Principal, Earned Finance Income / Unearned
    Discount, and Permitted Fees) requires reviewed Chapter 520 / Reg Z contract
    rules and a separate allocation posting type.
  - **Bank settlement / deposit reconciliation** (clearing `1090 · Undeposited
    Receipts` into `1010 · Operating Bank Account`) requires a separate
    deposit/settlement reconciliation record tied to bank statements or payment
    processor batches.

---

## 4. Source-event provenance and idempotency

Every generated GL export line or journal batch entry must carry immutable
provenance back to its authoritative Railet source row:

- `dealership_id`
- `destination_ledger_id` (target accounting book/integration identifier)
- `source_domain` (`vehicle_cost` or `bhph_posting`)
- `source_record_id` (`VehicleCostEntry.id` or `DemoPosting.id`)
- `source_request_key` (UUID)
- `reverses_source_id` (`reverses_id` if `kind == 'reversal'`, else `null`)
- `mapping_version_id` and `mapping_rules_sha256` (retained as provenance of which mapping version translated the source event)
- `vehicle_id` / `stock_number` (for vehicle costs) or `book_id` / `customer_id` (for BHPH postings)
- `effective_on` (accounting effective date) and `entered_at` (system entry timestamp)
- `actor_id` (user who recorded the source posting)
- `amount_cents` (positive integer) and `debit_account_code` / `credit_account_code`

### Stable deduplication identity and controlled remapping

- **Mapping-independent deduplication key:** The canonical export identity for a
  source event is `(dealership_id, destination_ledger_id, source_domain, source_record_id)`
  (or `{dealership_id}:{destination_ledger_id}:{source_domain}:{source_record_id}`).
  It intentionally **excludes** `mapping_version_id`. Including
  `mapping_version_id` in the deduplication key would allow the same source
  event to be re-exported under a new mapping version as a distinct key and
  double-posted.
- **No silent re-export under a new mapping:** Once a source event has been
  committed to a `destination_ledger_id` under `mapping_version_id = N`,
  activating `mapping_version_id = N + 1` must **not** re-emit that historical
  source event under the new accounts. Reclassifying an already-exported entry
  requires an explicit, audited reclassification/adjustment or linked
  reversal-and-repost workflow approved by the owner/CPA, with its own distinct
  source adjustment ID.
- **External importer limits:** An export key in Railet's file or payload does
  **not** by itself make an external accounting system idempotent. Unless a
  verified provider API enforces unique external transaction IDs, preventing
  duplicate GL postings requires Railet's own export-ledger state tracking plus
  post-import reconciliation against the external GL trial balance/journal.

---

## 5. Reconciliation rules and exception classifications

The proposed reconciliation would compare the designated operational
subledgers against the dealership's external GL trial balance / journal export
as of a cutoff date. Comparisons would use integer cents, and discrepancies
would be classified and retained rather than silently adjusted:

1. **`unmapped_category_or_method`:** A `VehicleCostEntry.category` or
   `DemoPosting.payment_method` has no active rule in the selected
   `AccountingMappingVersion`. Batch export fails closed until mapped.
2. **`baseline_vs_itemized_gap`:** A vehicle has non-zero legacy
   `Vehicle.acquisition_cost` or `Vehicle.recon_cost` fields that are not
   represented as `VehicleCostEntry` rows. Reconciliation reports baseline
   amounts and itemized journal totals in separate columns so staff and the CPA
   can see whether a vehicle's purchase/recon was entered on the vehicle form or
   in the itemized register.
3. **`unapplied_receipt_balance`:** Net credit balance in `DemoPosting.Bucket.UNAPPLIED`
   representing receipts recorded in Railet that have not yet been contractually
   allocated to principal/interest.
4. **`unsettled_cash_control`:** Net debit balance in `DemoPosting.Bucket.CASH`
   (`cash_control`) that has not been matched to a bank deposit or processor
   settlement batch.
5. **`backdated_entry_cutoff_skew`:** Entries where `effective_on <= cutoff_date`
   but `entered_at > previous_export_timestamp` (backdated into a prior period
   after that period was exported). Reconciliation flags these explicitly so the
   accountant can post an adjusting entry in the open GL period rather than
   mutating closed periods.
6. **`reversal_period_straddle`:** An original cost or receipt has
   `effective_on` in Period A, and its linked `reversal` has `effective_on` in
   Period B. Both entries remain immutable in their respective effective periods
   with cross-linked IDs.
7. **`external_gl_only_or_missing`:** A journal entry exists in the external GL
   export with no matching Railet `source_record_id`, or a Railet posting is
   missing from the external GL export.

---

## 6. Permissions, isolation, and cutover ownership

- **Permissions and dealership isolation:**
  - Viewing and exporting future accounting reconciliation reports or GL batches
    would require an active same-dealership membership (`owner` or an authorized
    accounting role; never cross-dealership). An accounting role is not currently defined.
  - Creating, activating, or superseding an `AccountingMappingVersion`, or
    approving a cutover reconciliation, would be restricted to active dealership
    **owners** (`Membership.Role.OWNER`) with CSRF protection, signed preview
    confirmation, and immutable audit events.
- **Proposed cutover and authoritative-ledger boundary (subject to owner and CPA approval):**
  - During Phase 4 migration/pilot cutover (`RAILET_PLAN.md` § 4), the
    dealership owner and CPA must sign off on a written cutover plan, timestamp,
    and boundary between operational subledgers and the general ledger. The
    following sequence is a design proposal, not a settled business decision:
  - **Before cutover (proposed):** The legacy DMS / external accounting system
    remains the sole authoritative record; Railet runs only in synthetic or
    parallel-verification mode without initiating customer charges or live GL
    postings.
  - **At cutover (proposed):** Each open vehicle's cost baseline and each open
    BHPH account's opening balance is imported with explicit source provenance,
    reconciled to the cent against authorized legacy exports, and logged with an
    exception register for any unverified or disputed item.
  - **After cutover (proposed, pending CPA/owner sign-off):** If approved by the
    dealership owner and CPA, Railet's append-only subledgers (`VehicleCostEntry`
    and the reviewed production BHPH subledger) would serve as the operational
    subledger for new vehicle costs and customer receipts, feeding the
    dealership's general ledger via versioned journal exports while the CPA's
    general ledger remains the authoritative system for AP, payroll, bank
    reconciliation, tax adjustments, and financial statements. Two systems must
    never act as simultaneous uncoordinated authorities for the same subledger
    balance.

---

## 7. Unresolved dealer/CPA decisions and closed gates

Before implementing GL exports or any external accounting adapter (such as
optional QuickBooks integration):

1. **Dealer CPA review of chart-of-accounts structure:** Confirm which vehicle
   cost categories (`purchase`, `auction`, `transport`, `repair`, `parts`,
   `detail`, `other`) the dealership capitalizes into inventory vs. expenses,
   and how unitemized baseline costs (`acquisition_cost`, `recon_cost`) are
   handled at cutover.
2. **Reviewed BHPH contract and allocation rules:** Complete legal and financial
   review of precomputed vs. simple-interest accrual, unearned finance charge
   amortization, late fees, and Florida sales-tax/repossession credit rules
   (`Rule 12A-1.012, F.A.C.`).
3. **QuickBooks / external provider gate:** No QuickBooks OAuth credentials,
   API calls, SDKs, or webhook listeners are enabled or permitted until the
   mapping and reconciliation model above is reviewed by the dealership's CPA
   and security/provider terms are approved.
