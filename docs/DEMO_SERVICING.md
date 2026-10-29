# Monthly precomputed servicing simulation

Scope: explicitly synthetic, opt-in installment-coverage simulation. Never a live contract, principal/earned-interest allocation, payoff, late-fee assessment, collection instruction or bank reconciliation. Existing receipts remain unapplied in the authoritative ledger.

## Primary-source review (October 27, 2026)

| Authority | Observation / applicability | Control and verification | Unresolved production gate |
| --- | --- | --- | --- |
| CFPB [12 CFR 1026.18(g), (h), (k)](https://www.consumerfinance.gov/rules-policy/regulations/1026/18/) current official presentation | Closed-end credit disclosures distinguish payment schedule, total payments and prepayment treatment; do not apply open-end/card allocation provisions to auto installment contracts by analogy. | Simulation labels retain schedule totals and never claim APR/legal disclosure or payoff. | Transaction applicability, effective text/session history and reviewed disclosures before live use. |
| Florida [2026 §520.09](https://www.leg.state.fl.us/Statutes/index.cfm?App_mode=Display_Statute&URL=0500-0599/0520/Sections/0520.09.html) official text retrieved | Prepayment in full before maturity can require unearned-finance-charge credit. | Scheduled remaining total is not a payoff; no refund/rebate formula implemented. | Counsel must reconcile federal requirements, applicability and effective amendments before payoff implementation. |
| Florida [2026 §520.085](https://www.flsenate.gov/Laws/Statutes/2026/520.085) official text retrieved | Simple-interest contracts are separately addressed. | Only explicit monthly precomputed supplied-charge schedules are eligible; no automatic conversion of simple-interest illustrations. | Contract/rate/deferral/fee review remains open. No statutory dollar limits are implemented here. |
| FAC [69V-50.100](https://flrules.org/gateway/ruleNo.asp?id=69V-50.100) | Current retrieval failed. Earlier research recorded a development notice, not an adopted allocation rule. | Do not claim a legally mandated allocation order from that draft. | Current adoption/effective-date verification and alternative authorities remain unresolved. |

The retrieved compilations are research evidence, not verified transaction-effective legal approval. No new production gate is satisfied by this feature. The algorithm below is an explicit demo assumption, not Florida law.

## Demo policy: monthly-oldest-first-v1

- Explicitly select one immutable, verified monthly precomputed illustration for a synthetic account. No automatic selection of an alternative schedule. Store actor, timestamp, reason, version, schedule digest and retry key. The baseline cannot be edited or replaced by ordinary writes.
- Use the supplied total finance charge and exact installment cents already retained by the schedule engine. No new APR, earnings split or principal balance formula.
- Cover oldest outstanding installments first. An early/extra payment may cover future installments; excess after the full schedule remains simulated excess. This is not early payoff or principal-only curtailment.
- Partial payments leave the remainder on that installment. Include installments due on/before the as-of date in demo amount due. Past due includes strictly earlier dates; due today is not past due. Days past due uses the oldest unpaid past date with no contractual grace assumption or late fee.
- Full linked reversals remove their receipt's coverage as of the reversal's effective date. Reproject the schedule; preserve all original ledger entries. No partially editable receipt.
- Include only records entered by an explicit server capture timestamp and effective by the as-of date. Historical effective-date views are not a claim about what staff knew then. Store/display the capture timestamp where evidence is inspected.
- Keep installment coverage, remaining scheduled total, net eligible receipts and simulated excess separate. Never label schedule covered as paid off.
- Red + text: Demo past due. Amber + text: Demo due today. Green + text: Demo up to date / Demo schedule covered. Missing/unselected/invalid baseline remains neutral, never green.

## Independent reference cases

Use literal scheduled amounts $100 on February 1, March 1 and April 1 (not the implementation's calculation formula). On March 2: no payments -> due $200, oldest 29 days overdue in 2026; $40 paid -> due $160; $150 paid -> due $50 with oldest March 1, 1 day overdue; $250 paid -> due $0, $50 left on April 1; $325 paid -> schedule covered, simulated excess $25. Reversing $150 restores $200 due when effective; a future-effective reversal does not erase today's coverage. Due-date equality produces Due today, not Past due. Independent existing $366.67/$366.67/$366.66 residual case remains conserved.

## Implemented controls and verified operation

- DemoServicingPlan persists one explicit monthly precomputed source per account, schedule hash, fixed policy version, reason, actor, timestamp and retry key. Book locking and uniqueness prevent competing selections. PostgreSQL/SQLite reject ordinary update/delete and unauthorized/mismatched/non-monthly insertions. No contract amendment workflow is implied.
- Signed previews are actor/dealership/book/policy bound and expire after 30 minutes. Edit returns to preparation; retries retain the original selection. Viewers cannot select baselines, foreign accounts remain inaccessible, and CSRF is required. The feature uses DEMO_SERVICING_ENABLED plus the existing ledger demo gate; both default off outside DEBUG.
- Read-only effective-date coverage includes an explicit recorded-through timestamp, rejects pre-opening/future as-of dates, and fails neutral on invalid source/record-limit failures. Opening principal is verified against the retained illustration before projection. Current account views hold the book lock; account lists lock selected book IDs in order, refresh financial facts and bulk-read selected plans/postings. Limits: 600 installments, 10,000 postings per projection, 50,000 postings per list batch. These are computational scope, not statutory limits.
- Red amounts and labeled badges show Demo past due; amber is Demo due today; green is Demo up to date or Demo schedule covered. Account overview includes the next/oldest unpaid date. Unselected/invalid accounts remain neutral. All figures are expressly synthetic installment coverage, not posted principal/interest allocation.
- Portable account export v3 preserves the baseline metadata alongside original schedules and journal. Existing export audit rows are unchanged.

Verification: full PostgreSQL suite **350 tests passed in 115.246s**, no skips. Independent literal arithmetic references cover missed/partial/extra/early/full coverage, final cents and excess; effective dates and record captures cover linked reversals. Integration tests cover unchanged principal/unapplied ledger balances, signed preview/edit/retry, immutability, direct insertion guards, scope/permissions, monthly-only selection, source digests, portable baseline metadata, and red list status. Two PostgreSQL concurrency tests verify one selection for the same preview and rejection of competing previews.

Browser checks created two separate invented accounts and used actual illustration creation -> baseline preview/edit/confirm. Verified red past due, amber due today, green up to date and neutral unselected accounts; account, coverage and list views at 1440/390/320px had no outer overflow. Final checks verify due amounts themselves use the matching red/green colors and show the next unpaid date. Existing user test accounts were not selected or modified. Ignored evidence: `.local/servicing-review/` and `.local/servicing-tests.log`.

Django system checks passed; migration consistency reports no changes; migrations finance 0011 and 0012 applied to the local development preview. These are developer checks, not professional legal/financial approval or staff usability validation. Live servicing, earned-interest/principal allocation, fees, refunds, payoff, default/collections and simple-interest servicing remain disabled.

## Payment-impact preview

Receipt review now compares today's simulation before/after a virtual proposed receipt, including effective date, installment links, per-payment excess and any redistribution caused by backdating. The virtual receipt exists only in memory. All actual receipts still post wholly unapplied. Unknown/unselected baselines show the ordinary receipt review rather than invented coverage.

Preview preparation and confirmation lock the book. Signed previews include a digest of the selected plan/policy, local as-of date and captured journal facts. Changed journal/baseline/day requires a fresh reviewed preview (409, no new posting). Same-key confirmed retries return the original receipt, and re-preparing an already-recorded same-key payment cannot double-count it. Edit retains amount/date/reference/key and returns to preparation. This adds no new allocation/fee/payoff rules or production permissions.

Payment-impact verification: full PostgreSQL suite **359 tests passed in 138.058s**. Seven new reference/integration cases verify independent $200 -> $50 due for a $150 payment, linked installment amounts, final scheduled excess, five-row/full-detail visibility, backdated redistribution, neutral unselected/disabled behavior, baseline changes after preview, edit preservation and already-recorded retries. Two PostgreSQL concurrency tests verify one receipt for a shared preview and a fresh-review 409 for competing distinct previews. Posted principal remains unchanged and receipts remain wholly unapplied.

Browser verification used one separate invented account: preview/edit, an independently recorded synthetic concurrent receipt, updated 409 review without stale posting, final confirmation and same-token retry returning the original receipt. Final ledger principal remained $1,000 and net unapplied funds $950. Final layout checks at 1440/390/320px show the before/after comparison within the first 900px and all three coverage columns without sideways scrolling. A final 15-test payment/view run passed after text/layout refinement. Evidence: ignored `.local/payment-impact-review/`. No production deployment or live payment processing.

## Linked reversal-impact review

Reversal review now includes the selected original receipt, effective date,
required reason, and today's before/after due and status using a virtual full
linked reversal. Remaining receipts are replayed; the installment table shows
net coverage lost, not an assertion that the original receipt's old coverage
must all become due. Simulated excess changes are shown separately. No journal
entry is created during preview, and no principal/interest allocation, refund,
provider action, fees or production permissions are introduced. Existing
regulatory research and unresolved production gates above remain applicable;
this work does not adopt a new statutory allocation or delinquency rule.

Book locks and the signed plan/date/journal digest now protect reversal reviews
as well as receipt reviews. Changed facts require a refreshed preview before
posting; already-reversed receipts cannot be previewed twice, and identical
confirmed retries return the original receipt with its linked reversal. Wrong
keys/facts are rejected. Receipt and journal views retain links to the original
and show the correction's actor, entry timestamp, effective date and reason.
Unknown/unselected or disabled simulations retain the ordinary linked reversal
review without invented due/status figures.

Reversal verification: full PostgreSQL suite **369 tests passed in 142.863s**,
with no skips. Ten new cases include literal $0 -> $200 due when reversing a
$200 receipt, remaining-receipt replay with $50 due, excess-only changes,
unchanged original/principal and balanced linked postings, reason/date/edit
validation, same-key retries, competing correction rejection, permissions,
CSRF, disabled/unselected simulation and two PostgreSQL confirmation races.
Browser verification used a separate invented account: $900 receipt reversal,
edit, concurrent $50 receipt, refreshed $0 -> $850 review, confirmation and
idempotent retry, linked evidence and payment history. Existing accounts were
not corrected. Final preview-only layout checks at 1440/390/320px kept the
comparison within the first 900px and all coverage columns visible without
horizontal scrolling. Evidence: ignored `.local/reversal-impact-review/`.
These are developer checks; staff usability and professional review remain
outstanding. No live payment/provider/refund action or public deployment.

## BHPH status worklist (October 28, 2026)

The account list now has All/Past due/Due today/Up to date/Not calculated
shortcuts, visible sort selection, the next unpaid installment date and direct
Record payment links for authorized editors. Unknown or unverifiable baselines
stay neutral under Not calculated; Up to date also includes fully covered demo
schedules, without claiming payoff. Next unpaid date may be in the past and is
not represented as a promised future payment. The list omits unapplied funds to
keep the worklist focused; each account still shows its authoritative unapplied
ledger amount. No due/status rule, fee, grace period or collection behavior changes.

Status filtering and Oldest overdue first sorting use the existing verified
simulation across all matching candidates before pagination. This avoids filtering
only the visible page or treating receipt totals as contractual payment allocation.
Past-due records sort by oldest unpaid date, then stable account ID; due-today,
current, covered and uncalculated accounts follow in that order. Other sorts keep
their existing meaning. Clicking Past due selects oldest-overdue ordering when
starting from the default recent sort. Search, typed rules, context scopes and
saved views preserve status/sort; saved views are dynamic and private.

The worklist bounds a status/sorted search to 500 matching accounts and 50,000
captured postings, with existing per-account projection limits. Exceeding a batch
limit hides results with a narrowing instruction, not partial matches or invented
green statuses. Ordinary unfiltered browsing keeps its paginated path. Matching
book locks are acquired in ID order before refreshing records and reading the
shared baseline/journal capture; writers use the same locks. Large datasets will
need a separately designed scalable projection before increasing these bounds.
List projections omit full coverage tables to limit retained memory. Viewing this
worklist does not post, modify a schedule or queue customer contact. Existing
regulatory research and unresolved production gates remain unchanged.

Worklist verification: full PostgreSQL suite **384 tests passed in 176.074s**,
no skips; 18 focused SQLite worklist/search cases passed. Eight new tests cover
literal partial/due-today/current/covered/unknown cases, global filtering before
pagination (including an older match hidden beyond the ordinary first page),
stable tied dates, dynamic private saved views after payment/reversal, preserved
search/rules/scopes, invalid source neutrality, candidate/journal limits and
read-only role/gate enforcement. Existing receipt activity is still tested in
SQL and unapplied totals remain visible and verified inside the account.
Browser checks used one separate invented due-today baseline, no new receipt:
past due selects oldest order, amber due today shows $100, current remains green,
unknown remains neutral, tab changes retain search and the payment link opens
the correct account with a blank amount. Migration consistency: no changes.
Evidence: ignored `.local/account-worklist-review/`. This is developer
verification, not staff validation or permission for live collections.
Final layout checks at 1440/390/320px also verify search and sort controls each
remain at least 140px wide, actions do not overlap and the document does not
scroll sideways. No production deployment or public push was performed.
