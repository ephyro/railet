# Printable synthetic payment receipts

The existing authorized receipt page now has Print receipt and a single sheet
shared by screen and browser printing. It shows exact retained amount, method,
effective/entry dates, actor and reference, plus canonical customer/account IDs.
Vehicle/stock identity comes only from a verified frozen account context; an
unlinked account says No vehicle linked. Current customer/workspace/display
names are explicitly labeled current. This is a current journal view, not a
stored historical receipt artifact, original customer document or legal receipt.

The sheet always says Demonstration only and no real funds received/processed.
Receipts remain unapplied; no interest, fees, principal reduction, payoff, tax,
settlement, provider refund or balance claim is added. A linked full reversal
preserves the original amount and displays correction ID, amount, effective date,
entry time, reason and actor. The view locks the book while reading the payment,
reversal and context so concurrent ledger writers cannot produce a mixed read.
Invalid frozen context fails closed. Existing ledger demo gate, dealership scope,
viewer read access, private/no-store and nosniff headers remain required.

Printing uses the browser dialog, which can also save PDF. There is no new route,
PDF dependency, email delivery, background print job or public file. Print CSS
hides app navigation, account actions and workspace banners, while retaining
sheet-specific demo/reversal labels in black and white. References wrap without
truncation, including on narrow screens and across paper pages. Without JavaScript,
use the browser's Print menu. Cancelling printing changes nothing; invoking the
dialog is not represented as successful printing or delivery, and no print event
or immutable document artifact is stored. A later reprint may include a newer
linked reversal/current display name; the view-generation timestamp is shown.

Scope review: this adds a presentation of the existing synthetic journal, no new
regulated allocation behavior, legal receipt wording or statutory deadline.
RAILET_PLAN.md and LEDGER_FOUNDATION.md source/applicability records still apply.
Real receipts require applicable legal/operational review, receipt identity
snapshots/versioning, delivery and retention decisions before live use. No
production gate is changed and no real customer data is authorized.

## Verification

Full PostgreSQL suite: **389 tests passed in 132.967s**, no skips. Five new
integration cases verify exact facts/method, immutable frozen vehicle identity
after inventory edits, current customer labeling after profile edits, escaped
references, unchanged journal/export history, linked reversal evidence, viewer
printing, foreign/gate/POST denial and invalid-context failure. Existing payment
and reversal preview/retry/concurrency coverage remains passing. Migration
consistency reports no changes.

Firefox checks followed an invented $13.37 Cash payment on the dedicated synthetic
browser account through review/confirmation to its printable receipt. The print
button invokes the browser dialog without claiming successful printing/delivery.
Final read-only checks generated letter and A4 PDFs from a retained linked receipt,
a letter PDF with its full linked reversal, the $13.37 receipt and a long-reference
case. Text extraction verified exact amounts, methods, references, source vehicle,
reversal evidence, demo labels and provenance; app controls were absent. Normal
and reversed examples fit one page. Screens at 1440/390/320px do not overflow.
These are developer checks, not physical-printer testing or staff validation.

Actual PDF checks caught and corrected a legacy hidden-footer style, missing
numeric text mappings with the variable screen font and a reversal footer spilling
to another page. Printing now uses static sans-serif fonts and compact spacing;
screen typography remains the Railet Manrope family. Long text can still flow to
additional pages rather than be truncated. Private evidence is under ignored
`.local/print-receipt-review/`. No public files, delivery or production deployment.
