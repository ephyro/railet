# SPDX-License-Identifier: MPL-2.0
import hashlib,json
from datetime import date
from django.db import transaction
from .models import DemoBook,DemoSchedule
from .services import require_demo,require_member,key,LedgerError
from .schedules import calculate,VERSION


def result_digest(result):return hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def calculate_for_book(book,inputs):
    require_demo()
    if set(inputs)!={'method','first_due_on','count','frequency','first_day','second_day','finance_charge','contract_rate','regular_payment'}:
        raise LedgerError('Use only the supported illustration inputs.')
    try:first_due=date.fromisoformat(inputs['first_due_on'])
    except (ValueError,TypeError):raise LedgerError('Enter a valid first due date.')
    opening=book.postings.get(kind='opening')
    return calculate(principal_cents=opening.amount_cents,start_on=book.opening_on,first_due_on=first_due,**{name:value for name,value in inputs.items() if name!='first_due_on'})


@transaction.atomic
def save_illustration(*,dealership_id,book_id,actor,inputs,expected_digest,creation_key):
    require_demo();require_member(actor,dealership_id);creation_key=key(creation_key)
    book=DemoBook.objects.select_for_update(of=('self',)).get(pk=book_id,dealership_id=dealership_id,customer__dealership_id=dealership_id)
    prior=book.schedule_illustrations.filter(creation_key=creation_key).first()
    if prior:
        if prior.inputs!=inputs or prior.result_sha256!=expected_digest or prior.created_by_id!=actor.pk:
            raise LedgerError('This save key belongs to a different saved illustration.')
        return prior,False
    result=calculate_for_book(book,inputs)
    if result_digest(result)!=expected_digest:raise LedgerError('The calculation changed after preview. Review a fresh illustration before saving.')
    return DemoSchedule.objects.create(book=book,method=inputs['method'],inputs=inputs,result=result,result_sha256=expected_digest,calculation_version=VERSION,creation_key=creation_key,created_by=actor),True
