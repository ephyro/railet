# Florida dealership record-retention research and release gates

**Research baseline: November 7, 2026; targeted source and code review: November 13, 2026. Status: preliminary; no operational retention schedule is approved.** This is an engineering research register, not a legal opinion, complete inventory of obligations, or certification. Applicability depends on the entity, record, transaction, dates and other duties. The design proposal below supports synthetic-only development; Florida dealer/finance counsel, privacy counsel and a Florida CPA must review applicability, effective dates and overlapping duties before operational use or disposal is enabled.

**Do not implement a universal five-year deletion period or automated purging.** A minimum retention period is not automatically permission to destroy a record. No live-data or deletion gate is changed by this research.

## Source and date limits

The Florida citations below refer to the **2026 Florida Statutes** as retrieved, not a claim that every provision first took effect in 2026. Verify the session-law history and effective date for each affected transaction before implementation. In particular, [chapter 2026-14, section 19](https://laws.flrules.org/2026/14) amends § 212.13(5)(f), concerning audit procedure, not the retention sentence in § 212.13(2); the [Senate identifies May 12, 2026 as its effective date](https://www.flsenate.gov/Session/Bill/2026/00104). No other specific historical effective date is inferred merely from a compilation. Counsel must verify historical versions, later changes and transition rules.

The eCFR results reviewed identified themselves as current through November 2 for title 49, November 3–4 for title 12, and November 5 for title 16, 2026; recheck later amendments before use. eCFR is continuously updated and unofficial. For rule 12A-1.012, the official [rule history page](https://flrules.org/gateway/RuleNo.asp?id=12A-1.012) identifies April 16, 2018 as the latest final rule's effective date, but its linked final-text Word file could not be opened by the research tool. The [2018 proposed text](https://flrules.org/Faw/FAWDocuments/FAWVOLUMEFOLDERS2018/4410/4410doc.pdf) is **not** treated as adopted text. The current DOR forms and instructions independently establish the form guidance described below; exact adopted subsections and any subsequent change remain to be checked from the final file.

## Record-category research matrix

| Category and primary source | What the source says; limitations |
| --- | --- |
| **Florida dealer transaction record** — [§ 320.27(6)](https://www.leg.state.fl.us/Statutes/index.cfm?App_mode=Display_Statute&StatuteYear=2026&URL=0300-0399/0320/Sections/0320.27.html), 2026 compilation. | A licensee keeps the specified purchase, sale, exchange and receipt-for-sale book or record, including listed vehicle, party, temporary-tag and title-transfer details, for **five years**, in paper or electronic form as prescribed or approved by FLHSMV. The text does not specify one clear start event for every entry: the trigger for particular transactions remains unresolved. For an in-state purchaser, the provision permits destruction of original paper when the licensee maintains electronic records after successful title **and registration** transfer under chapter 319. For an out-of-state/country purchaser it specifies delivery of the lawfully reassigned title or manufacturer’s certificate/statement of origin **and** electronic images of all sale documents before original papers may be destroyed. Other overlapping obligations may apply. Counsel and FLHSMV must resolve scope and timing before implementation. |
| **EFS scanned originals** — [FLHSMV EFS-02](https://www.flhsmv.gov/pdf/proc/efs/efs-02.pdf), revision 10/23, stated effective immediately. | For the listed documents, as applicable, submitted by EFS agents and approved by the tax collector or license plate agent, section D says destroy **or otherwise render invalid** within **five business days of transaction approval**. If retained, the agent must mark the face VOID or INVALID; if destroyed, it says the documents **should** be shredded and properly disposed of. This is not an unconditional shredding command or a rule for every dealership record. Confirm current procedure, the agent's role, documents and interplay with other obligations with FLHSMV and counsel. |
| **Odometer disclosures and specified powers of attorney** — [49 C.F.R. § 580.8(a), (c), (d)](https://www.ecfr.gov/current/title-49/subtitle-B/chapter-V/part-580/section-580.8); [2019 final rule](https://www.govinfo.gov/content/pkg/FR-2019-10-02/html/2019-20360.htm). | Covered dealers/distributors retain copies of issued and received statements, and received powers of attorney under §§ 580.13–.14, for **five years**, with the jurisdiction-retention exception in (d). They must be kept at the primary place of business for systematic retrieval. Electronic statement copies must be unalterable and indicate attempts to alter; the POA provision specifies **unauthorized** attempts. Section (d) assigns the stated electronic-title/electronic-POA disclosure retention to the jurisdiction for at least five years and permits dealer copies; it should not be generalized to every POA or jurisdictional record. Exact start triggers, applicability and technical controls require review. The eCFR text was checked; verify the 2019 rule’s effective and transition dates against the transaction. |
| **Chapter 520 licensed business books/accounts/records** — [§ 520.997(1), (3)–(5)](https://www.flsenate.gov/Laws/Statutes/2026/0520.997), 2026 compilation. | A chapter 520 licensee preserves and makes its books, accounts and records available for examination for **at least two years after the final entry therein**. Which entry is final for each record, and whether a charge-off is final, are not determined by this source; later entries or other obligations may extend practical retention beyond five years after sale. Subsection (4) authorizes rulemaking about record contents and destruction; the applicable current OFR rules remain unverified. Subsection (5) concerns notice when **the licensee itself** is subject to bankruptcy; it is not a customer-bankruptcy retention-hold rule. |
| **Florida sales/use tax books and records** — [§ 212.13(2)](https://www.flsenate.gov/Laws/Statutes/2026/212.13), [§ 213.35](https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0200-0299/0213/Sections/0213.35.html), [§ 95.091(3)–(4)](https://www.flsenate.gov/Laws/Statutes/2026/95.091), 2026 compilation. | Section 212.13(2) requires specified dealer records for the period in § 213.35. Section 213.35 ties preservation to expiration of the department's assessment period under § 95.091(3). For taxes due on or after July 1, 1999, the general assessment period is **three years from the latest** of tax due, return due, or return filed; § 95.091(3)(a)1.a–b and (3)(b) qualify this. Exceptions include assessment while a refund/credit right remains available, certain nonpayment, missing or fraudulent returns subject to the written-disclosure exception, and erroneous refunds; subsection (4) addresses tolling for specified review proceedings. Other provisions or agreements can matter. **Three years is not a universal deletion date**; the assessment limitation is relevant because § 213.35 incorporates it. CPA review must determine the period for each tax and record. |
| **Federal consumer credit records** — [Regulation Z, 12 C.F.R. § 1026.25(a)](https://www.ecfr.gov/current/title-12/chapter-X/part-1026/subpart-D/section-1026.25); [Regulation B, 12 C.F.R. § 1002.12(b)](https://www.ecfr.gov/current/title-12/chapter-X/part-1002/subpart-A/section-1002.12). | Reg Z generally requires **evidence of compliance**, subject to the listed exclusions, for **two years after the date disclosures are required or action is required**, not necessarily when actually provided or taken; enforcement agencies may require longer. Reg B generally requires specified consumer-application records for **25 months after notice** of action or incompleteness; existing-account adverse actions have their own notice trigger, while certain other applications use receipt as the trigger. Business-credit exceptions, including (b)(5) and subpart B, must be evaluated separately. Section (b)(4) requires covered records to be retained beyond the normal period after specified actual notice of an investigation/enforcement proceeding or service of a qualifying action, until final disposition unless earlier release is allowed by agency or court order. Counsel must assess whether the dealer is the creditor and which records and exceptions apply. |
| **Customer information disposal** — [FTC Safeguards Rule, 16 C.F.R. § 314.4(c)(6)](https://www.ecfr.gov/current/title-16/chapter-I/subchapter-C/part-314/section-314.4); [FTC dealer guidance](https://www.ftc.gov/business-guidance/resources/automobile-dealers-ftcs-safeguards-rule-frequently-asked-questions); [§ 501.171(8)](https://www.flsenate.gov/Laws/Statutes/2026/501.171), 2026 compilation. | For a covered financial institution, the FTC rule requires procedures for secure disposal of customer information no later than **two years after last use in connection with providing a product or service**, unless necessary for business operations or other legitimate business purposes, required by law/regulation, or targeted disposal is not reasonably feasible because of how the information is maintained. Periodic retention-policy review is also required. This is not a universal two-year deletion command and its application to inquiries, applicants, backups and the software provider is unresolved. Florida requires covered entities or third-party agents to take reasonable measures to dispose of covered customer records when they are no longer to be retained, using the statutory unreadability standard. Scope and interplay with other duties require privacy counsel's review. |

### Statutes of limitation are not retention schedules

[§ 95.11(2)(b)](https://www.flsenate.gov/Laws/Statutes/2026/95.11) generally provides five years for an action founded on a written instrument, with stated exceptions, including certain deficiency-judgment and payment-bond claims. [§ 95.051(1)(f)](https://www.flsenate.gov/Laws/Statutes/2026/95.051) lists payment of principal or interest on an obligation founded on a written instrument among tolling circumstances. Accrual, tolling, the claim type and applicable exceptions need counsel's fact-specific analysis. Neither provision by itself imposes a five-year contract-record retention duty or authorizes deletion after a claim deadline. Tax assessment periods above are distinct: § 213.35 expressly uses the assessment period to define its preservation duty.

## Repossessions: rule and current form evidence

- The official [FAC rule history for 12A-1.012](https://flrules.org/gateway/RuleNo.asp?id=12A-1.012) identifies **April 16, 2018** as the latest adopted version, but the linked final text was inaccessible in this research environment. Exact final rule subsection text, eligibility, record-retention wording and any amendments not reflected in that result are **unresolved** until the official final text can be read and checked. The proposed text is not proof of adoption.
- DOR's [current DR-95B, revision 01/19](https://floridarevenue.com/Forms_library/current/dr95b.pdf), labeled effective 01/19, is the **Schedule of Tax Credits Claimed on Repossessed Tangible Personal Property**, including motor vehicles. Its instructions describe a credit or refund for eligible financed repossessions and state a claim deadline of **12 months following the month of repossession**. This is a claim deadline, not a records-retention period. Review the rule and a specific transaction with a CPA; do not implement a calculator or claim from this summary.
- DR-95B's instructions say to keep the completed schedule in the books and records for a return credit; for a refund, attach the completed schedule and required documentation to [DR-26S, revision 01/24](https://floridarevenue.com/Forms_library/current/dr26s.pdf), and retain copies. DOR's [DR-26SN, revision 01/24](https://floridarevenue.com/Forms_library/current/dr26sn.pdf), identifies supporting materials for repossession refunds, including the financing agreement, tax return, accounting records, payment history and repossession/ownership evidence. Confirm the latest forms, exact applicability and required evidence before filing.
- DOR's [forms index](https://floridarevenue.com/Pages/forms_index.aspx) lists DR-95B. A separate [DOR refund-help page](https://taxapps.floridarevenue.com/Refunds/Help/Repossess.aspx) still suggests the older DR-95A and uses an older DR-95B title. Treat that apparent conflict as **unresolved**; the older PDF's existence is not proof it is currently required. Obtain DOR/CPA confirmation rather than directing users to submit both forms.

## Holds, unresolved work and software gates

- Do not assert a blanket bankruptcy, litigation, investigation or audit hold solely from § 520.997(5). Reg B's specific notice rule is described above. Counsel must determine other preservation duties, triggering facts, duration and affected records; do not treat all holds as identical.
- Confirm § 320.27 record-specific clocks, EFS-02 applicability and document-destruction interactions; independently verify any reliance on the Dealer Handbook, FLHSMV TL-02 or RS-31. Those sources are not relied on for unverified retention or form claims here.
- Verify current OFR chapter 69V-85 requirements, federal odometer exceptions and electronic controls, credit-record categories, legitimate business purposes, tax assessment extensions and backup/immutable-ledger disposal. Shared customer records may be subject to multiple record-specific obligations and holds.
- Legal and CPA review, explicit record classification, tested holds, backup/restore implications, supervisory approval and record-specific disposal rules remain **open**. The prototype has no automated retention purge. Do not infer that every other form of deletion is disabled or that stored prototype records are compliant merely from this statement.
- An owner-only synthetic data export is not an approved statutory inspection packet or a production backup. Any future inspection/disposal workflow requires a separate verified design and explicit release authorization.

## November 13 source verification limits

This is a targeted recheck, not a refresh of every November 7 citation. The current
[Florida Senate § 320.27(6)](https://www.flsenate.gov/Laws/Statutes/2026/320.27),
[§ 520.997(3)](https://www.flsenate.gov/Laws/Statutes/2026/520.997) and
[§ 213.35](https://www.flsenate.gov/Laws/Statutes/2026/213.35) were accessible and
support the dealer-record, final-entry and tax-assessment distinctions above.
Their transaction-specific historical effective dates and intervening session-law
review remain unresolved; the 2026 compilation is not that verification.

The retrieved [Reg B text](https://www.ecfr.gov/current/title-12/chapter-X/part-1002/subpart-A/section-1002.12)
and [Reg Z text](https://www.ecfr.gov/current/title-12/chapter-X/part-1026/subpart-D/section-1026.25)
displayed currency through November 9, 2026; [odometer retention](https://www.ecfr.gov/current/title-49/subtitle-B/chapter-V/part-580/section-580.8)
displayed November 10. The applicable historical effective/transition dates and
changes after those currency dates remain unresolved. Reg B § 1002.12(b)(4)
provides a specific preservation trigger for qualifying actual investigation or
enforcement notice, or service of a qualifying action; retain covered information
until final disposition unless an agency/court order permits earlier release.
This is not authority for a universal hold duration.

The direct [§ 314.4 rule-text request](https://www.ecfr.gov/current/title-16/chapter-I/subchapter-C/part-314/section-314.4)
was blocked by an access challenge. Current [FTC agency guidance](https://www.ftc.gov/business-guidance/resources/ftc-safeguards-rule-what-your-business-needs-know)
was accessible and corroborates secure disposal tied to most recent customer
service use, with legal/business-need and targeted-feasibility exceptions. Exact
current rule text, applicable compliance dates and dealer/provider applicability
still require verification; this proposal does not authorize indefinite live-data
retention. The [12A-1.012 history page](https://flrules.org/gateway/RuleNo.asp?id=12A-1.012)
still lists April 16, 2018; its final-text link could not be resolved in this
recheck. Adopted wording remains unverified. EFS-02, tax exceptions, DOR forms and
other baseline sources were not rechecked here; their earlier limits remain.

## Stored-record mapping (design proposal; no clocks activated)

Code inspected: `core`, `customers`, `inventory`, `deals`, `documents`, `finance`
and `feedback` models, including `inventory/reconditioning_models.py`; their
`export.py` components; `core/dealership_export.py`; and
`dev/restore_exercise.py`. These are currently synthetic records, not evidence
that a regulated transaction occurred. References to researched duties below are
conditional mappings to the preceding source matrix, not new legal conclusions.

| Stored category | Candidate obligation and trigger evidence | Unresolved classification/control |
| --- | --- | --- |
| Vehicles, acquisition files, trades and inventory audit history | Dealer transaction-record candidate under § 320.27(6); optional `acquired_on` and staff-entered `sold_on` exist. | No verified title/registration transfer or temporary-tag event model; neither vehicle status nor these dates establishes the statutory clock. Reacquisitions need distinct transaction identity. |
| Vehicle photos/thumbnails, vendors/vendor events, recon tasks, costs/corrections and invoices | Invoices/costs may support tax records under § 213.35; acquisition evidence may overlap dealer records. | Photo/task/vendor periods not established; tax filing, due, assessment-extension and refund events are not modeled. Classify evidence by purpose, not file extension or completion date. |
| Customers, addresses, normalized contact fields, activities and change history | Shared identity and notes may support multiple transactions; covered customer information needs last-service-use/exception review under Safeguards research. | No authoritative last-service-use event. Lead stage, appointment completion, login, export or `updated_at` is not a substitute. Inquiry versus application/customer classification unresolved. |
| Draft deals, proposals, tax context, trades, follow-ups/events, completion/void/follow-on records | Possible future dealer, credit and tax evidence. Reg B notice/receipt triggers and Reg Z required-disclosure/action dates differ. | Draft/rehearsal completion is not consummation, a credit decision or notice. Required credit dates are absent; abandoned, declined, incomplete and withdrawn cases need separate classification. Void/archive does not start or end a legal clock. |
| Deal PDFs/events, acquisition PDFs/events, invoice PDFs/events | Content may include dealer, odometer/POA, tax or credit evidence; § 580.8 applies to specified disclosures, not every mileage field. | Current uploads are unverified supporting documents. Add reviewed category, issuer/recipient, issue/receipt and transaction evidence; upload time alone cannot start a legal clock. EFS originals versus electronic copies need separate custody and invalidation review. |
| Frozen packet JSON/HTML, versions/hashes, completion references | Historical facts and artifact provenance supporting the associated record category. | Retain exact captured versions and dependencies; do not rewrite snapshots when shared profiles change. These demo packets are not signed legal forms. Printed synthetic receipts are rendered views, not retained signed/issued receipt artifacts. |
| Demo books, balanced postings/reversals, account contexts, schedules and servicing plans | Future licensed-business candidate under § 520.997: at least two years after final entry; tax/credit evidence may overlap. | No approved final-entry determination. Zero balance, charge-off, reversal, illustration end or account export is not verified closure. Preserve full linked journal and calculation versions; resolve later adjustments and reopened accounts. |
| Customer, packet, account and dealership export events; module audit histories | Provenance for source records and preservation actions; hashes identify prepared exports. | No independent statutory period established for every event. Preparation is not proof of download/receipt; hashes cannot recreate past ZIP bytes. Avoid deleting history independently of its evidence dependencies. |
| Feedback reports and offline mock-message submissions/events | Internal reports/simulations; potentially relevant matter evidence if linked by a reviewed scope. | No sourced universal period. Mock delivery is not real communication or consent evidence. Restrict accidentally entered sensitive content and route for preservation/privacy review without erasing originals. |
| Dealership/membership/user provenance, saved views, sessions, credentials, synthetic MFA factors/events, operational logs | Administration/security categories require their own purpose and access review. | No general duration established here. Saved views are not transaction records by default. Credentials/secrets are excluded from ordinary exports; MFA free-form references cannot establish dealership scope. Secret rotation/revocation is separate from preserving authorized evidence. |
| Backup copies, private storage versions, downloaded exports and legacy source exports | Copies inherit applicable content obligations and matter scope. | No approved backup rotation or external-copy destruction schedule. Track custodians/storage and recoverability; orphaned blobs require investigation, not age-based cleanup. Legacy records need original trigger provenance, not import date. |

### Proposed classification and clock register

Foundation owns retention/hold metadata and exposes explicit module interfaces;
modules continue owning records and artifacts. No microservice or deletion job is
proposed. A record may have multiple obligations and holds. Store dealership,
module/type/stable ID, artifact/version/hash references, category, jurisdiction,
rule/version and authority, effective-date range, applicability decision/evidence,
responsible custodian/reviewer, trigger type, occurred-at and recorded-at dates,
source provenance, exceptions, last review and next review date. Preserve prior
assessments as appended versions. Missing or disputed trigger/applicability means
`unresolved`, with no calculated disposal date; never infer from row timestamps.

For reviewed rules only, calculate each obligation separately; all applicable
minimums, pending matters and exceptions must be resolved before any future
disposal review. Keep a separate privacy/legitimate-purpose review so a long
minimum does not justify keeping unrelated information indefinitely. Any future
review date is a review prompt, never a deletion instruction. No current record
gets a guessed period from this mapping.

### Proposed legal-hold placement and release

1. Staff can report a preservation concern privately; a designated same-dealership
   hold custodian can immediately activate a provisional hold while counsel
   evaluates it. Capture matter ID/type, reason, authority or instruction reference,
   notice/service and knowledge dates, custodians, record scope and reviewer.
   Litigation anticipation, audit, complaint, dispute, bankruptcy and agency notice
   are distinct review reasons; only the Reg B case above has a sourced trigger
   specified here. A preservation hold is separate from a servicing/contact stop.
2. Resolve scope into stable record/artifact IDs plus a versioned relationship rule
   for future related records. Include historical snapshots, archived attachments,
   relevant journal/corrections, events and known copies. A customer hold may span
   buyer/co-buyer deals and accounts; a vehicle hold may span reacquisitions. Preview
   affected records/counts and unresolved links without exposing another dealership.
   Unresolved scope blocks future disposal of candidate records pending review.
3. Proposed states: `active provisional`, `active confirmed`, `release requested`,
   `released`. Review dates never expire a hold. Narrowing scope is a partial release
   requiring the same controls. New matter records inherit applicable active scope;
   changing relationships cannot silently remove preserved membership. Ordinary
   edits may continue only with preserved before/after evidence; immutable documents
   and financial postings keep their existing correction rules.
4. Release requires a recorded written decision from the designated legal reviewer,
   supporting disposition/order where applicable, and approval by a separate
   authorized dealership custodian. The requester cannot approve their own release;
   if no independent approver is available it stays active. Show matter, affected
   scope, other holds and unresolved obligations before confirmation. Release one
   hold only, preserve its history, and reevaluate every other obligation. Release
   never deletes records or authorizes disposal. Mistaken release is corrected with
   a linked reactivation event, not by overwriting the decision.

These roles and dual approval are engineering proposals, not statutory role
requirements or implemented permissions. Enforce dealership isolation and distinct
place/review/release privileges server-side; ordinary staff/viewers cannot release.
Log actor ID and role at action time, event/recorded times, reason, evidence
reference, scope additions/removals, before/after state, policy version, approvals
and rejected attempts. Preserve actor provenance after account deactivation.
Sensitive legal instructions stay in restricted evidence storage; routine screens
show only necessary hold status. Audit and state changes must commit atomically,
with idempotent requests, revision checks and serialization against scope changes
and any future disposal evaluator. Audit failure rolls back the action. Existing
inventory-specific `AuditEvent` is not a general legal-hold log; a future dedicated
append-only hold history needs DB guards plus privilege and tamper-evidence review.

### Proposed export, backup and exception controls

- Preserve authorized access/export while a hold is active; hold status does not
  grant download rights. A future export version must include authorized retention
  assessments, hold membership and release provenance, capture boundaries, artifact
  versions/hashes and omissions. Restrict privileged matter evidence separately;
  record recipient/custodian and preparation versus confirmed delivery distinctly.
  Existing module/dealership exports have no hold metadata and are not inspection
  packets or complete backups. Size/integrity errors must not silently omit held data.
- Current exports include archived records, private photo originals/thumbnails,
  three PDF categories and frozen packet HTML, but exclude secrets, sessions,
  personal saved views, orphaned storage and prior ZIP bytes. Multi-query/file
  reads do not give a coordinated snapshot. A hold needs a consistent evidence
  capture and gap report, not reliance on an export hash or ordinary archive flag.
- A future backup catalog must identify database/media versions, encryption-key
  recovery custody, copy location, custodian, capture range and holds affecting
  rotation. Suspend conflicting expiration/overwrite pending scoped preservation
  review; avoid claiming every backup must be held forever. Reconcile current hold
  and release history from a separately protected authoritative register after
  restore and before reopening writes or any future disposal evaluation. An older
  backup must not erase newer holds or resurrect a released state incorrectly.
  Test DB plus private bytes and required keys together. The existing disposable
  synthetic restore exercise does not test hold replay or live preservation.
- Downloads, staff printouts, legacy exports and provider copies need recorded
  custodians and acknowledged preservation/release instructions; Railet cannot
  remotely guarantee recall or erasure. Business closure, staff departure or a
  hosting migration must transfer custody without losing access or evidence.
- Multiple holds release independently. Reopened accounts, late entries, returns,
  repossessions, refund/tax examinations and amendments require reassessment, not
  reset-to-today of every clock. Duplicate/merged identities must retain source
  links; missing files, corruption, cross-dealership links and unscoped MFA/orphaned
  artifacts go to restricted exception review. Do not repair history by deleting it.
  Paper-original invalidation under EFS and preservation of copies require a
  specific reviewer decision; a generic hold flag must not silently settle a conflict.
- Erasure/privacy requests, accidental sensitive uploads and retention exceptions
  require recorded legal/privacy review with least-privilege access while unresolved.
  No automatic redaction, anonymization, encryption-key destruction, cascade delete,
  storage lifecycle purge or backup expiry is authorized by this proposal. Existing
  failed-upload cleanup and unrelated application deletion paths are not certified
  hold-aware; inspect them before implementing preservation enforcement.

### Existing removal and cleanup inventory

On November 15, 2026, a static source review identified these paths; none consults
an operational legal hold. The offline rehearsal below does not protect records.

- `core/filter_views.py` physically deletes a user's dealership-scoped saved view
  on request. Its name and filter parameters can contain user-entered text, and
  personal saved views are excluded from the synthetic dealership export.
- Draft-deal archival, trade removal, inventory-photo hiding and deal/acquisition
  file archival update retained records rather than deleting their files. They can
  change which records are visible or current, and are not hold-enforcement controls.
- `inventory/photos.py` and the document upload services attempt to delete newly
  written blobs after failed uploads. These paths do not check holds. Cleanup can
  itself fail. Photo uploads reject outer transactions so a later outer rollback
  cannot silently orphan successfully written files. These paths are not scheduled
  retention or disposal workflows.
- `dev/restore_exercise.py` creates and cleans up its own disposable synthetic
  PostgreSQL cluster and media workspace. It retains the workspace if it cannot
  confirm the cluster stopped; abrupt termination may also leave it behind.
  `dev/restore_fixture.py` exercises database guards only in that isolated setup.

This inventory covered application source, project management commands, storage
helpers and the restore exercise, not an operational environment. Built-in or
third-party commands, direct database/storage administration, external lifecycle
rules, backups and provider copies were not verified. Existing foreign-key and
audit guards are not a general hold system. Reassess these paths and all copies
before relying on preservation enforcement; no disposal schedule is established.

### Acceptance and release gates (outstanding)

The offline `core/hold_rehearsal.py` now models invented identifiers, overlapping
holds, unresolved scope, independent release and reactivation as immutable
in-memory values. Explicit `enabled=True` is required for each operation. A clear
hold check is only a prompt for further review, never disposal eligibility; the
module has no database, application endpoint, deletion or retention calculation.
It does not implement legal-review roles, written decisions, persistence or access
controls. Five synthetic developer tests cover its state rules and structural
input validation; this is not legal
review or operational validation.

The operational design remains unimplemented; there are no persistent hold models, permissions, clocks
or release endpoints from this task. Future synthetic checks must cover shared
customers/co-buyers, archived files and frozen snapshots, overlapping/provisional
holds, scoped future-record inclusion, unauthorized/self/stale releases, audit
rollback, concurrent placement/release/scope evaluation, missing dates and imports,
reopened journals, export failures and restoration of newer holds over older
backups. Exercise both supported databases and private storage, with independent
expected scope manifests. No such runtime verification or dealership staff/legal
validation is claimed here. Counsel/CPA source and date review, operational owners,
privacy exceptions, backup policy and separately authorized implementation/release
remain open. Automatic deletion remains disabled; disposal is separate future work.
