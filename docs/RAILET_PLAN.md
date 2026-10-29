# Railet: product, compliance, and business plan

Planning baseline: October 22, 2026. Owner: Ephyro. Product: Railet DMS, railet.com.

## 1. Product commitment

Build one coherent, modular DMS for Florida independent dealers with buy-here-pay-here operations. Begin at the founder's dealership, then validate with a small group of independent dealers. Community software will use MPL 2.0. Hosting infrastructure selection is deferred; local development, secure deployment requirements, and backup/restore design are not deferred.

Promise: enter facts once, produce consistent paperwork, understand every account balance, and retain control of your data. Success means staff can complete real work more easily with demonstrably correct results. Do not claim certification, guaranteed legal compliance, or guaranteed savings.

## 2. Architecture and module boundaries

Start with a modular monolith: one application and deployable release, a relational database, private document storage, and background jobs where needed. Prefer PostgreSQL for transactions and constraints. Select the application framework after a small inventory/document prototype, based on maintainability and contributor accessibility. Do not introduce microservices for the initial release.

Each module owns its records and exposes explicit application interfaces; cross-module changes go through those interfaces. Use database transactions for financial operations and an outbox for reliable external work. Version integration contracts. Enforce authorization on the server, not only in navigation. Keep dealership scoping in the data model; independently test isolation before shared hosting.

| Module | Responsibility |
| --- | --- |
| Foundation | Dealership, users, roles, MFA, audit events, settings, retention, search |
| Inventory | VIN, stock number, ownership/title evidence, title brands, odometer, costs, recon, availability |
| Customers | Buyers/co-buyers, contact data, consent, tasks, documents |
| Deals | Line items, fees/taxes, trades/payoffs, down payments, financing terms, approval and finalization |
| Documents | State/form versions, applicability, validation, generation, signed artifacts and delivery evidence |
| Servicing | Contracts, schedules, allocations, payments, reversals, delinquency and collections |
| Finance | Double-entry subledger, reconciliation, accounting mappings and export |
| Feedback | Private reports, sanitized diagnostics, feature requests and resolution tracking |
| Extensions | State packs and adapters for signing, accounting, lenders and payment providers |

Documents reference a consistent snapshot of the deal and vehicle at generation/signing. Subsequent edits never silently rewrite finalized artifacts. Template versions and calculation versions remain identifiable. Inventory's title brand must drive disclosure checks and applicable listing outputs; merely adding a form does not establish compliance.

## 3. Compliance implementation policy

This is an implementation roadmap, not a legal opinion or a complete list of applicable law. Obligations depend on the dealer's practices, transaction, customer and jurisdiction. The software vendor may also acquire direct duties when hosting data or operating services. Self-hosting and open source do not remove those duties.

Maintain a compliance register with: authority/link, applicable workflow, jurisdiction, effective date, exception, requirement, software control, operational owner, reviewer, test/evidence and next review date. Mark each rule researched, implemented, reviewed and verified separately. A statutory compilation may include changes with future effective dates; verify session laws and effective dates against the actual transaction date before coding rules.

### Initial compliance matrix

| Area and authority | Planned control | Release gate |
| --- | --- | --- |
| GLBA; FTC Safeguards Rule, 16 CFR 314 [1] | Role-based access, MFA, encryption and key management, private files, session controls, safe logging, tested restores; incident and service-provider procedures | Security review and dealership written security program before real customer data. Map exceptions individually; do not assume small-dealer exemption from the entire rule |
| FTC Privacy Rule, 16 CFR 313 [2] | Versioned notices, delivery evidence, applicable sharing/opt-out handling, controlled exports | Review actual dealer and vendor data flows |
| Florida security/breach law, §501.171 [3] | Incident timestamps, affected-record investigation, notification workflow, vendor/dealer responsibilities | Counsel-approved response matrix for state and federal deadlines and thresholds |
| TILA / Regulation Z, 12 CFR 1026 [4] | Independently verified APR/finance charge/amount financed/payment disclosures; handle odd periods and deferred downs | Attorney and finance specialist approve calculations and representative contracts before financed signing |
| Florida Chapter 520, especially §§520.03, 520.07–.09 [5] | Verify seller licensing; version contract requirements and applicable charges/limits, refunds and fees | Confirm OFR licensing and effective rules. No single hardcoded universal interest ceiling |
| ECOA / Regulation B, 12 CFR 1002 [6] | Application status and deadlines, decision reasons, applicable notices, retention and fair-lending review | Review dealer/lender notice responsibility before credit decisions |
| FCRA, risk-based pricing, furnishing and identity-theft rules [7] | Permissible-purpose records, applicable notices; identity-theft controls where applicable; furnishing accuracy/dispute workflow if enabled | Credit pulls and bureau furnishing disabled until provider onboarding and legal review |
| FTC Used Car Rule, 16 CFR 455 [8] | Applicable Buyers Guide generation, warranty consistency, language requirements and final copy retention | Confirm display/delivery process; software output alone does not satisfy physical display duties |
| Florida Chapters 319/320, including §319.14 [9] | Structured title brands, required written disclosures and advertising checks; title/tag deadlines and ownership evidence | Review Florida forms and delivery/signature requirements, including rebuilt/flood and other applicable statuses |
| Federal odometer requirements, 49 CFR 580 [10] | Model-year/exemption logic, mileage status, compliant disclosure workflow | Verify current forms and electronic-title/odometer acceptance; do not substitute an ordinary signature pad |
| Florida dealer retention, §320.27 and FLHSMV handbook [11] | Five-year retention for specified dealer records; printable/exportable inspection packet | Retention by record category, longer applicable periods and legal holds override deletion |
| E-SIGN and Florida UETA, §668.50 [12] | Applicable electronic consent, attribution, tamper evidence, accessible copies and delivery | Review document eligibility and DMV acceptance before electronic signing |
| EFTA / Regulation E, §1005.10; provider/Nacha obligations [13] | Separate recurring-debit authorization and copy, cancellation, variable-payment notices, return handling | No compulsory recurring EFT as a general credit condition; approve provider-specific workflow before autopay |
| Collections, repossession and bankruptcy [14] | Contact preferences, consent/stop flags, review queues, dispute/bankruptcy holds and communication history | Florida collection rules may reach original creditors; federal FDCPA applicability differs. Counsel reviews notices and repossession workflows before activation |
| Florida tax, fees, advertising and consumer-protection requirements [15] | Effective-date tax/fee settings, approved price presentation, reconciled sales reporting | Florida tax professional reviews tax examples; legal review of fee/add-on disclosures and advertising |
| Card processing and marketing [16] | Hosted/tokenized payment fields; consent and suppression lists before automated messaging | PCI DSS is an industry/contractual standard, not a blanket DMS law. Verify payment and messaging obligations before enabling integrations |

Additional review before special cases: military borrowers and SCRA, deceased borrowers, out-of-state sales, trade-in negative equity, GAP/service contracts and refunds, GPS/starter-interrupt devices, accessibility, and third-party collection servicing. Do not assume all military lending laws treat purchase-money auto credit alike.

### Financial correctness requirements

- Use decimal/integer money representation with documented rounding; never binary floating point for posted money.
- Record immutable balanced postings; corrections use linked reversals/adjustments, with actor, reason, timestamps and authorization.
- Distinguish contractual finance charge methods, APR disclosure, accrual and payment allocation; configure only reviewed methods.
- Separate promised down payments, received money, unapplied funds, principal, interest and fees.
- Idempotent receipts and provider events; settlement reconciliation; handle concurrent payments and returns without duplicate posting.
- Preserve effective dates versus entry timestamps and complete contract/amendment history.
- Verify against independent examples, not tests that repeat the implementation formula.

## 4. Phased delivery and acceptance gates

No calendar promises until scope, team capacity and outside review availability are known.

### Phase 0 — discovery and project foundation

Deliver workflow maps from the dealership, anonymized form inventory, data dictionary, compliance register, threat model, architecture decisions and open-source contribution/security policies. Inventory the legacy export formats and third-party contract/form rights. Never publish DealerCenter assets, captured account content, customer data, sessions or vendor source as part of Railet; keep the reference capture private and outside the future public repository/history.

Interview staff plus 3–5 other Florida BHPH dealers. Measure baseline time, errors and support pain. Ask what they would actually pay for and who decides to switch. Obtain a scoped quote from Florida dealer-finance counsel for forms/calculations and identify a tax/accounting reviewer.

Exit: approved initial workflow, reviewed scope/assumptions, synthetic data fixtures, agreed community/enterprise boundary. A public release needs a clean repository review, not just ignored files.

### Phase 1 — inventory and customers

Deliver fast search, inventory list/detail, costs/recon, title brands and missing-title tasks, customers/co-buyers, attachments, permissions and audit trail. Use synthetic records first. No lender pulls or money movement.

Exit: staff can find/add a vehicle and customer without duplicate entry; permissions and private downloads verified; restore demonstrated. Validate VIN exceptions rather than assuming every historical vehicle has a modern VIN.

### Phase 2 — deals and reviewed paperwork

Deliver deal states, itemized pricing/trades/down payments, reviewed tax/fee rules, versioned Florida document packs, preview, missing-data checks and finalization. Begin with narrowly supported transactions; financed signing stays gated pending calculation and contract review.

Acceptance example: mark vehicle rebuilt, start deal, see applicable disclosure checks and required packet items, finalize reviewed paperwork, then edit vehicle status; historical packet remains unchanged. Do not assume rebuilt must appear on every form or that an extra disclosure is legally insufficient.

Exit: representative cash/BHPH/trade/rebuilt examples reviewed; no blank essential contract fields; unapproved templates cannot finalize. Start with legally reviewed paper-signing workflow; e-sign can follow.

### Phase 3 — BHPH subledger and manual servicing

Deliver opening balances with provenance, reviewed schedules/accrual/allocations, cash/manual receipts, reversals, payoffs, delinquency, promises to pay, controlled extensions and daily reconciliation. An extension is a reviewed contractual action, not an unrestricted date edit.

Exit: independent reference cases cover partial/early/late payments, weekly/biweekly/monthly schedules where supported, deferred downs, returned payments, reversals, fees, payoff and amendments. Every account ties to the subledger. Operational daily close is usable by staff.

### Phase 4 — controlled dealership pilot and migration

Import a limited verified dataset from authorized exports. Preserve originals securely, document mappings and exceptions, and reconcile balances and documents. Run parallel comparison without initiating duplicate customer charges or treating two systems as simultaneous authorities. Define the authoritative ledger and cutover time explicitly.

Exit: owner approves reconciliations; reviewed workflows have no unresolved critical discrepancies; security review, restore drill, access review and support runbook complete. Rollback plan identifies what happens to transactions after cutover, not merely how to restore yesterday's backup. Retain legacy access/exports as required.

### Phase 5 — community release and paid pilot

Publish clean MPL core, installation/update/backup docs, synthetic demo, contribution guide, private security contact and compatibility policy. Onboard 2–3 design partners with defined support expectations. Public code can precede production readiness but must state its maturity and disabled workflows plainly.

Exit: another IT operator can install and restore using docs; paying dealers complete the core workflow; support demand and costs measured. Add third-party integrations one at a time after their own gates.

### Later

Managed hosting, e-sign, recurring payments, accounting sync, bureau reporting, lender submissions, listing syndication, auctions, marketing and multi-location analytics. Each requires a product case, provider agreement and compliance review where applicable. Do not build a lender marketplace or distributed services platform before the basic workflow works.

## 5. Open-source and monetization plan

### Licensing and ownership

MPL 2.0 is file-level copyleft. Distributed covered files, including modifications, remain subject to MPL source-availability obligations; separate proprietary files can form a larger work. Internal/server-only use generally does not require publication solely because of network access; delivered browser code can be distribution. Users need not contribute changes upstream. Competitors may legally host and sell compliant versions. Build a business around service quality and useful offerings rather than assumed exclusivity. [17]

Before public release add the unmodified MPL license text, file notices/SPDX identifiers, dependency inventory and required third-party notices. Keep commercial code in explicitly separate files/packages with documented license boundaries. Do not copy MPL contributions into closed files to avoid their license. Verify rights to forms, fonts and assets separately.

Use a contribution policy with inbound MPL licensing and a DCO-style sign-off initially. Contributors retain their copyrights; do not promise later proprietary relicensing of community contributions without the necessary permissions. Use trademark policy to protect the Railet name without restricting MPL rights. Check Ephyro's legal ownership/entity details before assigning copyright notices.

### Recommended offering boundary

| Offering | Included | Commercial approach |
| --- | --- | --- |
| Community, MPL 2.0 | Single-dealer inventory, customers, deals, reviewed basic Florida documents, BHPH servicing, subledger, standard reports, baseline roles/MFA/audit, backup/export tools, feedback | Free self-hosting; no seat cap in core |
| Managed Railet | Core plus operated upgrades, monitored backups, support and recovery service | Future recurring per-rooftop subscription; hosting design deferred |
| Services | Migration/reconciliation, training, implementation and custom integrations | Scoped one-time or contracted fees; earn early without building hosting |
| Enterprise extensions | Dealer-group management/consolidation, sophisticated approval policies, SSO/SCIM, cross-location reporting and enterprise support | Separate commercial files/modules, annual or monthly agreement |
| Usage services | Signing, credit/history reports, messaging, payments | Optional provider usage with plainly disclosed cost/margin; customer choice where feasible |

Basic security, access to customer records, essential disclosures and complete data export stay in Community. Enterprise enhancements may be paid, but the free core must be safe and operationally useful. Clearly label which code is MPL and which extensions are proprietary; do not describe the whole enterprise bundle as MPL if it is not.

### Pricing experiments, not market claims

Do not set permanent prices from guesswork. Test willingness to pay around $149–249 per rooftop/month for future managed core, and $349–499 for a genuinely supported enterprise/group offering, subject to cost and buyer research. These are proposed interview anchors, not researched competitor pricing. Start with written paid migration/support pilot quotes; do not sell production capabilities that have not passed release gates. Publish inclusions and usage charges; avoid surprise unlock fees and per-feature charges for essential everyday work.

Illustrative economics: at $199 monthly revenue and an assumed $60 variable monthly cost, contribution is $139/dealer/month before engineering, legal, marketing, taxes and founder compensation. A hypothetical $10,000 monthly fixed cost would require 72 such dealers. Replace assumptions with measured hosting, support time, external service and payment-loss exposure. Model migration labor and high-support customers separately.

Sales sequence: founder dealership proof -> design partners -> documented migrations and references -> public demos -> focused independent-dealer outreach. Sell ease of work, trust and predictable cost. Open source supports ownership and IT adoption; it is not the entire sales pitch.

## 6. Seamless feedback and support

Persistent Help & feedback entry, with contextual Report paperwork issue in document preview. A report records application/version, module, sanitized error identifier, expected/actual behavior and optional redacted attachments. Show exactly what leaves the installation, destination, privacy status and retention before sending. Never automatically attach SSNs, credit reports, contracts, customer records, tokens or financial data.

Default to a private intake queue; only publish a sanitized issue deliberately. Provide report number/status and link fixes to release notes. Allow self-hosters to configure a destination; do not force cloud telemetry. Separate security incidents, account support, bugs and feature requests. Optional diagnostics should not block offline work; failed submission can remain a local draft.

## 7. First implementation backlog

1. Establish clean project structure, MPL policy, contributor/security docs, architecture and compliance decision records.
2. Build synthetic demo data and accessible navigation: Today, Inventory, Customers, Deals, Payments, Reports; administration separate.
3. Implement dealership/user authorization and audited inventory/title/customer records.
4. Implement inventory -> customer -> draft deal -> document preview using clearly marked demonstration forms.
5. Implement contextual private feedback with a local/mock destination first.
6. Obtain reviewed Florida forms and independent calculation cases; implement validation and finalization only after review.
7. Build transactional financial subledger and manually entered receipts before live payment processing.

Validation focuses on authorization, financial correctness, document snapshots, applicability, migration reconciliation and backup restoration. UI prototype checks can be lightweight; money and isolation checks cannot. Use synthetic data in CI and issue trackers, pin dependencies, scan secrets and dependencies, and review changes affecting financial/legal rules.

## 8. Source register

Sources consulted October 22, 2026. Links establish research starting points; each operational rule still needs effective-date and applicability review. Sources using 2025 compilations must be compared with subsequent changes before launch.

[1] FTC auto dealer Safeguards FAQ: https://www.ftc.gov/business-guidance/resources/automobile-dealers-ftcs-safeguards-rule-frequently-asked-questions

[2] FTC auto dealer Privacy FAQ: https://www.ftc.gov/business-guidance/resources/ftcs-privacy-rule-auto-dealers-faqs

[3] Florida Chapter 501 (including §501.171): https://flsenate.gov/Laws/Statutes/2026/Chapter501/All

[4] Regulation Z: https://www.consumerfinance.gov/rules-policy/regulations/1026/

[5] Florida installment contracts: https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0500-0599/0520/Sections/0520.07.html ; Chapter 520: https://www.flsenate.gov/Laws/Statutes/2025?chapter=520 ; OFR: https://www.flofr.gov/divisions-offices/division-of-consumer-finance

[6] Regulation B: https://www.consumerfinance.gov/rules-policy/regulations/1002/

[7] FTC consumer-report notices: https://www.ftc.gov/business-guidance/resources/using-consumer-reports-credit-decisions-what-know-about-adverse-action-risk-based-pricing-notices

[8] FTC Used Car Rule dealer guide: https://www.ftc.gov/business-guidance/resources/dealers-guide-used-car-rule

[9] Florida title-brand disclosures: https://flsenate.gov/Laws/Statutes/2025/319.14

[10] NHTSA odometer disclosure: https://www.nhtsa.gov/press-releases/consumer-alert-changes-odometer-disclosure-requirements

[11] FLHSMV dealer handbook: https://www.flhsmv.gov/pdf/dealerservices/dealerhandbook.pdf ; electronic filing retention: https://www.flhsmv.gov/pdf/proc/efs/efs-02.pdf

[12] Review authorities: E-SIGN, 15 USC 7001 et seq.; Florida §668.50; federal/state electronic odometer and title rules. Detailed applicability research remains pending.

[13] Recurring transfers: https://www.consumerfinance.gov/rules-policy/regulations/1005/10/

[14] Florida collection practices: https://www.flsenate.gov/Laws/Statutes/2025/559.72 ; further repossession, bankruptcy, SCRA and FDCPA applicability research remains pending.

[15] Review authorities: Florida Chapter 212 and DOR guidance; §501.976 and FDUTPA; applicable FTC advertising requirements. Detailed current rules and tax examples remain pending.

[16] Review authorities: PCI SSC/provider contracts; TCPA/FCC rules, Florida telephone solicitation laws and CAN-SPAM. Detailed provider- and workflow-specific review remains pending.

[17] Mozilla MPL FAQ: https://www.mozilla.org/en-US/MPL/2.0/FAQ/ ; license and notices: https://www.mozilla.org/en-US/MPL/2.0/

### Draft financing proposals (development, October 23, 2026)

Cash, outside-financing and BHPH classifications and optional, separately retained
financing proposals are implemented as draft records. Existing drafts migrate to
“Not chosen”. See [DEAL_TYPES_AND_TERMS.md](DEAL_TYPES_AND_TERMS.md) for source
review, controls, verification and unresolved effective-date/applicability gates.
This does not enable origination, APR/payment calculations, contracts or servicing.

### Draft trade-ins and explicit intake (development, October 23, 2026)

One active trade-in vehicle record can be attached to a draft without duplicating
its customer or worksheet amounts. Structured title/mileage and payoff-recipient
details are retained with versioned history. Separate synthetic inventory intake
copies identity through the inventory module's creation interface and is disabled
outside the development gate. Removal preserves the record, previews changed money
and keeps acquired inventory. See [TRADE_INS.md](TRADE_INS.md) for authority,
applicability/effective-date uncertainties and release gates. No tax credit,
odometer/title document, payoff instruction, loan or ledger posting is enabled.

### Saved draft review (development, October 24, 2026)

The deal workspace now links to a read-only review of canonical parties/vehicle,
worksheet, active trade and selected financing proposal. Human completeness
reminders do not determine legal readiness. No forms, signing, loan schedules,
financial postings or finalization are enabled. See [DEAL_REVIEW.md](DEAL_REVIEW.md)
for access controls, consistent reads, independent agent-handoff review and actual
verification evidence. Existing production and compliance gates remain unchanged.

### Independent audit follow-up (October 24, 2026)

Ordinary inventory entry can create duplicate same-dealership VIN records; trade
intake has a narrower duplicate check. Resolve canonical vehicle identity,
reacquisition/sold-stock history and existing duplicate reconciliation before a
live inventory pilot. Do not silently impose a global VIN uniqueness migration or
merge historical records. The overseer's reproduced evidence and disposition of
the independent agent findings are in
[DEVELOPMENT_REVIEW_2026-10-24.md](DEVELOPMENT_REVIEW_2026-10-24.md).

### Duplicate VIN review (development, October 24, 2026)

Ordinary inventory entry now checks new/changed nonblank VINs against same-dealer
active and sold stock, blocks unreviewed duplicates, and requires an acknowledgement
and reason for a separate stock record. Audit evidence and concurrency locks are
shared with the inventory workflow; original history remains intact. This addresses
the ordinary-entry gap recorded above. Existing duplicate reconciliation, canonical
vehicle/reacquisition policy, import controls and production acceptance remain open.
See [DUPLICATE_VIN_REVIEW.md](DUPLICATE_VIN_REVIEW.md) for boundaries and independently
verified results. No global unique migration, automatic merges or production gate
changes were made.

### Supporting PDF files (development, October 24, 2026)

The Documents module now supports private PDFs linked to a saved draft, authorized
attachment downloads and reversible archive/restore with independent audit events.
Upload retries are idempotent; original bytes/hash and archived files are retained.
No signed-document verification, generated form, preview, loan, purge or financial
posting is introduced. All module routes remain gated by DEBUG-derived
DEAL_FILES_DEMO_ENABLED and synthetic-data prerequisites. See
[DEAL_FILES.md](DEAL_FILES.md) for source applicability/effective-date questions,
security/retention/storage gates, implementation and verified results.

### Private local feedback (development)

The Feedback module now provides explicit preview-before-save intake and numbered local reports, scoped to their author and dealership owners. It does not transmit reports, collect diagnostics, attach files, or automatically redact free text. Submissions use signed actor/dealership-bound previews and retry protection. See [FEEDBACK.md](FEEDBACK.md) for permissions, privacy/retention limits, checks, and the outstanding PostgreSQL/VM integration verification. No live integration or production gate is enabled.

### Frozen demonstration summaries (development)

Saved drafts can now produce retained synthetic HTML summaries with frozen parties, vehicle/title/mileage, worksheet estimates, active trade, selected proposal, and human completeness reminders. JSON source snapshots and exact HTML bytes are stored with version/hash/provenance; later source edits do not regenerate them. This is not legal paperwork, a reviewed Florida form pack, or deal finalization. No signing, ledger, loan, payment or production workflow is enabled. See [DEMO_PACKETS.md](DEMO_PACKETS.md) for integrity/access boundaries and remaining PostgreSQL/VM verification.

### Draft archive/restore (development)

Drafts can now be put aside and restored with reasons, revision checks and preserved event history. Archived drafts stay readable; worksheet/party/trade edits require restoration. No inventory status, money, customer profile, supporting-file lifecycle or saved packet is altered. Draft event schema 4 records archive metadata; demo packet template v2 explicitly captures active/archived state while existing artifacts remain unchanged. See [DRAFT_ARCHIVING.md](DRAFT_ARCHIVING.md) for verification and pending VM/PostgreSQL integration.

### Internal deal follow-ups (development)

Saved deals now have assignable internal tasks with optional dates, completion/reopening and retained event history. Home shows the signed-in account’s open reminders; the full list is paginated and scoped by dealership. These are not legal deadlines, automated customer communications or collection actions. See [DEAL_FOLLOWUPS.md](DEAL_FOLLOWUPS.md) for authorization, concurrency boundaries, tests and pending PostgreSQL/VM verification.

### PostgreSQL integration and synthetic ledger foundation

An isolated private-socket PostgreSQL 17.11 developer instance now applies all current migrations and passes the 237-test full suite with no skips, including new workflow and ledger concurrency checks. Browser integration and a separate synthetic database/private-file restore exercise passed. The original offline VM disk was not modified; its existing data upgrade is not represented as verified. See [POSTGRES_INTEGRATION.md](POSTGRES_INTEGRATION.md).

The Community finance module now rehearses provenance-backed synthetic opening balances, structurally balanced append-only integer-cent postings, fully unapplied manual receipts, exact linked full receipt reversals and aggregate reconciliation. Signed posting previews, scoped permissions, retry protection and database guards are implemented. No contractual allocations, interest/APR, fees, loan creation, settlement, real money or collections are enabled. Current primary-source review and unresolved effective-date/applicability/professional-review gates are recorded in [LEDGER_FOUNDATION.md](LEDGER_FOUNDATION.md).


Development now supports explicit proposed Precomputed/Simple method metadata and separate immutable synthetic schedule illustrations. See SCHEDULE_METHODS.md for primary sources, unresolved applicability/effective-date review, arithmetic assumptions and production gates. APR, payoff/refunds and live servicing remain disabled.


Synthetic BHPH account workspace: see [record boundaries and workflow](BHPH_ACCOUNT_WORKSPACE.md). Shared customers, immutable draft context, saved illustrations and unapplied receipt history are integrated. Linking a draft does not originate a loan; live allocation and servicing gates remain unchanged.

Synthetic BHPH workflow follow-up: account setup can begin directly from a saved BHPH draft, reuse its canonical customer/vehicle and capture proposed terms in the same transaction as an explicitly sourced invented opening. One account per draft prevents duplicate openings; no worksheet-to-debt conversion or contract finalization is enabled. See BHPH_ACCOUNT_WORKSPACE.md for workflow and migration controls.

Synthetic account portability follow-up: authorized account exports include the full bounded journal, frozen draft context, saved illustration inputs/results and a file-hash manifest. Export preparation is audited and shares the financial book lock for a coherent capture. This narrowly scoped account download does not fulfill complete dealership export/restore or activate live servicing; see ACCOUNT_EXPORT.md.

Customer-data follow-up: optional contact addresses are stored once and reused in deal/account views; new versioned demo packets freeze buyer/co-buyer addresses. Address entry is not verification, residency or tax-jurisdiction determination, contact consent or legal completeness. No external validation service or live document behavior is enabled. See CUSTOMER_ADDRESSES.md.

Monthly precomputed synthetic servicing follow-up: accounts may explicitly select one immutable monthly precomputed illustration as a versioned installment-coverage baseline. Partial/early/extra receipts and full corrections are projected against oldest installments, with an as-of date and record capture timestamp. Due/past-due/due-today statuses are labeled Demo; missing or invalid baselines remain neutral. Authoritative ledger receipts remain unapplied and principal is unchanged. No actual loan, earned-interest allocation, statutory delinquency, fee, payoff or collection instruction is enabled. See [DEMO_SERVICING.md](DEMO_SERVICING.md) for assumptions, source review and remaining production gates.

Daily payments follow-up: the existing synthetic payment register now exposes
receipts, linked reversals, net activity and manually recorded payment methods
under BHPH. Unknown historical methods remain Not recorded; new reversals retain
the original method. Account export v4 includes the method. This is not cash-drawer
or bank reconciliation and enables no real payment activity. See PAYMENT_REGISTER.md.

BHPH worklist follow-up: status shortcuts and oldest-overdue ordering apply the
existing synthetic installment simulation across matching accounts before
pagination, with bounded scans and explicit unknown status. Next unpaid dates and
a direct Record payment action keep common work near the account row. No live
collections, contractual delinquency or allocation rule is introduced. See
DEMO_SERVICING.md for capture/locking limits and verification.

Printable synthetic receipt follow-up: the existing private receipt view supports
browser print/save-PDF with exact journal facts, verified frozen vehicle context
and linked reversal evidence. The sheet preserves explicit demo labels and
identifies current customer/workspace display names; it is not a stored or legally
reviewed receipt artifact. See PRINTABLE_RECEIPTS.md for scope and verification.

### Draft desking, Florida tax and inline vehicle entry (October 29, 2026)

Deal type is prominent during creation and on the saved desk. Creation includes
visible pricing, selected financing terms, a server-backed estimate and an
inventory-owned inline vehicle path alongside inline customer entry. Creation
serializes dealer scope and rolls vehicle/customer/deal/audits back together;
retries return one saved draft. Unknown title/mileage facts remain unknown.
Automatic draft tax is limited to a dated 2026 Florida-resident single-vehicle
retail profile, with explicit registration county and qualification assertions.
Existing manual tax/history/artifacts remain preserved. Precomputed charges and
equal-monthly simple-interest illustrations are explicitly distinct; neither is
APR, actual daily accrual, a live loan or tax filing. See FLORIDA_DRAFT_TAX.md for
primary authorities, effective-date scope, unresolved rule/professional review,
provenance and verification. Community/enterprise and production gates are unchanged.
