# BHPH account workspace (synthetic development)

This workspace joins existing records without creating a loan or a second customer database. It is available through **BHPH demo** navigation and existing customer profiles when the synthetic-ledger gate is enabled. Opening balances still require explicit invented provenance; no draft worksheet is silently converted into debt.

## Record responsibilities

- Customers own current contact details. The workspace links the authoritative customer record; it does not duplicate or freeze a contact profile.
- Deals expose an explicit read interface for eligible BHPH drafts and their proposed facts. Only active drafts in the same dealership with this account's customer as buyer and a vehicle in that dealership are eligible.
- Finance owns the existing synthetic book, journal and schedule illustrations, plus a one-time immutable `DemoAccountContext`. That context preserves vehicle identity, draft/revision references, title brand and proposed terms. It is context only, not a contract, legal amount financed, selected schedule or origination event.
- The link preview is actor/dealership/book bound and expires after 30 minutes. Saving rechecks the current draft and digest under locks. Changed details require a fresh preview. Repeating the same save returns the saved context; another draft cannot replace it. PostgreSQL validates insertion scope; PostgreSQL and SQLite reject ordinary updates/deletes. Privileged database administrators can bypass these controls.

The workspace reads opening principal and net unapplied receipts from the existing ledger. It does not subtract unapplied receipts from principal. Alternative schedule illustrations remain forecasts using the opening amount, not schedules adjusted by actual payments. No amount due, next-payment status, delinquency, paid-through date, APR or payoff is inferred.

## Payment rehearsal

1. Open an account and choose **Record demo payment**.
2. Enter invented amount, effective date and reference. Review the financial consequences before posting.
3. Confirm once; retries reuse the same posting. The workflow opens that posting's private demo receipt.
4. Open receipts from payment history. A full linked correction marks the original receipt corrected without changing its amount or reference. Corrections continue to use the existing reviewed preview and append-only reversal flow.

Receipt views are generated from retained journal entries, not a finalized statutory receipt template or immutable HTML artifact. Current customer/user names can change; stable record identifiers, original posting amount, reference, actor and timestamps remain identifiable. They are clearly synthetic and do not establish bank settlement or receipt of real funds.

## Design decisions

Preserve Railet's existing system font and palette: ink `#202b27`, green `#285b44`, muted text `#657069`, separators `#e1e6e1`, paper `#f7f8f6`, white surfaces. Use left-aligned customer/vehicle identification, payment history as the main work area, and a quieter side column for opening figures and frozen proposed terms. Keep a single primary payment action. On narrow screens, stack identity and columns; preserve labeled links and visible keyboard focus. Avoid dashboard metrics that could look like a legally meaningful amount due.

This follows the current synthetic boundaries in [schedule methods](SCHEDULE_METHODS.md), [ledger foundation](LEDGER_FOUNDATION.md) and the [compliance plan](RAILET_PLAN.md). No new contractual allocation, lending rule or legal interpretation is activated. Live servicing, contractual calculations and legal receipt/statement requirements still require the applicable reviews. Developer tests and browser checks do not constitute staff or legal validation.

## Verification evidence

Focused PostgreSQL regression run: 66 tests passed across finance, customer workflows and financing proposals. The 12 new account tests also passed on SQLite, including database immutability checks. Browser rehearsal linked synthetic draft #1 to synthetic account #1, recorded a $10.25 demo receipt, opened it directly, and reversed that same entry. The original receipt stayed intact and opening principal remained unchanged. Workspace and receipt views were checked at 1440, 390 and 320 pixels, with desktop/mobile screenshots inspected. Private evidence is under `.local/account-review/`; no real customer records or funds were used.


BHPH workspace verification: the complete PostgreSQL suite passed **273 tests** in 124.795 seconds, with no skips. Synthetic account/browser evidence is retained privately under `.local/account-review/`.

## Open directly from a saved BHPH draft

An active BHPH draft now offers **Open a demo BHPH account from this draft**. Customer and vehicle come from the saved authoritative records; staff enter an explicit invented opening amount, effective date and source, then review the proposed facts and financial consequences before confirming. No amount is prefilled from the worksheet and no real customer debt is inferred.

Confirmation atomically creates the synthetic book, its balanced opening journal entry, and the frozen draft context. Any failure rolls back all three. Actor/dealership/draft-bound previews expire after 30 minutes. The service locks the dealership and draft, rechecks proposed facts, and rejects stale previews. Repeating a completed request returns its original account even if later draft edits occur; a reused request key with changed opening facts is rejected.

A draft can be linked to only one demo account. This is an anti-duplication product rule, not a lending rule. It is enforced by a database uniqueness constraint and by both the original linking interface and new opening service. Existing duplicate links would cause the migration to fail rather than silently delete or merge financial records; reconcile them explicitly before retrying a deployment. The current synthetic database was checked and contained no duplicate links.

After creation the draft links directly to its saved account. The account's existing schedule, payment preview, private receipt and linked-correction workflows remain available. Creating the account does not finalize the draft, originate a loan, generate reviewed legal paperwork, mark inventory sold or record a payment. The live-servicing and legal-review boundaries above remain unchanged.


October 26 draft-opening verification: the complete PostgreSQL suite passed 285 tests in 111.229 seconds with no skips, including same-key and distinct-key concurrent opening cases. Ten focused SQLite tests passed. Synthetic browser checks covered draft → reviewed opening → account navigation at 1440/390/320 pixels; no outer page overflow was found. These are developer checks, not staff or legal validation. Private evidence: `.local/draft-opening-review/`.

Account discovery now supports customer, recorded vehicle, stock/VIN and exact account-number search, quick linked/unlinked scopes, advanced rules and private saved views using the shared filter engine. See [account search](ACCOUNT_SEARCH.md) for read boundaries and verification scope.

A private account export is now available from Account figures. See [portable account export](ACCOUNT_EXPORT.md) for exact JSON/CSV scope, snapshot consistency, privacy, file hashes and the append-only export audit. It is not a complete dealership backup or legal statement.

The account list also links to a dealership-wide [synthetic payment register](PAYMENT_REGISTER.md). It separates recorded/effective dates and shows receipts, corrections and net activity for a selected range without treating that net as a balance or settlement.
