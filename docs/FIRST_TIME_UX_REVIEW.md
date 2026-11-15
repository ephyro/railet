# First-time workflow review

Developer evaluation, November 2026, using the local synthetic preview. This is
not a substitute for observation of dealership staff who have not seen Railet.

## Walkthrough and changes

- Home had two similarly named follow-up destinations. It now distinguishes
  customer follow-ups and appointments from deal follow-ups assigned to the user.
- The customer follow-up queue now explains how to add a follow-up, uses a compact
  search bar, and groups each customer's activity, owner, date and action on mobile.
- Customer profiles previously displayed only the 25 most recent activity entries
  without a path to older notes. A scoped, paginated history now exposes all entries.
- Customer profiles now identify a frozen completion rehearsal accurately rather
  than calling it a draft.
- On phones, the new-deal screen placed Save above vehicle/customer entry. The
  deal fields now precede the estimate and Save; the full estimate remains visible.
- The BHPH account now explains that a demo payment schedule is needed to show
  simulated due and late status, with a clearly named setup link. The account
  list states up front that its statuses are simulations and payments are unapplied.
- The investment report's phone view now groups each vehicle's labeled figures
  together instead of hiding most of the row behind horizontal scrolling.

## Developer verification

Firefox inspection covered Home, Vehicles, Customers, customer follow-ups, new
deal, BHPH accounts and inventory investment at 1440 and 390 pixels. No outer
page overflow was detected in those views. Screenshots were inspected for Home,
follow-ups, vehicle list, deal entry and BHPH. A separate browser exercise created,
assigned, rescheduled, completed and reopened a synthetic follow-up. Deal creation
was exercised with a synthetic vehicle/customer, tax estimate, financing illustration
and saved history at 1440/390/320 widths. PostgreSQL customer/navigation tests
passed 16 checks; SQLite activity tests passed 10. These are developer checks,
not observed user comprehension or regulatory validation.

A further Firefox exercise created a synthetic customer and BHPH account, reviewed
and recorded a synthetic payment, and checked the receipt and ledger entries. The
finance account, schedule and worklist test suites passed 35 tests on both SQLite
and PostgreSQL. The seven-page desktop/phone overflow check was repeated after
the BHPH wording change; the account setup path was checked at 1440, 390 and
320 pixels.
The investment report's internal table was checked separately at those widths;
the phone layouts no longer require horizontal scrolling to read its figures.

## Further usability work

- Have someone unfamiliar with Railet locate a customer, add an appointment,
  start a deal and record a synthetic BHPH payment without coaching; record where
  they hesitate and compare against this assessment.
- The customer follow-up queue does not yet have a quick assignment filter.
- The BHPH page is still a dense list when many accounts exist; test grouping,
  useful default ordering and terminology with staff before changing it.
- On mobile, the new-deal form remains long because it contains financing and tax
  controls. Test whether users can complete it comfortably and whether a progress
  indicator or smaller steps would help without hiding important information.
- Synthetic-only banners and calculation limitations must remain clear until live
  workflows and security/legal gates are satisfied.
