# Working on Railet

## Product and plan

Railet (railet.com) is Ephyro's modular dealership management system, initially for Florida independent dealers with buy-here-pay-here operations. Read `docs/RAILET_PLAN.md` before architecture, financial, document, security, licensing, or scope decisions. It records the phased roadmap, compliance research, open questions, and monetization proposal. Pricing and implementation choices in that plan are proposals, not promises.

Build one coherent product as a modular monolith. Keep inventory, customers, deals, documents, servicing, finance, administration, and feedback responsibilities explicit. Favor simple, maintainable solutions and clear navigation. Do not introduce microservices or choose production hosting prematurely.

## Licensing and public releases

The planned community license is MPL 2.0. Preserve covered-file notices and third-party attribution. Separate commercial extensions into explicitly licensed files/packages; never move community contributions into closed files to evade MPL obligations. Do not assume contributors assign copyright or permit proprietary relicensing.

Keep essential security, reviewed basic documents, core BHPH functions, and complete data export in the community offering. Monetization focuses on services, future managed hosting, and enterprise extensions. Obtain explicit direction before changing these boundaries.

DealerCenter HTML and its asset directory are private reference material. Never include them, their copied code/assets, customer data, credentials, or session information in a public release. Use independently written implementations and synthetic fixtures. Review repository history as well as current files before publication. Do not publish or push without authorization.

## Compliance and production gates

Regulatory compliance is a required engineering constraint. Follow applicable federal and Florida requirements for each implemented workflow; use the compliance matrix in `docs/RAILET_PLAN.md` as a starting point, not an exhaustive legal checklist. Do not treat the owner's LLC, open-source licensing, disclaimers, or self-hosting as substitutes for compliance or reasonable precautions.

Before implementing a regulated behavior, identify the applicable requirements and effective dates, translate them into explicit validation and workflow controls, and record the source and verification evidence. If applicability or interpretation is unresolved, document the uncertainty and keep the affected live behavior disabled while continuing safe development with synthetic data. Do not silently substitute a guess for a legal requirement.

Do not weaken security, financial integrity, required disclosures, or retention controls to meet a deadline or create a paid upgrade. Obtain explicit user authorization before production deployment, importing real customer data, or initiating live payments; development work and mock integrations may continue within the authorized scope.

Do not claim Railet is certified or legally compliant merely because a feature exists. Distinguish researched requirements, implemented controls, legal review, and verified operation.

For regulatory changes, consult current primary sources, verify effective dates and jurisdiction, and update the compliance register/plan with the authority, applicability, implementation, evidence, and unresolved questions. Compilations may include provisions not yet effective. Never invent statutory limits, deadlines, tax rates, or required language.

Use synthetic data and clearly marked demonstration documents until the relevant production gates are satisfied. Florida contracts, disclosures, lending calculations, and transaction workflows require appropriate legal/financial review before live use. Do not enable live credit pulls, bureau reporting, payment processing, electronic signing, or automated collections without the associated review and integration prerequisites. These are production gates, not reasons to stop reversible development or mock integrations.

Treat title brands as structured data driving applicable disclosure and advertising checks. Do not assume a rebuilt brand must appear on every form or that a separate disclosure is automatically insufficient. Preserve generated/finalized deal snapshots, template versions, and signed artifacts; subsequent edits must not silently alter history.

## Financial integrity

- Use decimal or integer monetary values with explicit rounding, never binary floating point for posted money.
- Use transactional, balanced, append-only financial postings. Corrections require linked reversals/adjustments with actor, reason, and timestamps.
- Distinguish contractual interest/accrual, APR disclosures, payment allocation, fees, deferred downs, unapplied funds, and settlement.
- Make payment/provider event processing idempotent and safe under concurrency.
- Preserve calculation versions, effective dates, entry timestamps, and contract amendment history.
- Reconcile migrated balances against authorized source exports; document exceptions. Define one authoritative ledger during cutover.
- Verify money calculations against independent reference cases, not tests that merely repeat the implementation formula.

## Security and customer information

Enforce permissions and dealership isolation on the server. Keep documents private and authorize every download. Design for MFA, encryption, safe secrets handling, audited changes, and tested backup restoration. Never print secrets or place actual customer records in tests, logs, issue trackers, or public artifacts.

Feedback must preview what is sent, use private intake by default, and sanitize diagnostics. Do not automatically attach contracts, credit reports, SSNs, tokens, or customer financial data. Self-hosters control reporting destinations and optional telemetry.

Retention is record-specific. Respect applicable retention periods and legal holds; do not implement a universal five-year deletion policy. Baseline security and export cannot depend on a paid license.

## User experience

Prioritize UX as a core product requirement alongside correctness, security, and compliance. Railet exists to make dealership work clear and efficient. Make the correct action easy and consequential mistakes difficult.

- Organize screens around dealership tasks, with consistent navigation and a clear next action. Keep common actions easy to find and minimize unnecessary steps.
- Enter information once and reuse authoritative records across modules. Preserve finalized transaction snapshots rather than silently updating historical documents.
- Use plain dealership language, sensible defaults, and actionable errors. Do not default unknown legal or vehicle facts to reassuring values such as an unbranded title.
- Preserve entered work after validation errors and warn before losing unsaved changes. Avoid confirmations for routine reversible actions.
- Use behavioral design to reduce uncertainty and support real progress: confirm when work is saved, show meaningful completion states, and make the next useful step clear. Never fake progress or activity, manufacture urgency, or use streaks and rewards to pressure staff.
- Before consequential actions, show the affected records, financial consequences where relevant, and what confirmation will do. Never make a posted financial correction look like an ordinary editable field.
- Include keyboard navigation, visible focus, labeled inputs, accessible error feedback, readable contrast, and responsive layouts in acceptance criteria. Do not rely on color alone to communicate status.
- Test important workflows with dealership staff before calling them validated. Distinguish developer checks from actual staff feedback; do not claim user testing that has not occurred.
- Show only implemented, usable tasks. Do not add fake actions, placeholder modules, or “Coming soon” controls to everyday screens.
- Keep promotions and upgrade prompts out of everyday workflows. Clearly explain paid service costs when a user deliberately chooses a paid service.
- Resolve usability and compliance requirements together; do not remove required disclosures or controls merely to reduce clicks.

## Implementation and verification

Before editing, inspect existing code and applicable instructions. Respect unrelated user changes. Keep modules responsible for their own records and expose explicit interfaces for cross-module behavior.

Test according to risk: financial correctness, authorization, isolation, document applicability/snapshots, payment idempotency, migration reconciliation, and restores need meaningful verification. Lightweight reversible UI changes do not require redundant tests. Run relevant checks and report actual results and limitations; never claim checks passed if they were not run.

Use accessible forms, clear labels, readable errors, and direct links from daily tasks to the relevant records. Keep implementation details out of ordinary dealer workflows. Add dependencies only with a clear need and compatible licensing.

Document material architecture decisions and changes to release gates. Continue independently on authorized, reversible work; ask for missing business decisions only when they materially block progress. Do not spawn subagents unless the user explicitly requests delegation or parallel agent work.
