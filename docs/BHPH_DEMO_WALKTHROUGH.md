# Synthetic BHPH workflow review

This walkthrough demonstrates navigation and retained records across the end-to-end synthetic BHPH flow: **vehicle → customer → deal → synthetic completion rehearsal → BHPH account → test receipt → reversal**. It does not originate a loan, allocate payments, validate Florida paperwork, mark a vehicle sold, or permit real customer data. Use invented names and records only.

## Prerequisites

- Run the development build (`RAILET_DEBUG=1`), which enables the synthetic gates (`FL_TAX_ESTIMATES_ENABLED`, `RECON_DEMO_ENABLED`, `DEAL_FILES_DEMO_ENABLED`, `CUSTOMER_ACTIVITY_DEMO_ENABLED`, `DEMO_PACKETS_ENABLED`, `DEMO_COMPLETION_ENABLED`, `DEMO_LEDGER_ENABLED`, and `DEMO_SERVICING_ENABLED`).
- Sign in with an `owner` or `staff` account (`viewer` accounts are read-only and cannot save records, rehearse completion, open accounts, or post receipts; owner-only JSON/ZIP exports in Customers and Dealership export require an `owner` account).

## End-to-end walkthrough (owner or staff preparation)

1. **Add an invented vehicle and customer:**
   - Under **Vehicles**, choose **+ Add vehicle**. Enter an invented stock number, year, make, model, and optional asking price (for example, `$1,500.25`). Keep unknown title or mileage facts as `Not verified` / `Not recorded` rather than defaulting to reassuring values.
   - Under **Customers**, choose **+ Add customer** (or create one inline when starting a deal). Enter an invented name and optional contact details or sales lead stage.
2. **Start and save a BHPH draft deal:**
   - Open the vehicle and choose **Start a deal** (or under **Deals**, choose **+ Start a deal**), then select the customer.
   - Set **Deal type** to **Buy here, pay here**. Enter the worksheet amounts (for example, vehicle price `$1,500.25`, planned down payment `$300.00`, and either a 2026 Florida county tax estimate or a manual tax entry with an override reason). Saving a planned down payment does not record money received.
   - Under **Buy here, pay here terms** (`Financing details`), enter the proposed financing fields required before a completion rehearsal:
     - **Proposed interest method:** `Precomputed` or `Simple interest`
     - **Creditor or funding source:** e.g., `Synthetic BHPH Creditor`
     - **Payment frequency:** e.g., `Monthly`
     - **Number of payments:** e.g., `12`
     - **First payment date:** e.g., `2026-12-01`
     - **Precomputed finance charge** (if `Precomputed`, e.g., `$150.00`) or **Annual contract rate** (if `Simple interest`, e.g., `0.0000`)
   - Choose **Save deal**.
3. **Review the draft and freeze a synthetic completion rehearsal:**
   - On the deal worksheet, choose **Review deal** to open the read-only **Draft review**. Check the saved vehicle, buyer, worksheet balance, proposed financing terms, and completeness reminders.
   - In the **Next: rehearse completion** banner, choose **Review and freeze** (`/deals/<id>/completion/review/`). If any required financing or worksheet fields are missing, the page lists them under **Fix before continuing** with a **Return to deal worksheet** action.
   - If blank or unverified facts remain (such as unverified title brand or mileage), enter **Review notes** explaining them. Check both confirmation boxes (confirming you reviewed the saved facts and understand this only freezes a rehearsal) and choose **Save completion rehearsal**.
   - The deal moves to **Completed rehearsals** (`/deals/<id>/completion/`), locking its worksheet, parties, trade, and proposed terms, and preserving a frozen demo summary packet. The vehicle is **not** marked sold and no contract or loan is created. (While no BHPH account is linked, the completed rehearsal also offers **Review void rehearsal** to practice recording an immutable synthetic void reason that blocks later account handoff; do not void the rehearsal if you want to proceed to Step 4. A synthetic void is not a legal cancellation and does not adjust any payment or balance.)
4. **Open (or link) a synthetic BHPH account from the completed rehearsal:**
   - On the **Completed rehearsal** page, under **Next: demo BHPH account**, choose **Set up demo BHPH account** (`/deals/<id>/demo-account/`). (You can also open a demo account directly from an active BHPH draft before completion, or link an existing unlinked account for the same customer from `/bhph-demo/<account_id>/link/`; if an account was already opened from an earlier draft, the completed rehearsal links to that existing account and notes its saved context may precede the rehearsal.)
   - Enter an explicit **Synthetic opening principal (USD)** (for example, `$1,200.25`), an **Effective date**, and an **Opening-balance source (synthetic only)** reference, then check the synthetic-only confirmation and choose **Review account opening**. The opening amount is supplied explicitly for the rehearsal, never automatically copied from the draft balance into debt.
   - On **Review the demo account**, verify the frozen customer, vehicle, opening figures, and preserved proposed terms, then choose **Open demo account**.
5. **Record and verify a synthetic payment receipt:**
   - On the **BHPH account** workspace (`/bhph-demo/<account_id>/`), choose **Record payment**.
   - Enter `$25.50`, select a payment method, enter an effective date and invented reference, check the synthetic confirmation, and choose **Review demo payment**.
   - Try **Edit before posting** on the preview screen: the entered `$25.50` amount and fields remain populated so you can review again.
   - Choose **Record demo payment**, then open **View demo receipt** or **View payment history**. Verify the receipt is listed as **Unapplied**, **Opening principal** (under **Account figures and export**) remains `$1,200.25`, and **Unapplied payments** is `$25.50`. The payment has not reduced principal or allocated interest/fees, and no real money moved.
6. **Reverse the test receipt:**
   - From the receipt, choose **Reverse payment**. Enter today's effective date and an invented reason such as `Practice entry made by mistake`, confirm the synthetic-only acknowledgement, review, and confirm the full reversal.
   - The original receipt remains visible as **Reversed in full**, with a linked reversal and reason. **Unapplied payments, net of corrections** returns to `$0.00`; opening principal stays `$1,200.25`. This is an internal correction, not a refund.
   - A newly opened account has no selected demo schedule: **Amount due** is **Not calculated** and **Late status** is **Not assessed**. A separately selected demo schedule can show simulated coverage, not live servicing.
7. **Verify cross-record handoffs and idempotency:**
   - Return to the customer profile and completed deal rehearsal. Their BHPH account links open the same account (`Account #<id>`), and revisiting `/deals/<id>/demo-account/` redirects to the existing account rather than creating a duplicate.

## Uncoached staff review

Use the [staff workflow protocol](STAFF_WORKFLOW_TEST.md) for moderator setup, uncoached end-to-end tasks, observable checks and a private observation template. It also retains the separate prepared-account payment scenario. Do not call either workflow validated until staff have actually tried it.

Record only synthetic observations: the task, where the reviewer paused, the expected action, and the outcome. Avoid customer records, passwords and private vendor captures. Correcting a saved payment must use the linked correction workflow (`Reverse payment`), never an editable receipt amount.

## Developer verification

- **Browser and HTTP journey checks (developer-only, not staff validation):**
  - Exercised the full `vehicle → customer → BHPH deal → draft review → completion rehearsal → frozen summary → demo BHPH account opening → test receipt` journey in headless Firefox (at `1440px`, `390px`, and `320px` viewports) and via Django test client suites (`deals.test_completion`, `deals.test_review`, `finance.test_completed_handoff`, `finance.test_accounts`, `finance.test_print_receipts`).
  - Verified that incomplete BHPH financing proposals block completion rehearsal with explicit field names, that frozen completion rehearsals preserve buyer/vehicle/proposal snapshots even after shared profiles change, that `Edit before posting` on account opening, receipts, and reversals preserves form entries, and that recording a receipt leaves opening principal unchanged while increasing net unapplied payments.
  - All reviewed/demo exports (demo packet ZIP, account export ZIP, filtered report CSVs, and owner-only customer/dealership exports), completion/void rehearsals, and payment steps are synthetic evaluation tools only—they do not establish legal compliance, live servicing, complete production backup/restore, or dealership-staff usability validation.
  - See [November 2026 BHPH journey review](BHPH_JOURNEY_REVIEW_2026-11-03.md) and [November 2026 developer evaluation](EVALUATION_2026_11.md) for detailed browser evidence and remaining production gates.
