# SPDX-License-Identifier: MPL-2.0
from datetime import date
from decimal import Decimal, InvalidOperation
import uuid
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from core.models import Dealership, Membership
from customers.models import Customer
from .models import DemoBook, DemoPosting


class LedgerError(ValidationError):
    pass


def require_demo():
    if not getattr(settings,'DEMO_LEDGER_ENABLED',False):
        raise PermissionDenied('Synthetic ledger rehearsal is disabled.')


def require_member(actor, dealership_id):
    if not Membership.objects.filter(user=actor,dealership_id=dealership_id,role__in=[Membership.Role.OWNER,Membership.Role.STAFF]).exists():
        raise PermissionDenied('Only dealership owners and staff can post synthetic entries.')


def cents(value):
    if isinstance(value,(float,bool)):
        raise LedgerError('Enter an exact decimal amount, not a binary floating-point value.')
    try:
        amount=Decimal(value)
    except (InvalidOperation,ValueError,TypeError):
        raise LedgerError('Enter a valid amount.')
    if not amount.is_finite() or amount <= 0 or amount > Decimal('9999999999.99'):
        raise LedgerError('Enter a positive amount no greater than 9999999999.99.')
    # Inspect the exact coefficient before arithmetic can round under Decimal's context.
    digits=amount.as_tuple().digits
    exponent=amount.as_tuple().exponent
    if exponent < -2 and any(digits[exponent+2:]):
        raise LedgerError('Use at most two decimal places; amounts are not rounded automatically.')
    from decimal import localcontext
    with localcontext() as ctx:
        ctx.prec=max(28,len(digits)+3)
        return int(amount*100)


def key(value):
    try:return uuid.UUID(str(value))
    except (ValueError,TypeError,AttributeError):raise LedgerError('A valid idempotency key is required.')


def text(value,label,limit):
    if not isinstance(value,str) or not value.strip() or len(value.strip())>limit:
        raise LedgerError(f'{label} is required and must be at most {limit} characters.')
    return value.strip()


def effective(value,opening=None):
    if not isinstance(value,date) or hasattr(value,'hour'):
        raise LedgerError('An explicit effective date is required.')
    if value>timezone.localdate() or (opening and value<opening):
        raise LedgerError('Use a date from the opening date through today for this rehearsal.')
    return value


@transaction.atomic
def open_book(*,dealership_id,customer_id,actor,label,source_reference,opening_on,opening_amount,request_key):
    require_demo();require_member(actor,dealership_id)
    amount=cents(opening_amount);request_key=key(request_key)
    label=text(label,'Demo label',100);source=text(source_reference,'Synthetic opening source',300);opening_on=effective(opening_on)
    Dealership.objects.select_for_update().get(pk=dealership_id)
    if not Customer.objects.filter(pk=customer_id,dealership_id=dealership_id).exists():
        raise LedgerError('Choose a customer from this dealership.')
    prior=DemoBook.objects.filter(dealership_id=dealership_id,creation_key=request_key).first()
    if prior:
        entry=prior.postings.get(kind='opening')
        if (prior.customer_id,prior.label,prior.source_reference,prior.opening_on,entry.amount_cents,prior.created_by_id)!=(customer_id,label,source,opening_on,amount,actor.pk):
            raise LedgerError('This creation key was used for different opening facts.')
        return prior,False
    book=DemoBook.objects.create(dealership_id=dealership_id,customer_id=customer_id,label=label,source_reference=source,opening_on=opening_on,creation_key=request_key,created_by=actor)
    DemoPosting.objects.create(book=book,kind='opening',amount_cents=amount,debit='principal',credit='opening_offset',actor=actor,reason=source,effective_on=opening_on,request_key=request_key)
    return book,True


@transaction.atomic
def record_receipt(*,dealership_id,book_id,actor,amount,effective_on,reason,request_key,payment_method=DemoPosting.PaymentMethod.UNSPECIFIED):
    require_demo();require_member(actor,dealership_id)
    amount=cents(amount);reason=text(reason,'Synthetic receipt reference',300);request_key=key(request_key)
    if payment_method not in DemoPosting.PaymentMethod.values:raise LedgerError('Choose Cash, Check, Other or Not recorded as the payment method.')
    book=DemoBook.objects.select_for_update().get(pk=book_id,dealership_id=dealership_id,customer__dealership_id=dealership_id)
    effective_on=effective(effective_on,book.opening_on)
    prior=book.postings.filter(request_key=request_key).first()
    if prior:
        if (prior.kind,prior.amount_cents,prior.reason,prior.effective_on,prior.actor_id,prior.payment_method)!=('receipt',amount,reason,effective_on,actor.pk,payment_method):
            raise LedgerError('This posting key was used for different facts.')
        return prior,False
    return DemoPosting.objects.create(book=book,kind='receipt',payment_method=payment_method,amount_cents=amount,debit='cash_control',credit='unapplied',actor=actor,reason=reason,effective_on=effective_on,request_key=request_key),True


@transaction.atomic
def reverse_receipt(*,dealership_id,book_id,posting_id,actor,effective_on,reason,request_key):
    require_demo();require_member(actor,dealership_id)
    reason=text(reason,'Correction reason',300);request_key=key(request_key)
    book=DemoBook.objects.select_for_update().get(pk=book_id,dealership_id=dealership_id,customer__dealership_id=dealership_id)
    original=book.postings.get(pk=posting_id)
    effective_on=effective(effective_on,original.effective_on)
    prior=book.postings.filter(request_key=request_key).first()
    if prior:
        if (prior.kind,prior.reverses_id,prior.reason,prior.effective_on,prior.actor_id)!=('reversal',original.pk,reason,effective_on,actor.pk):
            raise LedgerError('This correction key was used for different facts.')
        return prior,False
    if original.kind!='receipt':raise LedgerError('Only an original synthetic receipt can be reversed.')
    if book.postings.filter(reverses=original).exists():raise LedgerError('This receipt already has a correction; no second reversal was posted.')
    return DemoPosting.objects.create(book=book,kind='reversal',payment_method=original.payment_method,amount_cents=original.amount_cents,debit=original.credit,credit=original.debit,reverses=original,actor=actor,reason=reason,effective_on=effective_on,request_key=request_key),True


def reconcile(*,dealership_id,book_id):
    require_demo()
    book=DemoBook.objects.get(pk=book_id,dealership_id=dealership_id,customer__dealership_id=dealership_id)
    # One database statement for a consistent aggregate across all buckets.
    from django.db.models import Q, Count
    fields={"opening_count":Count("pk",filter=Q(kind="opening"))}
    for bucket in DemoPosting.Bucket.values:
        fields[bucket+'_debits']=Sum('amount_cents',filter=Q(debit=bucket))
        fields[bucket+'_credits']=Sum('amount_cents',filter=Q(credit=bucket))
    totals=book.postings.aggregate(**fields)
    debits={bucket:totals[bucket+'_debits'] or 0 for bucket in DemoPosting.Bucket.values}
    credits={bucket:totals[bucket+'_credits'] or 0 for bucket in DemoPosting.Bucket.values}
    return {'currency':'USD','debits':debits,'credits':credits,'net_debit':{b:debits[b]-credits[b] for b in debits},'total_debits_cents':sum(debits.values()),'total_credits_cents':sum(credits.values()),'opening_entries':totals['opening_count'],'balanced':sum(debits.values())==sum(credits.values()) and totals['opening_count']==1}
