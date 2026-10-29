# SPDX-License-Identifier: MPL-2.0
"""Read-only account discovery using authorized books and frozen vehicle facts."""
from django.db.models import Exists, OuterRef, Q
from customers.models import phone_key
from .models import DemoBook, DemoAccountContext


def search_accounts(*, dealership_id, query):
    books=DemoBook.objects.filter(dealership_id=dealership_id, customer__dealership_id=dealership_id).annotate(
        has_context=Exists(DemoAccountContext.objects.filter(book_id=OuterRef('pk'))),
    ).select_related('customer','account_context')
    if not query:
        return books
    number=query.removeprefix('#')
    valid_number=number.isascii() and number.isdigit() and len(number)<=19 and int(number)<=9223372036854775807
    if query.startswith('#') and valid_number:
        return books.filter(pk=int(number))
    condition=Q()
    fields=('label','customer__first_name','customer__last_name','customer__email',
            'account_context__snapshot__vehicle','account_context__snapshot__stock_number','account_context__snapshot__vin')
    for word in query.split():
        match=Q()
        for field in fields:
            match |= Q(**{field+'__icontains':word})
        condition &= match
    digits=phone_key(query)
    if digits and not any(c.isalpha() for c in query):
        condition |= Q(customer__phone_normalized__contains=digits)
    if valid_number:
        condition |= Q(pk=int(number))
    return books.filter(condition)


def with_account_activity(books):
    """One-statement journal projections; not due, delinquency or allocation."""
    from django.db.models import BigIntegerField, Case, F, Subquery, Sum, Value, When
    from django.db.models.functions import Coalesce
    from .models import DemoPosting
    latest = DemoPosting.objects.filter(book_id=OuterRef('pk'), kind='receipt').order_by('-entered_at', '-pk')
    funds = DemoPosting.objects.filter(book_id=OuterRef('pk')).order_by().values('book_id').annotate(
        net=Sum(Case(
            When(credit='unapplied', then=F('amount_cents')),
            When(debit='unapplied', then=-F('amount_cents')),
            default=Value(0), output_field=BigIntegerField(),
        )),
    )
    return books.annotate(
        activity_unapplied_cents=Coalesce(Subquery(funds.values('net')[:1]), Value(0), output_field=BigIntegerField()),
        latest_receipt_id=Subquery(latest.values('pk')[:1]),
        latest_receipt_cents=Subquery(latest.values('amount_cents')[:1]),
        latest_receipt_on=Subquery(latest.values('effective_on')[:1]),
        latest_receipt_correction_id=Subquery(latest.values('reversal__pk')[:1]),
    )
