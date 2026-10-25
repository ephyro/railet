# Internal deal follow-ups

A saved deal now links to **Follow-ups**, where owners/staff can add a title, optional details, optional owner and optional due date. These are internal work reminders only. They send no customer messages, run no automated collections, calculate no legal deadlines, and change no money, inventory or transaction state.

Owners/staff may create, edit, reassign, complete or reopen follow-ups within their dealership. Owners can be active owner/staff accounts in that dealership, or the task can remain unassigned. Read-only members may inspect tasks and their history but cannot write. All lists, detail pages, parent drafts and task editors are scoped on the server. Assignment is checked in both the form and the save path.

Home displays up to five open follow-ups assigned to the signed-in account, ordered by due date with undated tasks last, plus a link to the full list. The full list supports open/completed/all, assigned-to-me and per-deal scope with 25-row pagination. Overdue dates are identified in words, not color alone. No completion streak, urgency prompt or fake activity is added.

Task creation uses a per-deal UUID, protected by a unique constraint and the parent draft lock. A repeated identical submission returns the existing task; a reused key with different content/creator fails rather than creating another. Edits compare the task's own revision. Stale edits return 409 with entered values retained. No-op saves do not create fake activity. Atomic task events preserve recorded title/details, assignee ID, due date, completion actor/time and revision for each meaningful change. History paginates 20 events, and reopening clears current completion metadata while retaining the prior completion event.

Task changes do not increment the deal revision or create worksheet/financial events. An archived deal may retain and receive internal follow-ups without being restored; archiving does not silently complete or delete reminders. Canonical customer records and saved demo packets are not copied or altered. There are no task deletion endpoints. Privileged database writes remain able to alter records; no immutable audit infrastructure or record-retention/deletion policy is claimed.

Dates use the application's configured local timezone. Completion timestamps are recorded separately from due dates. No external calendar, email, SMS, telemetry, or provider integration is configured. Avoid private customer information in free text; the development build remains synthetic-only.

## Verification and integration

Eleven focused follow-up tests cover create/retry, creation-key conflict, assignment/completion/reopening history, stale/no-op updates, same-dealership active-editor assignment, role and dealership isolation, Home/list state and overdue filters, archived-parent behavior, audit rollback, escaping, CSRF/method/cache controls, and validation work preservation. The relevant follow-up/lifecycle/history run passed all 25 tests. Django migration drift checks passed.

Migration: `deals.0006_dealfollowup_followupevent_and_more`. It is applied to the separate synthetic SQLite preview database, not the primary development VM. PostgreSQL locking/concurrency integration remains unverified because the VM is unavailable in this environment. The full local SQLite suite passed 211 tests with 6 backend-specific skips (90.426 seconds); system checks passed. Firefox verified create/assignment on Home/complete/reopen and saved history, with form layouts at 1440,390,320 pixels and no horizontal overflow. These are developer checks, not staff usability validation or PostgreSQL verification. No public push or production deployment is performed.

## PostgreSQL integration follow-up

The subsequent isolated PostgreSQL 17.11 integration completed: all current migrations applied to a fresh synthetic database, the complete DMS suite passed 237 tests with no skips, and browser workflows passed on PostgreSQL. This supersedes the earlier lack of PostgreSQL runtime evidence for this source slice. The original offline VM and its existing data remain untouched and unverified for upgrade. See [POSTGRES_INTEGRATION.md](POSTGRES_INTEGRATION.md) for environment, concurrency, browser and synthetic restore evidence and limits.
