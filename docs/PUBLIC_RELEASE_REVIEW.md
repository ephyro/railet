# Current-tree public-release exclusion review

November 14 follow-up: the active development directory has no `.git`, but a
separate clean checkout at `.local/public-source` has three non-shallow commits.
Its `origin/main` was checked against the remote and matched commit
`a98760444c80e6e4b68e11bd5c46650b7ab0b683`; only `main` was advertised as a
branch or tag at that check. A historical filename search for common private
capture, credential and backup names found only `.env.example`. A narrow scan of
all three commits for private-key headers, GitHub token prefixes, AWS access-key
IDs and live provider-key prefixes reported no matches. These checks do not
establish that history or release contents are clean: renamed files, other secret
formats, customer data, provenance, rights and remote refs outside advertised
branches and tags remain unreviewed. The checkout was not changed or published.
Among its 343 tracked paths, 122 differed from the development tree, 221 matched,
and none were missing at this check; untracked development paths were not counted.
Review an explicit proposed release and its complete diff before publication.
The same narrow pattern scan was also run against the 492 tracked or nonignored
candidate paths in the development tree: no matches were reported and one
binary or unavailable path was skipped. This is not a comprehensive secret or
personal-data scan. A read-only ignore check matched representative capture,
environment and local database names; ignore rules cannot clean tracked history.
A second heuristic scan found five files with credential-assignment-shaped text
and ten files mentioning the vendor reference; these require human review in
context. No SSN-shaped string was found by that narrow pattern. Four of the
credential sites were password literals in test files containing synthetic markers;
a test session-key literal and settings match also require contextual review.
No matched values were printed. These patterns cannot establish absence of real
customer data, credentials, copied assets or sensitive information.
Additional candidate-tree checks found no matches for selected cloud-token and
JWT shapes; the one private-IP-shaped match was in the DocuSeal URL rejection
test. An email-domain inventory found no domains outside example/test domains,
apart from an intentionally invalid subdomain in a URL validation test. These
are heuristics, not exhaustive identity or credential checks. The checked
credential-assignment matches were test setup and the development-only fallback
in Django settings; values were not printed. `.env.example`'s password field
was empty or marked as a placeholder. `pip check` passed. A trailing blank line
at the end of `deals/models.py` was removed; `git diff --check` then passed for
tracked files. New files require separate whitespace checking.

`detect-secrets` scanned the 492 candidate paths and flagged seven lines in four
files: CI/test-only credentials, a mock URL/secret and the development settings
fallback. Context was inspected without printing matched values; settings require
a supplied secret when debug is disabled. A separate scan of explicitly enumerated
archive files from each available commit (343, 257 and 158 files) reported no
findings. These scanner results are heuristics, not proof that all secrets,
personal data, copied material or provenance issues are absent.

November 13, 2026: source/metadata review only, not release approval. No files
were removed, no Git commands were run, and nothing was packaged or published.
The development directory did not expose usable Git history during that review.
The separate checkout identified above now supplies limited history for review.
Do not initialize a replacement repository to bypass history review.

## Evidence and changes

Inspected `.gitignore`, `.dockerignore`, both Dockerfiles, release/licensing
sections of `AGENTS.md`, `RAILET_PLAN.md`, `CONTRIBUTING.md`, `SECURITY.md`,
`THIRD_PARTY_NOTICES.md`, the MPL license heading and application source notice
markers. Private captures, environment files, databases and local hosting state
were inspected by names/sizes or aggregate extension counts only; their contents
were not opened. No credentials or customer information were printed.

| Observed inclusion gap | Correction / remaining limit |
| --- | --- |
| Development `Dockerfile` uses `COPY . .`; `.dockerignore` excluded `DealerCenter*` but not the saved Deal Reports HTML/assets. | Excluded Deal Reports and BHPH Reports names and nested capture patterns. Git already excluded the root report captures; added nested counterparts. Renamed captures still require review. |
| Root `old.html` and `old_files/` were not excluded by either file; metadata shows HTML/JS/CSS/image assets. | Excluded both pending provenance review. Metadata cannot establish whether they are proprietary, vendor-derived or independently written; no such ownership claim is made. |
| `.wrangler/` contains local hosting state and was not excluded. | Excluded it from both channels. No hosting configuration or state contents were inspected. Proprietary website files under other names remain an unresolved packaging risk. |
| Docker context lacked exclusions for credential directories/keys, logs, SQL/dumps and ordinary build/test output already ignored by Git. | Added explicit context patterns, including nested credential/environment paths, keys, dumps, caches and generated media/static output. Existing private files remain untouched. |
| SQLite sidecars, other local database suffixes, compressed SQL, backup suffixes and export directories lacked explicit coverage. | Added targeted Git/Docker patterns. Arbitrarily named ZIP/CSV/JSON/PDF/data files are not proven safe; no broad rule silently excludes all legitimate fixtures/assets. |
| Third-party notice said no private captures were included, without distinguishing the working tree from a distribution. | Qualified the statement and linked this review. Keep MPL, dependency notices and the bundled Manrope OFL notice in intended distributions. |

Git ignores and Docker context exclusions are different controls. Neither removes
already tracked content, cleans history, filters an ad-hoc archive, or controls
files mounted later at runtime. The staging Dockerfile uses explicit application
copies, but copied source trees still require content/provenance review. Local
backup paths may be configured outside the defaults; ignore patterns are not a
retention policy or permission to delete any backup.

## License and fixture limits

`LICENSE` identifies MPL 2.0; its complete text was not compared byte-for-byte
with upstream in this review. `static/fonts/Manrope-OFL.txt` exists. A marker scan
of application/source roots found 279 Python, 3 shell, 101 HTML, 21 CSS and 7 JS
files, including empty Python files. Among nonempty files, seven generated Python
migrations lacked `SPDX-License-Identifier: MPL-2.0` within their first 1,000
characters: `core` migrations 0004/0006, `customers` 0003/0004/0006/0008, and
`documents` 0004. Marker absence is not a determination of licensing or authorship;
resolve attribution/notice coverage before release, without assigning unverified
copyright or changing contributor licensing. No notices were stripped or licenses
changed. Dependency artifact licenses, native libraries, images and commercial
extension boundaries need separate verification of the exact release artifacts.

### Seven migration notice follow-up — November 14, 2026

Reviewed the complete source of exactly these seven migrations:

- `core/migrations/0004_dealershipexportevent.py`
- `core/migrations/0006_syntheticmfafactor_syntheticmfaevent.py`
- `customers/migrations/0003_customeractivity.py`
- `customers/migrations/0004_customeractivity_assigned_to_and_more.py`
- `customers/migrations/0006_customerexportevent.py`
- `customers/migrations/0008_mockmessagesubmission_mockmessageevent_and_more.py`
- `documents/migrations/0004_vehicleinvoice_vehicleinvoiceevent_and_more.py`

Each contained a Django-generated header and application schema operations, with
no existing SPDX or copyright marker. `AGENTS.md` requires covered-file notice
preservation; `RAILET_PLAN.md` calls for file notices/SPDX identifiers, and
`CONTRIBUTING.md` declares inbound MPL 2.0 while preserving contributor copyright.
The root license and neighboring migration notice convention identify MPL 2.0.
On that available project-policy evidence, added only
`# SPDX-License-Identifier: MPL-2.0` to each file. This records the project's
declared community license, not new authorship, copyright assignment, an alternate
license or permission for proprietary relicensing. Original generated headers and
every original byte after the added line were preserved; Python AST comparisons
confirmed unchanged migration behavior. No migrations or runtime tests were run.

Result: the seven missing file identifiers are resolved. Contributor identity,
third-party provenance, any historical notices or licensing exceptions, and
authority for any historical contribution remain unverifiable from this checkout;
a generated header is not proof of rights. The `.git` directory remains empty.
Obtain original history/contribution evidence before treating attribution and
release rights as verified. No Git initialization, commit or publication occurred;
the broader release gate remains open.

Synthetic development policy does not prove every file contains invented data.
Test/seed source is intended for synthetic use, but fixtures, free text, screenshots,
exports and documents need deliberate content review before inclusion. Do not
publish actual records even when labeled demo. Keep `.env.example` available as a
Git setup template only after checking its values; actual `.env` files stay private.
This review did not open either file's contents or classify database contents.

## Checks and remaining release gates

November 14 Docker semantics follow-up: [Docker's build-context documentation](https://docs.docker.com/build/concepts/context/#dockerignore-files)
specifies root-relative matching using Go `filepath.Match`, with Docker's `**`
matching zero or more directories; a bare pattern such as `__pycache__` is not a
recursive basename rule. Added `**/__pycache__`, `**/.wrangler`, `**/*.qcow2`
and `**/*.iso` to cover nested equivalents. Existing `**/DealerCenter*`, report,
environment and key patterns cover root and nested names under those documented
semantics. The earlier Python `fnmatch` checks did not implement Docker matching
and must not be treated as proof. New static checks use path-segment matching for
the patterns present, including zero/multiple `**` segments and directory parents;
they are not Docker's matcher or a build. No Dockerfile-specific ignore files were
found in the visible tree; such files take precedence if added later. Named contexts
and arbitrarily renamed private files require separate review.

Targeted static pattern checks cover representative root/nested captures,
credentials, SQLite sidecars, dumps, exports and legacy/hosting paths, while
retaining application source and license/notice paths. These are pattern checks,
not Docker build, archive inspection or Git tracked/history validation. No real
data, credential, backup, proprietary-asset content scan or secret scanner was run.
No symlinks were found in the inspected application/source roots; this is not a
whole-tree symlink or external-target audit.

Before any separately authorized publication: complete review of the available
checkout's history/refs and tracked content; resolve legacy and proprietary asset
provenance; inspect intended release contents with restricted data/secret handling;
verify `.env.example`, synthetic fixtures and notices; and review the exact archive
or image produced by an explicit inclusion manifest. Exclusions reduce accidental
inclusion but do not certify any artifact clean. History review, content review,
notice resolution and publication authorization remain open. Production, live-data
and legal/financial release gates are unchanged.

November 14 license-text comparison: the repository `LICENSE` and Mozilla's
official MPL 2.0 plain-text copy were the same length but not byte-identical.
The observed line diff consisted of one trailing space and the Exhibit A URL
using `http` locally versus `https` in the current official copy. This comparison
does not establish rights in contributions or dependencies; preserve existing
notices and review the intended distribution and third-party licenses separately.

November 14 dependency check: `pip check` passed. A temporary `pip-audit` run
against the existing development virtual environment reported the same
`PYSEC-2026-3721` / `CVE-2026-13346` advisory twice for its pip 26.1.2
installer; the [PyPA advisory](https://github.com/pypa/advisory-database/blob/main/vulns/pip/PYSEC-2026-3721.yaml)
lists 26.2 as fixed. The local installer was upgraded to 26.3, and the repeat
audit reported no known advisories among 11 installed distributions. This is a
point-in-time audit of that environment, not a lockfile, build-image audit or
guarantee about all versions permitted by `requirements.txt`.

The bundled `static/fonts/manrope.ttf` had the same SHA-256 as the Manrope
variable font retrieved from the Google Fonts repository on November 14; the
repository retains its OFL notice. Installed package metadata was inspected
against the project's notice table; this does not review native binaries or
container images. The README's PDF archive/restore statement was corrected to
distinguish deal/acquisition attachments from invoices.

The latest synthetic full-suite runs passed 716 tests on SQLite (60 skipped)
and PostgreSQL (2 skipped), using isolated test databases. These are developer
checks, not staff, legal, deployment or complete release-content review. The
active source tree was not committed or pushed.

The candidate was assembled against `a98760444c80e6e4b68e11bd5c46650b7ab0b683`
in a separate disposable worktree for inspection. Its 493 indexed paths matched
the development tree byte-for-byte at that check; the staged change covered
274 paths and `git diff --cached --check` passed. `detect-secrets` checked the
indexed files and reported the same seven reviewed test/development findings.
Neither the separate worktree nor the scanner establishes release safety, and
the development tree and original checkout were not overwritten.

A Bandit source scan of the application modules had no scan errors and no
high/medium findings outside tests and migrations. Its one low finding outside
those paths was the debug-only Django secret fallback; settings reject a missing
secret with debug disabled. Static analysis is not an independent security audit
and does not validate production configuration, package images or providers.
The README and documentation local-link check covered 135 links with no missing
targets. All 103 newly added Python files parsed successfully; a scan found no
trailing-whitespace lines in new text files. A source-import inventory found no
direct HTTP client, socket, SMTP or subprocess imports in non-test application
modules; the listed `urllib` uses require ordinary code review and do not alone
prove the absence of network access.

An independent release check found that the offline synthetic hold rehearsal
accepted a manually constructed `RELEASED` hold with an empty event history and
reported a hold-clear result. Structural validation now rejects that case,
inconsistent transitions, self-approved releases and mutable history/scope
containers; five focused tests passed. The check cannot authenticate a fabricated
but internally consistent history or establish authorization. The helper grants
no disposal authority and is not connected to a live workflow.

An independent service-boundary review found that deal-file upload and archive
operations trusted their caller's actor/dealership pair, and invoice upload did
not recheck active status. The HTTP entry points scoped records and required an
editor, but a revocation while a request waited on its parent lock could still
leave stale authority. Synthetic document mutation services now acquire the
dealership and parent locks before locking/rechecking an active editor; invoice
and acquisition operations use the same order. Forty-seven focused PostgreSQL
tests passed; a separate PostgreSQL lock-wait regression exercised role and
  active-status revocation before five mutation types and checked that role and
  active-status changes wait through three upload types once authorized.
  Forty-seven SQLite tests ran
with two backend-specific skips. These checks do not certify all administrative
lock orders, external storage behavior or production readiness.
