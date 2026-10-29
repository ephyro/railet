# Synthetic payment register

The BHPH account list now links to a read-only **Payment register**. It summarizes recorded receipts and their linked corrections across the current dealership's synthetic books. It is available to authorized readers under the existing `DEMO_LEDGER_ENABLED` gate, with private/no-store responses. No real funds, payment allocation, contractual calculation, collections or settlement behavior is activated.

## Date meaning and totals

The default view selects **Date recorded** for today. Staff can choose **Effective date** instead, with explicit From/Through dates. Recorded dates use the application's current time zone (normally America/New_York); each local day runs from local midnight to the next local midnight, including daylight-saving transitions. Effective dates are the date values explicitly supplied on postings. Both dates remain visible on each result.

Opening entries are excluded. Receipts and corrections are summed separately as integer cents; net effect is receipts minus corrections. A correction can refer to an original receipt outside the selected range, so a negative net is valid. It is not a negative customer balance, payoff, cash-drawer shortage or bank transaction. No payment method, settlement status, earned interest or principal allocation is inferred.

## Coherent read and scope

Authorized book/customer scope is applied before the date filter. The report captures up to 5,001 joined rows in one database statement, rejects a result over 5,000, and derives both totals and paginated display from that same bounded capture. It does not combine independently timed aggregate and detail queries. There are 25 rows per page; totals cover all rows in the capture. A new request/page can capture newly posted activity; this report is not a retained historical artifact or signed statement. Use the separate account export when a portable captured record is needed.

The date-range limit is 92 inclusive days and the supported rehearsal date range is 1900–2100, ending no later than today. These are implementation limits, not statutory retention or servicing rules. Invalid dates or excessive results retain filter entries, hide totals and explain how to correct the query. There is no misleading partial total.

The register reuses authoritative journal entries and source-receipt links. Correction amounts are shown with a minus sign and a textual correction label, not color alone. The table remains keyboard focusable and horizontally scrollable on small screens. No journal entries, financial events or balances are written by viewing this report.

This adds no dependency or new regulatory interpretation. RAILET_PLAN.md and LEDGER_FOUNDATION.md remain the production boundary; developer verification does not establish staff or legal validation.


Payment-register verification (October 26, 2026): the full PostgreSQL suite passed 312 tests in 111.993 seconds without skips. Nine focused tests passed on each PostgreSQL and SQLite. Checks cover independent receipt/correction totals, negative range activity, recorded/effective date separation, daylight-saving boundaries, single-query capture, dealership isolation, date validation, size limits and pagination totals. Browser checks verified the synthetic $74.50 net range, date switching and validation at 1440/390/320 pixels without outer overflow. This is developer verification, not staff or legal validation. Private evidence: `.local/payment-register-review/`.

## Daily payments and manually recorded methods (October 28, 2026)

The existing register URL is now labeled Daily payments and directly visible on
BHPH. Today uses date recorded in the application time zone. Previous/next day
navigation preserves date basis; Today resets it to date recorded. Custom ranges
and effective-date selection remain available, with invalid filters expanded and
no partial totals. Receipt/reversal/net totals appear before optional controls.
The method table and source-linked entries derive from the same bounded capture.

Receipts now retain a manual payment_method label: cash, check, other or
unspecified (displayed as Not recorded). Older entries receive unspecified;
no historical method is inferred from notes, names, amounts or debit buckets.
The field labels a synthetic receipt only; it does not process checks/cards,
verify tender, mark funds settled, reconcile banks or count a cash drawer.
Reversals copy the original method, and database insertion guards reject an
unknown method, a method on an opening, or a mismatched reversal. The existing
append-only triggers preserve the method once posted; retries with a different
method are rejected. Missing method input remains unspecified for compatibility
with older synthetic callers and already-issued signed previews.

Migration 0013 uses ALTER ADD COLUMN rather than recreating the immutable
posting table, preserving SQLite and PostgreSQL append-only guards and old
posting identities/amounts/dates. PostgreSQL removes the temporary migration
default afterward. An additional trigger enforces method validity and reversal
matching. No original financial posting is rewritten. Account export v4 adds
payment_method to JSON/CSV; existing export audit rows retain their original
version. Unspecified is unknown, not cash.

The date, amount, authorization, signature, retention and production boundaries
above and in LEDGER_FOUNDATION.md continue unchanged. This adds no regulatory
interpretation, payment integration, statutory calculation or production gate.

Daily payment verification: 26 focused SQLite tests passed, including unchanged
append-only posting behavior and method/reversal insertion guards. A scratch
SQLite 0012 -> 0013 upgrade retained the exact original posting values and both
book/posting immutability triggers. Local PostgreSQL migration retained all 24
pre-existing postings byte-for-byte in their old fields and the existing export
audit row; all old methods became unspecified. Migration consistency reports no
changes. Browser checks created one separate invented account, checked exact
$338.50 receipts / $100.25 reversals / $238.25 net and all four method buckets,
followed the linked reversal, and exercised Check selection through review,
edit and confirmation. At 1440/390/320px there is no outer overflow and summary
totals fit in the first 900px. Evidence: ignored `.local/daily-payments-review/`.
These are developer checks, not staff validation or bank reconciliation.

Full PostgreSQL verification: **376 tests passed in 115.096s**, no skips.
Seven new cases cover independent per-method arithmetic and grand-total ties,
reversals on a later day, method-sensitive idempotency and immutable metadata,
direct database insertion guards, preview/edit/confirm, empty-day navigation and
export v4. Existing timezone/DST, scope, row-limit, pagination, servicing and
concurrency cases remain passing. Final method rows put Cash/Check/Other before
Not recorded; default new entry still truthfully starts at Not recorded.
