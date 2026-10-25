# Archive and restore draft deals

Archiving is organization of an unfinished draft. It is not cancellation of a signed contract, refund, loan reversal, inventory reservation/release, sale, or trade-intake reversal. No new legal rule or live transaction is introduced.

## Staff workflow

Open a draft and choose **Archive draft**. The confirmation identifies the draft, vehicle and buyer, explains the effect, and requires a reason. Restoring requires its own reason. Both actions check the submitted revision and expected prior state. A repeated or stale submission returns 409 with the reason preserved; it cannot toggle the state or duplicate history.

Archived drafts disappear from the default active list. **Show drafts** selects Active, Archived or All; scope is part of reusable filter/saved-view parameters. Existing saved views without a scope default to active. Draft IDs and direct links remain accessible; customer profiles label archived linked drafts. Read-only members can inspect them but cannot archive or restore.

Archived worksheets and proposals are disabled, party editors reject changes, and trade edit/remove/intake routes reject writes. Server-side persistence also rejects stale draft objects attempting ordinary saves on an archived parent; transactional trade operations roll back if that guard rejects them. Restore before resuming these edits. A stale worksheet POST is rejected with an explanation and a Back-button path to recover entered work.

Shared customer/inventory profiles remain authoritative and independently editable; archiving a draft does not freeze those canonical records. Supporting files keep their existing scoped upload/archive/restore behavior; archiving the draft is not a document retention or access restriction. Saved packets stay accessible, retain their exact bytes, and have no edit/delete actions. A new demonstration packet may still capture an archived draft; template `demo-summary-v2`/snapshot schema 2 explicitly records its state. Older artifacts are not regenerated.

## Integrity and history

Archive time, actor, current reason and a revision increment are saved atomically with a DealEvent. New event snapshots use schema 4 and include archive metadata; earlier snapshots are untouched. Restore clears current archive metadata but preserves the original archive event and adds a separate restoration event with actor/reason/time. Amounts, customers, inventory status, trade intake records, and packet bytes are not modified by these actions. Audit failure rolls back state and revision.

Server authorization requires owner/staff membership in the same dealership. Lifecycle preview fails closed on corrupt cross-dealership vehicle/customer references. POST locks take dealership before parent draft, matching packet creation and inventory intake; trade POST routes now use this same ordering to avoid an inverted dealership/parent wait. PostgreSQL concurrency behavior still requires runtime verification.

Application interfaces preserve history; privileged direct database writes can change records. No deletion schedule, legal hold management, event tamper-proofing, or database-level immutable storage is claimed.

## Verification

Nine focused local tests cover archive/restore metadata and reasons, fixed money/reference balance, unchanged inventory, revision/history, retry/stale state rejection, role/dealership/CSRF/method controls, default/explicit lists, archived worksheet/party/trade blocking, stale persistence guard, and audit-failure rollback. A further corruption test covers cross-dealership live references.

The focused lifecycle/deal/trade/packet run passed 73 tests with 2 backend-specific skips before the final corrupt-reference hardening. The full local SQLite suite passed 186 tests with 6 backend-specific skips before the final cross-reference hardening. The final lifecycle/packet run passed all 22 tests, including the additional corrupt-reference case. Django system/migration drift checks passed. SQLite does not verify PostgreSQL locks. The primary development VM remains unavailable; migration `deals.0005_draftdeal_archive_reason_draftdeal_archived_at_and_more` has been applied only to the isolated synthetic local preview database.

Firefox checks in that isolated database exercise confirmation, archive, disabled inputs, archived list, preserved version-1 packet text, restore and unchanged price. Confirmation layouts were checked at 1440,390,320 pixels. These are developer checks, not staff validation or production acceptance. No public push or deployment occurred.

## PostgreSQL integration follow-up

The subsequent isolated PostgreSQL 17.11 integration completed: all current migrations applied to a fresh synthetic database, the complete DMS suite passed 237 tests with no skips, and browser workflows passed on PostgreSQL. This supersedes the earlier lack of PostgreSQL runtime evidence for this source slice. The original offline VM and its existing data remain untouched and unverified for upgrade. See [POSTGRES_INTEGRATION.md](POSTGRES_INTEGRATION.md) for environment, concurrency, browser and synthetic restore evidence and limits.


Deal history schema 5 adds the proposed interest method. Older saved snapshots retain their original schema and contents.
