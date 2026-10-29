# Task-first interface redesign

Owner feedback: the marketing workflow sample is the desired visual direction. The previous interface confused a family member who tried it; that is useful usability feedback, not a formal staff validation. Prioritize recognizable tasks and reduce visible choices before adding more features.

## Design plan

Palette: green #204c41, ink #20352d, white #ffffff, paper #f5f7f5, divider #dee6e1, yellow #f2d56a used sparingly in the independently written letter mark. Typography: self-hosted Manrope (SIL OFL 1.1), 16 px body, 14–15 px secondary text, clear 32 px page titles. Keep information left aligned and controls comfortably sized.

Layout:

    Railet                                  Dealership / account menu
    Home     Vehicles     Customers     Deals     Payments
    Test workspace — made-up data only

    Page title                                  Main action
    Search / working content
    Optional advanced details

Home centers four usable tasks: start a deal, add a vehicle, add a customer, record a payment. Read-only users receive browse actions instead. Existing follow-ups remain secondary. Lists begin with search; advanced filter editing and saved searches are disclosed only when requested. Deals keep an explicit Draft status on the record while the module is called Deals. Secondary deal tools move behind More; Save and Review remain visible.

## Review against the request

Do not turn the sample into a decorative dashboard or copy the proprietary website's mockup markup/assets. Preserve actual records and working actions, with independently written templates/CSS. The sample's useful qualities are the quiet top navigation, readable hierarchy and task focus. Avoid another left sidebar plus many toolbars. Do not add statistics, unavailable modules, promotional prompts or artificial progress.

Financial posting previews, correction consequences, legal/production gates, unknown title facts, actor permissions and historical snapshots remain intact. Reducing visual density is not permission to hide errors or claim a draft is final. The development-mode notice remains visible once in the shared shell; action-specific financial disclosures remain at their relevant action.

Verification must include owner/staff/viewer navigation, keyboard/disclosure behavior, existing form submissions and error preservation, desktop/mobile layouts, and actual synthetic task flows. Browser checks are developer evidence; the owner's subsequent feedback determines whether the new layout is easier to use.

## Implemented behavior and verification

The shared shell now uses top tabs, the new font and a single visible test-workspace indicator. Home has four real task links. The Deals list has in-progress/archived/all tabs that retain search rules. Optional creation details, fee breakdowns, financing terms, secondary deal tools, follow-ups and saved searches use progressive disclosure. Applied filters and validation errors remain visible; field errors automatically reveal their affected details. Choosing a financing type explicitly opens its terms for entry. Payments now begins with customer accounts and direct Record payment links; standalone account setup and the register remain under More account tools. Consequential posting previews and server authorization remain in place.

The full PostgreSQL suite passed 330 tests in 112.054 seconds. Browser checks cover seven screens at 1440/390/320 pixels, keyboard operation of More, creating and saving a synthetic draft, exact saved amounts, financing fields, a saved-search round trip and a synthetic payment followed by its full linked correction. The draft balance reference was $2,100.50; the payment test was $12.34 and was reversed. No real funds, customer records or live DMS transaction were used. Local browser evidence is private under `.local/ui-redesign-review/`. This is developer verification, not a claim that the owner's family or dealership staff has validated the redesign.

Font attribution is retained in THIRD_PARTY_NOTICES.md and static/fonts/Manrope-OFL.txt. No proprietary marketing mockup code or images were copied into community source. No public push or production deployment was performed for this DMS redesign.

## Customer-first lists (owner feedback, October 26)

The owner reports that a family reviewer liked the top tabs but could not immediately find customers beneath the large search panel. Use a spreadsheet-style customer list: compact title/actions, one-line search, optional tools and dense readable rows. BHPH replaces the Payments navigation label and opens the existing account list; payments are actions inside each account. No invented active/closed status, due amount or live lending behavior is introduced.

Tokens: website green #204c41, yellow #f2d56a, porcelain #f7f9f7, ink #1c2c27, slate #5e6b64, border #dbe3dc. Manrope remains the UI font. The website mark is intentionally shared at the owner's request, with trademark rights reserved; proprietary website source remains private.

Plan: left-aligned heading and add action, compact search above column headings, customer names immediately visible.
```
Customers                               + Add customer
[ Search name, phone or email ] [Search]   Filters / Saved searches
Name                   Phone                 Email
Riley Demo             ...                   ...
```
Critique: the previous panel prioritized configuration and explanatory text ahead of records. Remove that hierarchy and oversized spacing; retain real table semantics and explicit links rather than pretend spreadsheet editing. BHPH uses customer/vehicle/account columns and an Open account action; no default Record payment shortcut on Home or the list.

Implemented and checked: Customers and BHPH now use compact toolbars and semantic column tables. The website brand mark and exact palette are shared; Home uses BHPH accounts, and recording payments stays inside the account workspace. The test-data notice remains visible. Existing account scopes and saved searches remain available; no account lifecycle state is invented.

Verification: 38 focused PostgreSQL customer/navigation/account/search tests passed (3.875s). Firefox checked seven screens at widths 1440, 390 and 320 without outer-page overflow. On desktop the first customer/account row finishes above 650px. The initial mobile check found off-screen accessible table labels extending the page; containing those labels fixed the overflow. Screenshots and the browser check are in ignored `.local/records-ui-review/`. These are developer checks, not a new staff usability study. Local preview only; no public push or production deployment.

## Apply records-first consistently across all lists

Owner screenshot shows Vehicles still burying rows under the original heading, presets and search panel. Correct all four list screens together. Retain website tokens (green #204c41, yellow #f2d56a, porcelain #f7f9f7, ink #1c2c27, slate #5e6b64, border #dbe3dc) and Manrope. Left-aligned title/add action followed by one compact toolbar then actual rows. Vehicle presets become an optional Views disclosure; deal scopes remain visible for archive access.
```
Vehicles                    [Views] [+ Add vehicle]
[Stock, VIN, make or model] [Search] [Filters] [Saved searches]
Photo / Vehicle          Status          Title         Cost
[actual vehicle rows immediately here]
```
Review: merely shrinking a standalone search card still gives tools more prominence than records. Use one shared inline toolbar in each table panel, no explanatory header paragraph, no absolute-positioned filters; opening advanced tools expands in normal flow and errors remain visible. Keep table semantics, thumbnails, keyboard links, and safe financial wording.

Completed across Vehicles, Customers, Deals and BHPH. Search, filters and saved searches share a single desktop toolbar; advanced sections expand in normal flow. Vehicle presets are under Views and photos/stock identifiers remain directly in the records. Shorter shared header preserves the top tabs, brand and test-data notice.

Verification: 79 focused PostgreSQL tests passed in 29.664s, including shared filters, dealership isolation, customer/inventory permissions, deal workflow and account search. An initial command referenced a nonexistent test module; the corrected run includes `deals.tests`. Browser checks cover seven screens at 1440/390/320px, no outer overflow, and first rows on all four list pages visible within 460px desktop / 650px narrow. Expanded filter and saved-search regions do not overlap each other or the records. Invalid filters show errors, and a stock search returns the expected synthetic vehicle. Screenshots inspected for desktop and phone; replaced one unsupported dropdown glyph with SVG. Evidence in ignored `.local/all-lists-ui-review/`. Local synthetic preview only.

## Section destinations and Deals/BHPH orientation (October 27)

Owner wants Home cards to open their respective lists, matching the top tabs, rather than immediately creating records. Home will show Vehicles, Customers, Deals, BHPH in navigation order for all roles; creation stays within the relevant section. Keep the current Manrope and website palette: green #204c41, yellow #f2d56a, white #ffffff, porcelain #f7f9f7, ink #1c2c27, border #dbe3dc.

Layout: left-aligned Home heading and four navigation cards. Deals uses a document symbol and the explicit purpose 'Vehicle sales and deal preparation.' BHPH uses a wallet symbol and 'Customer accounts and payment history.' Account numbers and Open account actions identify BHPH rows; technical draft-derived labels remain in account detail rather than competing with account identification in the list. Account detail explicitly says BHPH account before its number.
```
Home: Vehicles | Customers | Deals | BHPH
Deals: document / Deals / Vehicle sales and deal preparation
BHPH: wallet / BHPH accounts / Customer accounts and payment history
```
Critique: identical tables are useful for learning the product, but the user's purpose must be explicit. Keep shared list mechanics; distinguish headings and vocabulary using text plus icons, not color alone or decorative new dashboards. No financial behavior or real servicing status is added.

Verification: 26 focused PostgreSQL navigation/account/search tests passed in 2.014s. Browser clicks verified each Home card opens exactly its corresponding list and updates the active top tab; opening an account retains BHPH and explicitly identifies the BHPH account. Seven screens checked at 1440/390/320px without outer overflow; existing row-visibility, expanded filters/saved searches, invalid-filter and vehicle-search checks passed. Reviewed final desktop Home and BHPH screenshots. Evidence in ignored `.local/section-navigation-review/`. Preview only; no public push or deployment.

## Complete synthetic BHPH workflow (October 27)

Use the established website palette and Manrope. Compact next-action rows connect saved BHPH deal -> account setup -> account -> named customer payment form -> review -> saved receipt -> payment history. Keep clear cancel/back links and actual saved states. Critique: the links technically exist, but setup is easy to miss and technical account labels obscure the customer. Retain previews, edit/retry paths and financial consequences. No fake progress or new lending/servicing behavior.

Completed and verified: visible next-step account setup/open action on BHPH deals; named customer/account/vehicle context on payment entry, preview and receipt; direct receipt-to-history and another-payment links; clearer customer account links and form cancellation. Full UI browser walkthrough passed, with all four changed screens at 1440/390/320 without outer overflow. A real edit-preview bug was found and fixed: form actions now point back to their preparation endpoints after an edit response. New regression coverage checks opening, receipt and correction edit/review/save. 36 focused PostgreSQL tests passed in 2.195s. Receipt and payment screenshots reviewed. See BHPH_DEMO_WALKTHROUGH.md for a synthetic owner walkthrough and uncoached staff-review prompt. No staff usability validation or live financial readiness is claimed. No publication or production deployment.

## Restrained interaction feedback

Keep website tokens and Manrope. Add short 120–160ms hover/focus color transitions, user-triggered disclosure reveal, real submit loading state, and a brief highlight on server-confirmed success messages. No page entrance effects, counters, delay or fake progress. Layout remains records-first; status always has text. Reduced-motion preference removes animation, including an in-progress disclosure effect.

Review: native details must remain usable without JavaScript, errors must reveal immediately, and financial confirmation buttons must retain their name/value while loading. Do not disable those submitters before the browser serializes their action. Never infer successful save from a click; animate only the existing server success message.

Implemented: shared interaction-feedback.js adds user-triggered disclosure reveal, pending button/form accessibility state and browser-back reset. CSS adds short hover/focus color feedback, loading spinner and a server-success highlight that retains its text. Native disclosure size interpolation is progressive enhancement; menus and error-triggered reveals stay immediate. Financial confirmation forms supply action-specific pending labels, with separate wording for returning to edit. Enabled submitter names/values are preserved. Reduced motion removes CSS effects and cancels active disclosure effects.

Verification: 14 focused PostgreSQL preview/navigation tests passed in 1.032s. Firefox checks passed with reduced motion both off and on: normal disclosure effects versus zero reduced-mode effects, actual server-confirmed Customer saved notice, no loading on an invalid form, pending payment text and preserved action=post, and restored labels/busy state on pageshow. Posting was explicitly prevented in the browser feedback test; only invented customer records were added. Evidence in ignored `.local/motion-review/`. Local preview only.

## Payment-first BHPH account workspace

Owner feedback: opening the account should show amount due, lateness and payment action before background customer/vehicle details. Use brand green #204c41 for action, amber #79510d on #fff4d8 for unassessed status, blue #284d6a on #edf4fa for amount-due context, ink #1c2c27 and white #ffffff. Manrope with 28px identity, 22px primary values, 14px supporting text. Left-aligned compact identity, payment overview, history, then optional details.
```
BHPH accounts / Customer                        Account #
Vehicle / Stock
Amount due       Late status           [Record payment]
Not calculated   Not assessed          Demo only
Payment history                     Unapplied total $...
[receipts]
> Customer and vehicle details
> Account figures and export
> Proposed terms / Schedule illustrations
```
Critique: do not replace an information dump with more decorative metric cards. Use a single payment strip with explicit unknown states. No fabricated zero balance, due date, current status, delinquency or implied collection authority. The unknown states are genuine limits of the existing synthetic account, not fake controls. Payments remain unapplied. Preserve access to all previous records and controls.

Research checked October 27: NN/g visual hierarchy https://www.nngroup.com/articles/visual-hierarchy-ux-definition/ recommends ordering attention by importance; progressive disclosure https://www.nngroup.com/articles/progressive-disclosure/ separates common tasks from secondary detail with clear labels. W3C Use of Color https://www.w3.org/WAI/WCAG21/Understanding/use-of-color.html requires information beyond color. Applied as explicit labeled states plus color; no invented claims about universal color psychology, reduced task time or validated staff usability.

Implemented payment-first account header/overview and visible payment history, with background customer/vehicle, source figures/export, proposed terms and schedule illustrations under four native disclosures. Color is reinforced by labels and a question symbol for unassessed status. Actual unapplied total remains explicit and distinct from an unknown amount due. On phones the Record payment action comes before status tiles. No derived financial behavior or permissions changed.

Verification: 21 focused PostgreSQL account/payment-view tests passed in 1.328s, including a new check that neither opening principal nor unapplied funds are presented as due or a lateness determination. Linked and unlinked accounts checked at 1440/390/320px with no outer overflow. Record payment button bottoms at 357/357/441px for the long-name linked account; history headings at 470/534/646px. All secondary disclosures open by keyboard, original principal remains accessible, and payment action reaches the correct account form. Contrast calculations for blue, amber and primary green combinations are 8.02:1, 6.40:1 and 9.67:1. Developer screenshots/evidence in ignored `.local/payment-first-review/`; no claim of a full accessibility audit or staff usability validation. Local preview only.

## Task-first detail pages across modules

Apply the payment-first hierarchy to Vehicle, Customer and Deal records. Keep Manrope and six existing tokens: brand green #204c41, ink #1c2c27, white #ffffff, blue context #edf4fa, amber attention #fff4d8, border #dbe3dc. Left alignment; compact identity -> frequent action/key facts -> working records -> optional details.
```
Vehicle: photo/name + Start deal | Status / Title / Mileage
         > Photos > Costs > Notes > Activity
Customer: name + Start deal | phone / email
          Accounts / Deals | > Address > Change history
Deal: name + Save | draft balance / planned down / Review deal
      vehicle/buyer + numbers | optional fees, terms, history
```
Critique: do not spread the same metric-card template into every module. Vehicle needs recognition and evidence, Customer needs contact/linked records, Deal needs financial preparation. Keep title brand/ownership warnings visible, preserve photo-error and anchor access, and distinguish planned figures from receipts. No guessed readiness, live amount due or financial behavior is introduced. Source principles remain the visual hierarchy/progressive disclosure/color guidance cited above.

Implemented across Vehicle, Customer and Deal details. Vehicle status/title/odometer and start action lead; title warnings remain visible. Costs, photos/upload, notes and activity are disclosed on demand. Photo errors open their parent and #photos anchors reveal the gallery. Customer contact and linked BHPH/deal records lead, with address and full change records preserved under disclosures. Deal draft balance/planned down/review lead, with an unsigned planned amount in the overview and signed worksheet deductions preserved. Live preview still uses the same integer-cent calculation; financial posting behavior is unchanged.

Verification: 161 scoped PostgreSQL inventory/customer/deal/navigation tests passed in 78.797s. The interrupted session had stopped the local database and left a disposable test database; the developer database was restarted and the test runner recreated its own test database. Browser checks at 1440/390/320px found no outer overflow. Primary action bottoms: Vehicle/Customer 251/288/349px, Deal 359/382/468px. Verified photo anchor/upload access, saved customer-to-account link, and changing draft price updates the new overview exactly before reverting without saving. Reviewed desktop Vehicle and phone Customer screenshots. Evidence in ignored `.local/record-details-review/`. Local synthetic preview only; no public push or production deployment.

## Proportion and grouping pass

Owner requests fixing oversized small-item blocks and crowded rows consistently. Use frontend-design with the existing six tokens: green #204c41, ink #1c2c27, paper #f7f9f7, line #dbe3dc, blue #edf4fa, amber #fff4d8; Manrope. Shared rhythm: 4/8/12/16/24px, 26–28px page headings, 16–18px section headings, 14px record text; preserve 44px interactive controls and 16px mobile inputs.

Plan: Home is a compact directory rather than four large tiles; customer phone/email are inline facts; linked records are rows, not separate decorative cards; vehicle status/title/mileage use one compact strip. BHPH reserves green action and amber status accents without giving every short fact a large tinted panel. Deal top figures stay prominent but supporting identity and repeated balance areas are compacted. Forms keep readable input sizing and working space; trim section padding rather than controls.
```
Home: [Vehicles / explanation / View] [Customers / explanation / View]
Customer: Phone ... | Email ... | Edit
Vehicle: Status ... | Title ... | Odometer ...
Records: section heading -> rows -> next section (quiet divider)
```
Critique: a global font-size reduction would worsen usability. Group related small facts and reduce duplicated boxes, leaving real work areas (forms, payment history, deal numbers) dominant. No data, calculations, unknown status, required disclosure or permissions changes. A final dedicated layout stylesheet consolidates this pass rather than interleaving more module overrides.

Completed: final layout.css groups small facts into compact rows, replaces large Home tiles with a two-column directory, quiets Customer linked-record panels, reduces Vehicle fact-block padding, and concentrates BHPH attention on status/action/history. Deal supporting identities and summary spacing are tighter; one duplicated worksheet balance display was removed while top and summary outputs remain. Form/control sizing, labels, validation, title warnings and financial consequences remain intact.

Verification: 42 scoped PostgreSQL navigation/deal tests passed in 23.000s. Repeat scan of 25 screens at 1440/390/320 found no page-wide overflow, visibly unlabeled controls or missing contextual navigation. Browser interaction checks passed for checkbox labels, native and server validation within disclosures, error focus clear of sticky actions, photo anchor/upload access, linked customer-account navigation, and live deal estimates. Primary record actions remain above 465px at the narrowest tested width. Reviewed Home desktop, Customer phone and BHPH desktop screenshots. Evidence in ignored `.local/proportion-review/` and existing interaction evidence directories. No additional full-suite run was required for the layout-only changes; the prior shared-form full run remains 332 tests. Local preview only.

## Useful BHPH account-list facts

Owner wants useful list-level information without more clutter. Keep customer/account identity and frozen vehicle, add latest recorded receipt and actual net unapplied funds. Fold account number under customer and omit repeated missing-phone text. Latest means entry order (entered_at, pk), while its displayed date is explicitly effective date; retain a visible Corrected label if reversed. Net unapplied funds derives only from retained debit/credit journal buckets, never from draft estimates, principal or a schedule. Unknown due/late status stays explained once, not falsely repeated as zero/current. Use integer-cent aggregates in one scoped SQL read so displayed figures share a statement snapshot. No payments or legal calculations added.

Reuse green #204c41 actions, ink #1c2c27, white #ffffff, line #dbe3dc, blue #edf4fa for recorded funds, amber #fff4d8 for corrected history. Manrope 14px table, 12px supporting text, restrained row spacing. Desktop columns: Customer/account | Vehicle | Latest receipt | Unapplied funds | Open. Narrow screens keep customer/vehicle together and the two money facts side by side with explicit text labels; retain table roles.

Verification: 31 focused PostgreSQL account/search/payment-view tests passed in 2.272s. New independent arithmetic case records $19.99 plus $5.01 = $25.00, then reverses $5.01 and verifies net $19.99 while the latest receipt remains $5.01 and marked corrected. Entry order is tested separately from effective date; opening-only accounts show zero unapplied and no receipt, foreign accounts are excluded, and projected account facts load in one query without per-row related-record queries. Browser checks at 1440/390/320 have no outer overflow, show money facts without horizontal scrolling on phones, follow the correct receipt link and preserve an actionable empty search state. First row bottom is 416/579/651px. Desktop and phone screenshots reviewed; evidence in ignored `.local/bhph-list-review/`. No new money, live servicing, status inference or production deployment.

## Demo servicing states

Explicit monthly precomputed baseline selection now enables demo due amounts and labeled red/amber/green coverage states in the account and list. The amount itself follows the state color; unknown/unselected accounts remain neutral. Next/oldest unpaid date is visible in the account overview; calculation evidence lives on the read-only installment coverage page. Preview explains the immutable selection and oldest-first assumptions. No ledger money is allocated by this simulation. See DEMO_SERVICING.md for source review, controls and 350-test verification.

## Before/after payment review

Reuse current Manrope, green/red/amber state tokens and compact table styling. After customer/account and entered payment details, show Before/After demo due and status side by side, then the installments covered by this virtual receipt. Five rows remain visible; additional rows expand on request. Excess and backdated redistribution are explicit. Keep the action a single Record demo payment button, with Edit/Cancel retained. Status text accompanies color; no predicted effect is described as posted ledger allocation. A changed account forces updated review rather than accepting stale consequences.

Implemented payment-impact review with red/green amounts and text status, per-installment virtual coverage, optional expanded rows, excess and backdating explanations. Self-review found excess repetition and mobile table clipping; compact payment facts and a fixed-width wrapping table now keep the comparison in the first screen and every coverage column visible. Important unapplied/unchanged-principal/no-real-funds consequences remain before confirmation. Record-integrity explanation is an explicit disclosure; confirmed retries and stale-account re-review are tested. Full suite 359 passed, final focused 15 passed, browser desktop/phone workflows passed; see DEMO_SERVICING.md for evidence.

### Linked reversal review — October 28, 2026

Use the existing payment review's Manrope, green #204c41, ink #1c2c27,
paper #f7f9f7, red #942a24 and amber #79510d. Receipt identity, exact amount
and required reversal reason precede a compact Before / After reversal
comparison. Red/green/amber always have explicit status labels. Show net lost
installment coverage and excess changes below, with longer detail expandable.
Keep the original receipt and its correction together; a reversal is not a
refund. Reuse the current comparison rather than adding a new dashboard.
The review must remain fresh under concurrent receipts and corrections.

Reversal review critique and verification: removed the repeated amount row
and shortened the heading so the impact comparison stays within the first
900px even at 320px width. The original receipt link still identifies the exact
amount/date; the full-reversal consequence remains explicit. Compact installment
numbers avoid broken header words. Final Firefox checks at 1440/390/320px have
no outer or coverage-table overflow. Full PostgreSQL suite: 369 tests passed.

### Daily payments — October 28, 2026

Reuse the website brand green #204c41, ink #1c2c27, paper #f7f9f7,
blue #edf4fa, amber #fff4d8 and correction red #942a24, with Manrope.
Left-align a compact date navigator, then receipt/reversal/net totals in one
scan line, a method breakdown and source-linked entries. Keep custom date/basis
controls in a disclosure, open for invalid or custom selections. Add a visible
Daily payments link on BHPH; retain the existing register URL and single bounded
capture. Do not add a new dashboard or infer that green means bank settlement.
Mobile totals should fit above details, with labeled entry rows for readable
source links. Old methods remain explicitly Not recorded. This extends the
existing register rather than presenting duplicate payment destinations.

Daily summary verification: retained the existing register rather than adding a
second page. Cash/Check/Other precede Not recorded in the breakdown. Review at
1440/390/320px keeps all three top totals within the first viewport; mobile source
entries become labeled rows without a wide grid. Reversals carry both negative
amounts and text; positive totals are not labeled settled. Full PostgreSQL suite
376 tests passed; browser method entry and source links passed. No staff usability
validation is claimed.

### BHPH worklist — October 28, 2026

Keep Manrope, green #204c41, paper #f7f9f7 and ink #1c2c27. Past-due
#942a24/red, due-today #79510d/amber and up-to-date #235532/green must retain
text labels. Place All/Past due/Due today/Up to date/Not calculated links above
the existing compact search, with visible sort selection. Preserve customer,
vehicle and amount due, add next unpaid date and direct Record payment. Remove
unapplied funds from this worklist to avoid adding another column; it remains
available inside each account. Keep latest receipt as context, never call it a
balance. Desktop rows stay tabular; mobile rows retain labeled dates/status and
reachable actions. No counts that imply more coverage than the bounded capture.
This is a synthetic worklist, not an automated collection queue.

Worklist critique: the shared toolbar's narrow-screen overrides initially squeezed
search and sort into unreadable widths. The worklist now uses a two-row mobile
control grid and a bounded desktop sort width. Account actions stack on desktop
and have explicit spacing on mobile. Removed the redundant heading sentence to
leave more room for accounts. This is a proportion correction, not a new dashboard.

Final worklist browser checks at 1440/390/320px verify no outer overflow,
search and sort controls each at least 140px wide, and nonoverlapping Open
account / Record payment actions. Before/after source projections and navigation
were checked independently of screenshots. Full PostgreSQL suite 384 tests passed;
18 focused SQLite tests passed. Staff workflow validation is still outstanding.

### Printable synthetic payment receipt — October 28, 2026

Reuse Manrope and the Railet wordmark with green #204c41, ink #1c2c27,
paper #f7f9f7, rule #dbe3dc and reversal red #942a24. Use one left-aligned
receipt sheet, compact labeled facts, exact recorded amount and a prominent
Print receipt action. Keep account/history/reversal actions outside the sheet.
On paper use black text, clear rules, explicit demo/reversal labels and no app
navigation. Avoid a second print route or duplicate data representation. Current
customer identity and frozen vehicle context must be labeled as such; no guessed
vehicle, payoff or payment allocation. Long references wrap and may continue on
another page rather than being cut off. Browser printing does not prove delivery.

Print critique: actual PDF checks caught a legacy footer{display:none} rule and
missing numeric glyph mappings in the variable-font PDF text layer. Receipt
footers now explicitly display, and print uses static sans-serif fonts with
normal numeric features and no ligatures. Screen typography remains Manrope.
Verification must check extracted amounts and provenance as well as appearance.

Receipt verification: 389 PostgreSQL tests passed. Final browser/PDF checks keep
exact amounts extractable and provenance/demo/reversal labels visible, including
letter/A4 and a long reference. Normal/reversed examples fit one page after
compact print spacing. Screen checks at 1440/390/320px have no outer overflow.
No staff validation or physical-printer operation is claimed.

### Deal desking and inline vehicle — October 29, 2026

Manrope remains the workspace family. Use green #204c41 for saves, ink #1c2c27,
paper #f7f9f7, white #ffffff, border #dbe3dc and amber #fff4d8 for assumptions.
Left-align a prominent Deal type row, vehicle/buyer selection side by side, then
visible pricing/tax and financing with a sticky right-hand estimate. On mobile
stack the summary with a readable live payment/balance instead of a wide grid.

[Deal type: Cash / Outside financing / BHPH]
[Vehicle: choose / add new] [Buyer: choose / add new]
[Price, fees, FL county]   [Draft balance]
[Trade, down]             [Monthly illustration]
[Financing method/term]   [Save deal]

Reuse progressive disclosure only for secondary identity/cost/address fields,
not deal type, price or selected financing. Do not turn this into generic metric
cards. Inline vehicle creation must reuse inventory validation/VIN review/audit
and save atomically with customer/deal, with retry protection. Tax feedback must
show missing county/review needs rather than an authoritative $0 estimate.
Precomputed illustrations require a supplied finance charge; do not interpret a
contract rate as an add-on rate or call any illustration APR/live servicing.

Desking critique and browser checks: place the saved type above the overview;
keep selected financing expanded, order method/frequency/count/charge together,
and show the annual-rate input only for the monthly simple illustration. This
avoids presenting an unused rate as the driver of precomputed totals. Removed
repeated long method help and empty trade amounts from the initial creation view.
Tax remains read-only in automatic mode; the live backend receives prices/tax/term
fields only. An unsupported 2027 date clears the unverified estimate, explains the
scope and retains price entries. Screen checks at 1440/390/320px show no outer
overflow. With JavaScript unavailable, both identity paths are visible and server
validation controls the selected path; with JavaScript active, native validation
and conditional disabling are restored. Staff usability validation remains pending.

Full PostgreSQL regression: 404 tests passed. Browser verification completed inline
vehicle/customer creation, tax/charge preview, save, existing-desk price update and
preserved first-event history. Another read-only pass checked simple-monthly terms,
unsupported-year feedback, visible top-level type, automatic tax read-only behavior
and 1440/390/320px layouts. Review artifacts are private under `.local/desking-review/`.
No public publication or production transaction behavior was enabled.
