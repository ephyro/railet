# Synthetic BHPH workflow review

This walkthrough demonstrates navigation and retained records. It does not originate a loan, allocate payments, validate Florida paperwork or permit real customer data. Use invented names and records only.

## Owner preparation

1. Under Customers, add an invented customer. Under Vehicles, add an invented vehicle with its actual synthetic title status; do not default unknown facts to reassuring values.
2. Open the vehicle and choose Start a deal. Select the customer already saved. Under More deal details, choose Buy here, pay here. Example worksheet: price $1,500.25 and planned down payment $300.00. Saving does not record that down payment.
3. On the saved deal, choose Set up BHPH account. Enter an explicit invented opening principal of $1,200.25 and an invented source reference. Review before opening. The amount is independently entered for this rehearsal, not automatically converted from the worksheet into debt.
4. The account reuses the same customer and captures the saved vehicle context. Choose Record payment. Enter $25.50 and an invented reference, then Review demo payment. Try Edit before posting: the entered amount remains and can be reviewed again.
5. Record the demo payment, then choose View payment history on its receipt. Verify the receipt is present, the opening principal remains $1,200.25, and net unapplied payments are $25.50. The payment has not been allocated to principal, interest or fees; no real money moved.
6. Return to the saved deal and customer record. Their account links should open the same BHPH account. Reopening account setup must not create a duplicate account.

## Uncoached staff review

After preparing an invented account, give the reviewer a goal: “Find this customer's account, record an invented $25.50 payment, and show me its receipt.” Let them choose the route. Observe where they hesitate, confuse Deals with BHPH, lose the customer identity, or cannot find the next step. Do not call this validated until staff have actually tried it.

Record only synthetic observations: the task, where the reviewer paused, the expected action, and the outcome. Avoid customer records, passwords and private vendor captures. Correcting a saved payment must use the linked correction workflow, never an editable receipt amount.

## Developer verification

A full browser run creates customer, vehicle and BHPH deal through the forms, opens an explicit synthetic account, exercises payment preview -> edit -> review -> save, finds the receipt in history and checks unchanged principal plus unapplied funds. It also verifies the customer/deal links and checks desktop/phone layouts. Local evidence is retained in ignored `.local/bhph-workflow-review/`.

The run discovered that edit-before-posting previously submitted back to the confirmation URL. Explicit preparation form actions now restore the review path for account opening, receipts and corrections. A regression test verifies all three edit/review/save routes. Financial services, posting rules, calculation versions and production gates are unchanged.
