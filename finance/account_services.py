# SPDX-License-Identifier: MPL-2.0
from django.db import transaction
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from deals.account_context import eligible_account_drafts, account_draft_snapshot, completed_account_snapshot
from .models import DemoBook, DemoAccountContext
from .services import require_demo, require_posting_member, LedgerError
from .schedule_services import result_digest


@transaction.atomic
def link_draft(*, dealership_id, book_id, deal_id, actor, expected_digest):
    from core.models import Dealership
    require_demo()
    # Share the completion/void lock before reading eligibility or locking a book.
    Dealership.objects.select_for_update().get(pk=dealership_id)
    require_posting_member(actor, dealership_id)
    book = get_object_or_404(DemoBook.objects.select_for_update(), pk=book_id,
                            dealership_id=dealership_id, customer__dealership_id=dealership_id)
    prior = DemoAccountContext.objects.filter(book=book).first()
    if prior:
        if prior.deal_id != deal_id or prior.snapshot_sha256 != expected_digest:
            raise LedgerError('This account already has saved draft context. It cannot be replaced.')
        return prior
    deal = get_object_or_404(eligible_account_drafts(dealership_id=dealership_id, customer_id=book.customer_id).select_for_update(of=('self',)), pk=deal_id)
    if DemoAccountContext.objects.filter(deal=deal).exclude(book=book).exists():
        raise LedgerError('This draft already has a demo account. Open the existing account instead.')
    snapshot = account_draft_snapshot(deal)
    if result_digest(snapshot) != expected_digest:
        raise LedgerError('The draft changed after preview. Review its current details before linking.')
    return DemoAccountContext.objects.create(book=book, deal=deal, snapshot=snapshot,
                                            snapshot_sha256=expected_digest, created_by=actor)


@transaction.atomic
def link_completed(*, dealership_id, book_id, deal_id, actor, expected_digest):
    """Link an existing synthetic account using verified, frozen completion facts."""
    from core.models import Dealership
    from deals.models import DraftDeal
    require_demo()
    Dealership.objects.select_for_update().get(pk=dealership_id)
    require_posting_member(actor, dealership_id)
    deal = get_object_or_404(DraftDeal.objects.select_for_update(), pk=deal_id,
        dealership_id=dealership_id, buyer__dealership_id=dealership_id,
        vehicle__dealership_id=dealership_id, deal_type='bhph', archived_at__isnull=True,
        demo_completion__isnull=False)
    book = get_object_or_404(DemoBook.objects.select_for_update(), pk=book_id,
        dealership_id=dealership_id, customer__dealership_id=dealership_id, customer_id=deal.buyer_id)
    try:
        snapshot = completed_account_snapshot(deal)
    except (ValidationError, KeyError, TypeError, AttributeError) as error:
        raise LedgerError('The completed rehearsal could not be verified.') from error
    if result_digest(snapshot) != expected_digest:
        raise LedgerError('The completed rehearsal changed after preview. Review it again.')
    prior = DemoAccountContext.objects.filter(book=book).first()
    if prior:
        if prior.deal_id != deal.pk or prior.snapshot_sha256 != expected_digest or result_digest(prior.snapshot) != prior.snapshot_sha256:
            raise LedgerError('This account already has different or unverifiable context.')
        return prior
    if DemoAccountContext.objects.filter(deal=deal).exists():
        raise LedgerError('This rehearsal already has a demo account.')
    return DemoAccountContext.objects.create(book=book, deal=deal, snapshot=snapshot,
                                            snapshot_sha256=expected_digest, created_by=actor)


def customer_accounts(*, dealership_id, customer_id):
    """Read interface for the shared customer profile; respect the demo gate."""
    from django.conf import settings
    if not getattr(settings, 'DEMO_LEDGER_ENABLED', False):
        return DemoBook.objects.none()
    return DemoBook.objects.filter(dealership_id=dealership_id, customer_id=customer_id,
                                   customer__dealership_id=dealership_id)


def draft_account(*, dealership_id, deal_id):
    """Public read interface for draft navigation; never infer a new account."""
    from django.conf import settings
    if not getattr(settings, 'DEMO_LEDGER_ENABLED', False):
        return None
    return DemoAccountContext.objects.filter(
        deal_id=deal_id, book__dealership_id=dealership_id,
        book__customer__dealership_id=dealership_id,
    ).select_related('book').first()


@transaction.atomic
def open_from_draft(*, dealership_id, deal_id, actor, opening_amount, opening_on,
                    source_reference, request_key, expected_digest):
    """Atomic synthetic opening + frozen draft context; never loan origination."""
    from core.models import Dealership
    from deals.models import DraftDeal
    from .services import open_book, key, cents, text, effective
    require_demo()
    request_key = key(request_key)
    amount = cents(opening_amount)
    source = text(source_reference, 'Synthetic opening source', 300)
    opening_on = effective(opening_on)
    # Match opening's dealership lock, then serialize competing requests for this draft.
    Dealership.objects.select_for_update().get(pk=dealership_id)
    require_posting_member(actor, dealership_id)
    deal = get_object_or_404(DraftDeal.objects.select_for_update(), pk=deal_id,
                            dealership_id=dealership_id, buyer__dealership_id=dealership_id,
                            vehicle__dealership_id=dealership_id)
    prior = DemoBook.objects.filter(dealership_id=dealership_id, creation_key=request_key).first()
    if prior:
        saved = DemoAccountContext.objects.filter(book=prior, deal=deal).first()
        entry = prior.postings.get(kind='opening')
        if not saved or result_digest(saved.snapshot) != saved.snapshot_sha256:
            raise LedgerError('Saved account context failed its integrity check.')
        if saved.snapshot.get('source') == 'completed-rehearsal':
            try:
                completed_account_snapshot(deal)
            except (ValidationError, KeyError, TypeError, AttributeError) as error:
                raise LedgerError('The completed deal could not be verified.') from error
        if (prior.created_by_id, prior.opening_on, prior.source_reference,
                          entry.amount_cents, saved.snapshot_sha256) != (
                              actor.pk, opening_on, source, amount, expected_digest):
            raise LedgerError('This request was already used with different opening facts.')
        return prior, False
    if deal.deal_type != 'bhph' or deal.archived_at:
        raise LedgerError('Use an active BHPH draft before opening a demo account.')
    if DemoAccountContext.objects.filter(deal=deal).exists():
        raise LedgerError('This draft already has a demo account. Open the existing account instead.')
    completed = DraftDeal.objects.filter(pk=deal.pk, demo_completion__isnull=False).exists()
    try:
        snapshot = completed_account_snapshot(deal) if completed else account_draft_snapshot(deal)
    except (ValidationError, KeyError, TypeError, AttributeError) as error:
        raise LedgerError('The completed deal could not be verified. Review its frozen record.') from error
    if result_digest(snapshot) != expected_digest:
        raise LedgerError('The draft changed after preview. Review the current details before opening the account.')
    book, _ = open_book(dealership_id=dealership_id, customer_id=deal.buyer_id, actor=actor,
                        label=f'Demo BHPH draft #{deal.pk}', source_reference=source,
                        opening_on=opening_on, opening_amount=opening_amount, request_key=request_key)
    if completed:
        DemoAccountContext.objects.create(book=book, deal=deal, snapshot=snapshot,
                                          snapshot_sha256=expected_digest, created_by=actor)
    else:
        link_draft(dealership_id=dealership_id, book_id=book.pk, deal_id=deal.pk,
                   actor=actor, expected_digest=expected_digest)
    return book, True


def completion_has_account(*, deal_id):
    """Fail closed for any retained account link, including when the demo gate is off."""
    return DemoAccountContext.objects.filter(deal_id=deal_id).exists()
