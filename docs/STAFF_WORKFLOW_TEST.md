# Synthetic dealership staff workflow protocol

Status: prepared for a future session; no staff session has been completed or
observed by Codex. Developer checks are not staff validation. This is a test of
navigation and understanding, not a real sale, loan, payment or legal review.

## Moderator setup

- Use an isolated development workspace with `RAILET_DEBUG=1` and the synthetic
  gates listed in [the walkthrough](BHPH_DEMO_WALKTHROUGH.md#prerequisites).
  Confirm the test-workspace notice and that all relevant gates are enabled;
  do not use a production system or real records. Sign in as an owner or staff
  member at Home before handing over the screen. A viewer cannot perform writes.
- Choose a unique invented stock number and invented customer name for each
  session. Do not pre-create their vehicle, customer, deal or account. Prepare
  a separate developer practice fixture if you want to check setup; never reset
  posted or frozen history to make room for another participant.
- Give the participant the scenario below as written, one task at a time, without
  naming menus, pointing or clicking. Ask them to think aloud. Record the first
  hesitation and wrong turn before offering help; label a task assisted if you
  intervene. No time target is a pass/fail threshold. Stop if real information
  appears. Do not request or retain passwords, actual customer details or files.

## Uncoached end-to-end tasks

Provide the following **invented** facts on a paper or onscreen scenario card:

> A customer named **Morgan Example** is interested in stock **PRACTICE-\<unique\>**,
> a 2021 Synthetic Sedan. The VIN, title brand and mileage are unknown. The
> practice vehicle price is **$1,500.25**, planned down payment **$300.00**, and
> manually supplied practice tax **$0.00** for “Synthetic training example.”
> Use buy here, pay here, a **precomputed** finance charge of **$150.00**,
> **12 monthly** payments beginning on the first of next month, and creditor
> **Synthetic Creditor**. These figures are invented and not tax or contract advice.

Replace the placeholder in the stock number with a unique suffix. Keep the VIN
blank and unknown title and mileage facts unverified; do not invent contact data.
Then give these prompts in order, without providing the moderator checks below:

1. “Put this vehicle and customer into the system so we can find them later.”
2. “Start a deal for this customer and vehicle with the practice figures and
   financing terms on the card. Save it and show me what you saved.”
3. “Review the saved deal and preserve a completion rehearsal of the facts.
   If the system asks about missing information, use ‘Synthetic practice;
   title and mileage have not been verified’ as the review note.”
4. “Set up a test BHPH account for this completed rehearsal. Use **$1,200.25**
   as the invented opening principal, today's date and source **Synthetic
   opening example**. Show me the account before moving on.”
5. “Record a **$25.50 cash** test payment for today, using reference **Synthetic
   payment example**. Show me the receipt.”
6. “That test payment was entered by mistake. Correct it using reason **Practice
   entry made by mistake**, then show me the original and the correction.”

If they cannot complete a task, record where they stopped, offer a neutral
question such as “What were you expecting here?”, and record any assistance.
Do not silently finish the action for them. Ask afterward what was uncertain,
how they understood the frozen rehearsal, and whether they believe any real
money or loan was created.

## Moderator checks after each task

- The vehicle and customer are distinct, findable records with the scenario's
  identity; blank/unknown VIN, title and mileage have not been presented as verified.
- One saved BHPH draft links the correct records and shows the entered price,
  manual practice tax and reason, planned down payment and proposed terms.
  A planned down payment does not record a receipt.
- One completed rehearsal retains the reviewed facts and a frozen summary;
  its worksheet is locked, the vehicle is not marked sold, and no account or
  payment was created by completion. Do not void this rehearsal for this task.
- The new account links that completion and customer/vehicle, with opening
  principal **$1,200.25** and the invented source. It is a synthetic opening,
  not a contractual debt or an automatic copy of the draft balance. Without an
  independently selected demo schedule, amount due is **Not calculated** and
  late status is **Not assessed**; do not expect a $300 balance here.
- Exactly one **$25.50** cash receipt appears as unapplied; its receipt identifies
  the account and vehicle. One linked full reversal retains the original, its
  reason and the correction. After reversal, net unapplied payments are **$0.00**
  and opening principal remains **$1,200.25**. No refund or real funds moved.

## Private observation template

Keep completed notes in a private location, outside the repository. Use a session
code instead of a participant name. Share only sanitized findings with consent.

```text
Session code / date / moderator:
Device, browser, viewport, input/accessibility needs (optional):
Scenario stock suffix (invented only):
Task # / start and finish / outcome (unassisted, assisted, stopped):
First action / hesitation or wrong turn / help given:
Expected versus observed / short quote with permission:
Moderator record checks and discrepancies:
Safety or accessibility concern / impact / proposed follow-up:
Participant's understanding of rehearsal and money movement:
```

Do not infer usability from a single completion. Turn observed problems into
small, sanitized issues and retest changes with staff before claiming validation.

## Existing payment-only usability session

Status: prepared; no staff session has been completed or observed by Codex.
Developer browser checks are separate evidence and do not establish usability.

Use a dedicated synthetic account with a verified demo baseline, $300 demo due,
no receipts, an identifiable invented customer and a linked practice vehicle.
Keep a second account for developer checks so the participant starts fresh.
Never use real customer names, debt or funds. Start from the normal Home page,
not a deep link that reveals where to go. Sign in before handing over the screen.

Read this task without showing menu names or clicking for the participant:

> Jordan Practice has paid $300 cash today. Record the payment and prepare a
> printable receipt. Tell me when you think the task is finished.

Once finished, give the next task:

> That payment entry was made by mistake. Correct it, then tell me what the
> account now shows as due. Use “Practice entry made by mistake” as the reason.

Ask the participant to think aloud. Do not point at buttons, prescribe routes or
use words such as “obvious” or “easy.” If help is needed, note the point where
unassisted progress stopped before helping. Let the participant cancel the print
dialog or save an invented PDF; printing is not evidence of delivery. No actual
cash, checks or refunds are involved. Stop if real information is being entered.

Record each task separately: start/finish time, first click, wrong turns, requested
help, confusing labels, what they expected and an exact short quote. Ask “What did
you expect here?” after a hesitation. Do not convert time targets into pressure,
call a coached completion unassisted, or infer ease from a single successful click.
Afterward ask which part felt most uncertain and what they would call that screen.

Moderator checks after the participant finishes (do not show these beforehand):

- Correct customer/account/vehicle selected; one $300 Cash receipt, not duplicates.
- Preview understood and confirmed; demo due changes from $300 to $0.
- Receipt shows method, account/vehicle, amount and demo marking; print opens.
- One linked full reversal with reason; original receipt stays visible.
- Demo due returns to $300; principal stays $1,200 and net unapplied returns to $0. (Simulated demo due is an opt-in monthly precomputed coverage projection; posted receipts and reversals remain unapplied in the ledger and do not reduce contractual principal or calculate payoff.)
- Ask whether the participant understands that this was synthetic evaluation.

Keep observations private and exclude credentials, actual customer details and
financial documents from issue reports. Turn each observed problem into a small
issue: trigger, expected behavior, observed behavior, impact and proposed change.
Prioritize wrong-account/payment/correction risks ahead of cosmetic preference.
Re-test fixes with the participant before calling the workflow staff-validated.
Do not silently reset immutable ledger history; prepare a new practice account
when another clean attempt is needed.

## Preparation and developer rehearsal — October 28, 2026

A separate invented developer account completed Home -> BHPH -> customer search
-> correct account/vehicle -> $300 Cash receipt -> before/after preview -> print
PDF -> full linked reversal -> restored $300 demo due. Exactly one receipt and
one reversal were retained; opening principal stayed $1,200 and net unapplied
returned to $0. The PDF retained amount, method, customer, linked stock and demo
marking. This was automated developer verification, not an uncoached staff test.

A separate Jordan Practice account was prepared with $300 demo due and no receipt
or reversal, and remained unchanged throughout the developer rehearsal. Start
from Home and give only the task above; do not use a deep link as a navigation
hint. Local account IDs/evidence and a blank observation template are under
ignored `.local/staff-workflow-review/`. No passwords or real customer records
are included in this protocol. Actual participant completion, timing, wrong turns,
quotes and usability findings remain unrecorded. No product changes were made
based on invented staff feedback.
