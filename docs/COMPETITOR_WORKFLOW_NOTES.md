# Private-reference workflow findings

Review date: October 27, 2026. Sources: owner-supplied saved DealerCenter Deal and BHPH Reports webpages, reviewed locally, and owner-pasted product catalog. These notes record independently described workflow observations only. No vendor source, assets, customer data, report rows, credentials or session material are included. Original captures remain private and must not enter source publication or repository history.

## What the captures show

The deal page groups vehicle sale structure, parties/lienholder, financing terms and a summary, with separate notes, files, events, worksheet and post-sale areas. Visible amounts include price, cash received, trade-in, amount financed, monthly payment, finance charge and net profit. Its record status can identify a funding step. This is evidence of displayed UI concepts, not verification of their calculations or legal applicability.

The BHPH report builder exposes account status and owner filters, account information, insurance and auto-pay status, days past due and repossession status. Visible financial columns distinguish down-payment balance, principal, interest, fees, side-note balance, available credits, total balance, contracted payment and total due. Save, print/export, add-report and scheduled email controls are visible. The capture does not establish the semantics of side notes, the formulas, actual email delivery, account lifecycle transitions or reporting correctness.

## Implications for Railet

1. Keep Deals focused on preparing a vehicle sale. Keep BHPH focused on an established customer's account and recorded payment history. Use clear section labels and direct links between related records.
2. Account reporting is a significant BHPH workflow, not a decorative dashboard. Eventually let staff answer which account needs attention, why, the applicable date and which source transactions explain the amount.
3. Reuse filtering and personal saved views for report definitions. Preserve understandable defaults and a compact records-first table. Report/export permissions and dealership isolation remain server enforced.
4. Never collapse principal, accrued interest, fees, deferred down payments, credits and amount due into one ambiguous balance. A report must identify the date basis and calculation version where relevant.
5. Preserve the distinction between planned down payment, actual receipts, unapplied funds and settlement. Railet's current synthetic receipts remain wholly unapplied; they do not reduce principal.
6. Avoid automatic emailed financial reports as a first step. Any future delivery needs explicit recipients, authorization, private delivery, redaction/retention decisions and audited configuration. None is enabled by this review.

## Candidate sequence

- Continue testing the navigation and account workflow with dealership staff using synthetic records.
- Improve the existing account/payment history and read-only payment register using information already authoritative in Railet. Keep synthetic account limitations visible.
- Define account lifecycle, contractual schedules and allocation semantics before adding active/closed status, delinquency, total due or payoff reporting. Those are financial behaviors requiring current primary-source research, explicit controls, independent reference cases and the existing production reviews.
- Then build saved account report views and authorized exports around verified account facts. A prototype must not guess missing financial amounts or infer delinquency from an illustrative schedule.

This review introduces no regulated behavior and does not establish production readiness or add a new financial calculation.

## Owner-supplied catalog and business implications

The supplied catalog lists Dealer Desktop at $99/month and BHPH at $50/month. Other examples include CRM Plus at $99, Advanced CRM at $199, reconditioning at $99, integrated accounting at $99 and QuickBooks integration at $40. These are observations from the supplied catalog, not independently verified current public prices, a quotation or the owner's invoice. CRM tiers may be alternatives; do not sum every catalog entry or infer the eight subscribed services.

Illustrative optional bundle: DMS $99 + BHPH $50 + CRM Plus $99 + reconditioning $99 + integrated accounting $99 = $446/month, before usage, taxes, minimums and other terms. This is an arithmetic example, not the owner's bill. The supplied printing price is $5/use and eContracting is $3/use; their scope, licensing and underlying costs are not established by the catalog.

Separate three types of cost:

- Core application capabilities: inventory, shared customers, deal preparation, core BHPH, essential security and complete export remain within the planned community boundary. Ordinary record management is not evidence of a third-party per-use cost.
- Provider-backed services: bureau access/scores, licensed valuation data, SMS, shipping and payment processing can involve third-party contracts, qualifications, minimums and usage charges. Open-source application code does not provide those services for free. Electronic signing's deployment, licensing and operating costs require separate review.
- Railet services and enterprise work: charge transparently for setup, migration, training, support, future managed hosting and explicitly licensed enterprise extensions. No pricing or support commitments are created here.

Modularity should organize the product, not force staff to assemble everyday dealership work from repeated paid unlocks. No change to the existing community/commercial boundaries is proposed by this review.
