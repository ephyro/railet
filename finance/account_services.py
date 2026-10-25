# SPDX-License-Identifier: MPL-2.0
from django.db import transaction
from django.shortcuts import get_object_or_404
from deals.account_context import eligible_account_drafts, account_draft_snapshot
from .models import DemoBook, DemoAccountContext
from .services import require_demo, require_member, LedgerError
from .schedule_services import result_digest


@transaction.atomic
def link_draft(*, dealership_id, book_id, deal_id, actor, expected_digest):
    require_demo()
    require_member(actor, dealership_id)
    book = get_object_or_404(DemoBook.objects.select_for_update(), pk=book_id,
                            dealership_id=dealership_id, customer__dealership_id=dealership_id)
    prior = DemoAccountContext.objects.filter(book=book).first()
    if prior:
        if prior.deal_id != deal_id or prior.snapshot_sha256 != expected_digest:
            raise LedgerError('This account already has saved draft context. It cannot be replaced.')
        return prior
    deal = get_object_or_404(eligible_account_drafts(dealership_id=dealership_id, customer_id=book.customer_id).select_for_update(of=('self',)), pk=deal_id)
    snapshot = account_draft_snapshot(deal)
    if result_digest(snapshot) != expected_digest:
        raise LedgerError('The draft changed after preview. Review its current details before linking.')
    return DemoAccountContext.objects.create(book=book, deal=deal, snapshot=snapshot,
                                            snapshot_sha256=expected_digest, created_by=actor)


def customer_accounts(*, dealership_id, customer_id):
    """Read interface for the shared customer profile; respect the demo gate."""
    from django.conf import settings
    if not getattr(settings, 'DEMO_LEDGER_ENABLED', False):
        return DemoBook.objects.none()
    return DemoBook.objects.filter(dealership_id=dealership_id, customer_id=customer_id,
                                   customer__dealership_id=dealership_id)
