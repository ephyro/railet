# BHPH payment usability session

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
- Demo due returns to $300; principal stays $1,200 and net unapplied returns to $0.
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
