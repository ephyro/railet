# Offline synthetic account reconciliation rehearsal

`finance.reconciliation.compare_synthetic` compares two explicitly supplied,
invented in-memory lists. It has no route, importer, database access, file or
provider access, posting, account creation or cutover action. It requires
`DEBUG`, `DEMO_LEDGER_ENABLED`, an explicit
`SYNTHETIC_RECONCILIATION_ENABLED=True` test setting, and the literal argument
`synthetic_only=True`; the additional setting is absent/disabled by default.
Use invented data only. Labels and gates cannot prove data is synthetic.

The source is the **comparison reference** for this exercise; the target is a
candidate. This convention does not establish either system as a legally or
operationally authoritative ledger. Each side supplies a distinct invented
provenance ID and the caller supplies one common ISO as-of date; neither dates
nor provenance are independently verified. IDs are case-sensitive and follow
`SYNTH-SRC-A`, `SYNTH-TGT-A`, `SYNTH-MAP-A`, and `SYNTH-PROV-SOURCE` patterns:
after each prefix use 1–20 uppercase ASCII letters only. A matching mapping ID
is an explicit test assumption, not identity matching or a verified crosswalk.
No names, account numbers, free-text references or customer identifiers belong
in this component.

Every summary has exactly `record_id`, `match_id`, `principal_cents`,
`interest_cents`, `fees_cents` and `unapplied_cents`. All four amounts are
separate, explicitly provided signed integers in cents or `None` for unknown; they are never inferred,
rounded, allocated or treated as a payoff. Zero is a value, not unknown. The
caller must choose inputs with consistent meanings; unknown figures are explicit
exceptions and require resolution outside this rehearsal. Record
amounts are bounded to ±999,999,999,999 cents; each side is limited to 10,000
records. Invalid shapes, extra fields, floats, booleans, malformed IDs/dates,
equal provenance identifiers and two empty lists raise an error with no report.

Results are deterministic regardless of input order. The report identifies
per-account mismatches, either-side missing accounts, duplicate record IDs,
duplicate mapping IDs, and explicitly unresolved `match_id=None` entries. A
duplicate or unresolved mapping blocks aggregate totals and produces an explicit
`aggregate_unavailable` exception; ambiguous records are not paired. With unique
mappings, totals are computed independently per side, including records missing on
the other side; an aggregate difference is an exception, and equal totals never
cancel per-account discrepancies. `comparison_complete` is false for unresolved,
duplicate or missing accounts or unknown amounts; `reconciled` is true only if no exception exists.
Version `synthetic-account-reconciliation-v2` records each unknown field with its
side, record and mapping identifiers, including unpaired records. A matched account
with unknowns and no known differences is `incomplete`; known differences remain
visible. For each aggregate field, a side with any unknown value has a `None`
total, and the difference is `None` whenever either side is unknown. Known fields
remain comparable. Ambiguous mappings still suppress the entire aggregate.
The report is a rehearsal result, not an approval or evidence of migration.

Before any actual migration, separately define verified source snapshots,
versioned mappings, identification and handling of unknowns, authorization and
privacy controls, individual and aggregate reconciliation, exception resolution,
source system evidence, cutover ownership, independent review and rollback.
Contractual balances, interest, settlement and production use remain gated.
