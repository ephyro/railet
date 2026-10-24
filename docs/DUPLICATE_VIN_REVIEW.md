<!-- SPDX-License-Identifier: MPL-2.0 -->
# Duplicate VIN review in ordinary inventory entry

October 24, 2026. Ordinary inventory create/edit now checks a new or changed
nonblank VIN against the same dealership's active and sold stock. Comparison
uppercases and trims surrounding spaces, including legacy stored values. Blank VINs
remain allowed and historical VIN formats are not forced into a modern format.
The edited record is excluded. An unchanged normalized VIN does not interrupt an
unrelated edit to a pre-existing duplicate record.

Matching records block the save until the operator deliberately acknowledges the
matches and enters a nonblank reason (up to 300 characters). Reacquisition or a
legacy correction may justify a separate stock record. This is an explicit,
audited exception, not a permanent bypass. Nothing is automatically merged,
reused, deleted or reassigned. Existing sale/deal history stays intact.

The server scopes matches to dealership membership and recomputes them on each
applicable POST. Submitted dealership or matching IDs cannot choose the evidence.
The same inventory audit event includes the actual matched record IDs, actor,
reason and vehicle changes; it commits atomically with the vehicle. A forged
acknowledgement on a nonconflicting save has no duplicate-review audit metadata.
Stale revisions and failed audit writes cannot save an override.

Ordinary inventory POSTs lock the dealership before acquiring an editable vehicle
lock or checking matches. Trade intake uses the same dealership lock. This closes
the concurrent check/insert race among these entry paths. Trade intake's existing
hard block remains; it does not gain this override. Matching data shown is bounded
to 20 records while audit evidence records all matched IDs. GET forms take no row
locks. No schema, license, finance calculations or production gates change.

## Limits and remaining pilot gates

This addresses the ordinary-entry gap noted in DEVELOPMENT_REVIEW_2026-10-24.md;
that report describes the earlier observed behavior and remains unchanged as
historical evidence. There is no universal VIN unique constraint, bulk repair,
canonical physical-vehicle identity model or automated reacquisition accounting.
Model writes through unreviewed admin/import/direct database tools can bypass this
form workflow and must use equivalent controls before they are enabled. Existing
duplicates still need human reconciliation before a live inventory pilot. A
reviewed separate stock record is not a determination of title ownership,
accounting treatment or document compliance. All existing production gates stand.

## Verification and delegated work

Luna implemented the bounded form, view, template, matcher and tests. The local
model provided a narrow design review identifying concurrent creates, changed
match sets and legacy/sold stock as edge cases. It did not perform a code audit or
run tests; its suggestions were independently assessed. The overseer corrected a
mixed-race test's revision expectation, reviewed the source diff, added independent
changed-evidence/whitespace-reason cases and verified the integrated workflow.

Independent results: all 130 PostgreSQL tests passed, including ordinary/ordinary
and ordinary/trade-intake concurrent submissions. The three overseer cases passed
on local SQLite: recomputed changed evidence without foreign IDs, disappearing
matches ignoring old override metadata, and whitespace-only reason rejection.
Luna's focused local suite passed 27 tests with the two PostgreSQL-only races
skipped there. Migration-drift check reported no changes.

Firefox verified same-dealer sold matches, preservation of entered fields,
unselected acknowledgement by default, missing reason rejection, explicit
acknowledgement/reason save with the reason visible in activity, and unrelated
edits with an unchanged VIN. The original sold record remained intact. Layouts
at 1440, 390 and 320 pixels had no horizontal page overflow. Checks created only
two clearly synthetic stock records; existing owner review deals were not edited.
These are developer checks, not staff usability or legal validation.
