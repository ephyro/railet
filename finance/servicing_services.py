# SPDX-License-Identifier: MPL-2.0
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction,IntegrityError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import DemoBook,DemoSchedule,DemoServicingPlan,DemoPosting
from .services import require_demo,require_member,key,LedgerError
from .schedule_services import calculate_for_book,result_digest
from .servicing import POLICY,MAX_POSTINGS,project


def require_simulation():
    require_demo()
    if not getattr(settings,'DEMO_SERVICING_ENABLED',False):raise PermissionDenied


def verified_schedule(book,schedule,opening_cents=None):
    if schedule.book_id!=book.pk or schedule.method!='precomputed' or schedule.inputs.get('frequency')!='monthly':
        raise LedgerError('Choose a monthly precomputed illustration from this account.')
    if opening_cents is None:
        computed=calculate_for_book(book,schedule.inputs)
    else:
        from datetime import date
        from .schedules import calculate
        inputs=dict(schedule.inputs)
        try:
            first_due=date.fromisoformat(inputs.pop('first_due_on'))
            computed=calculate(principal_cents=opening_cents,start_on=book.opening_on,first_due_on=first_due,**inputs)
        except (TypeError,ValueError,KeyError):raise LedgerError('The saved schedule inputs could not be verified.')
    if result_digest(schedule.result)!=schedule.result_sha256 or result_digest(computed)!=schedule.result_sha256 or schedule.calculation_version!=computed['calculation_version']:
        raise LedgerError('The retained schedule could not be verified. No status was calculated.')
    return schedule.result


@transaction.atomic
def select_baseline(*,dealership_id,book_id,schedule_id,actor,reason,creation_key,expected_digest):
    require_simulation();require_member(actor,dealership_id);creation_key=key(creation_key)
    book=get_object_or_404(DemoBook.objects.select_for_update(),pk=book_id,dealership_id=dealership_id,customer__dealership_id=dealership_id)
    prior=DemoServicingPlan.objects.filter(book=book).first()
    if prior:
        if (prior.creation_key,prior.schedule_id,prior.created_by_id,prior.reason,prior.schedule_sha256)!=(creation_key,schedule_id,actor.pk,reason,expected_digest):
            raise LedgerError('This account already has a saved demo baseline; it cannot be replaced.')
        return prior,False
    if not isinstance(reason,str) or not reason.strip() or len(reason)>300:raise LedgerError('Enter a reason for selecting this demo baseline.')
    schedule=get_object_or_404(DemoSchedule,pk=schedule_id,book=book)
    verified_schedule(book,schedule)
    if expected_digest!=schedule.result_sha256:raise LedgerError('The preview does not match the saved schedule.')
    try:
        with transaction.atomic():
            saved=DemoServicingPlan.objects.create(book=book,schedule=schedule,schedule_sha256=expected_digest,policy_version=POLICY,reason=reason,creation_key=creation_key,created_by=actor)
    except IntegrityError:raise LedgerError('This selection key or account already has a saved demo baseline.')
    return saved,True


def projection_for_book(book,*,as_of=None,recorded_through=None,postings=None,plan=None):
    require_simulation();as_of=as_of or timezone.localdate();recorded_through=recorded_through or timezone.now()
    if as_of<book.opening_on or as_of>timezone.localdate():raise LedgerError('Use an as-of date from account opening through today.')
    plan=plan or DemoServicingPlan.objects.select_related('schedule').filter(book=book).first()
    if not plan:return None
    if plan.book_id!=book.pk or plan.policy_version!=POLICY or plan.schedule_sha256!=plan.schedule.result_sha256:
        raise LedgerError('The demo baseline could not be verified.')
    if plan.created_at>recorded_through:raise LedgerError('The baseline was not saved by this capture timestamp.')
    if postings is None:
        postings=list(book.postings.filter(entered_at__lte=recorded_through).order_by('entered_at','pk').values('id','kind','amount_cents','effective_on','entered_at','reverses_id')[:MAX_POSTINGS+1])
    openings=[p['amount_cents'] for p in postings if p['kind']=='opening' and p['entered_at']<=recorded_through]
    if len(openings)!=1:raise LedgerError('A single verified opening is required for the simulation.')
    result=verified_schedule(book,plan.schedule,opening_cents=openings[0])
    return project(rows=result['rows'],postings=postings,as_of=as_of,recorded_through=recorded_through)


def display_projection(result,*,include_rows=True):
    from .views import money
    labels={'past_due':'Demo past due','due_today':'Demo due today','current':'Demo up to date','covered':'Demo schedule covered'}
    facts=result if include_rows else {k:v for k,v in result.items() if k not in ('rows','coverage')}
    return {**facts,'label':labels[result['status']],'due_display':money(result['amount_due_cents']),
            'past_due_display':money(result['past_due_cents']),'remaining_display':money(result['remaining_scheduled_cents']),
            'excess_display':money(result['excess_cents']),
            'display_rows':[{**r,'scheduled':money(r['scheduled_cents']),'covered':money(r['covered_cents']),'remaining':money(r['remaining_cents'])} for r in result['rows']] if include_rows else []}


MAX_LIST_POSTINGS=50000


def attach_list_status(books,*,strict=False):
    """Call while book locks are held; bulk reads avoid per-account queries."""
    from collections import defaultdict
    require_simulation();captured=timezone.now()
    plans={p.book_id:p for p in DemoServicingPlan.objects.select_related('schedule').filter(book_id__in=[b.pk for b in books])}
    for book in books:book.simulation=None;book.simulation_error=None
    if not plans:return
    postings=list(DemoPosting.objects.filter(book_id__in=plans,entered_at__lte=captured).order_by('entered_at','pk').values('book_id','id','kind','amount_cents','effective_on','entered_at','reverses_id')[:MAX_LIST_POSTINGS+1])
    if len(postings)>MAX_LIST_POSTINGS:
        if strict:raise LedgerError('Too much journal activity for this status search. Narrow the customer or vehicle search; no partial results are shown.')
        for book in books:
            if book.pk in plans:book.simulation_error='Record limit exceeded; review this account separately.'
        return
    grouped=defaultdict(list)
    for posting in postings:grouped[posting['book_id']].append(posting)
    for book in books:
        if book.pk not in plans:continue
        try:book.simulation=display_projection(projection_for_book(book,plan=plans[book.pk],postings=grouped[book.pk],recorded_through=captured),include_rows=False)
        except LedgerError as error:book.simulation_error=' '.join(error.messages)


def payment_impact(book,*,amount=None,effective_on,reversal=None):
    """Locked-book, non-posting preview; virtual coverage never touches the ledger."""
    from .services import cents
    from .views import money
    if reversal is not None:
        if reversal.book_id!=book.pk or reversal.kind!='receipt':raise LedgerError('Choose an original receipt from this account.')
        if book.postings.filter(reverses_id=reversal.pk).exists():raise LedgerError('This receipt already has a reversal. Open its original receipt to review the linked correction.')
    captured=timezone.now();as_of=timezone.localdate(captured)
    enabled=getattr(settings,'DEMO_SERVICING_ENABLED',False)
    plan=DemoServicingPlan.objects.select_related('schedule').filter(book=book).first() if enabled else None
    if not plan:
        return result_digest({'as_of':as_of.isoformat(),'servicing_enabled':enabled,'baseline':None}),None
    postings=list(book.postings.filter(entered_at__lte=captured).order_by('entered_at','pk').values('id','kind','amount_cents','effective_on','entered_at','reverses_id')[:MAX_POSTINGS+1])
    if len(postings)>MAX_POSTINGS:raise LedgerError('The payment-impact preview exceeds the record limit. No payment was posted.')
    state=result_digest({'as_of':as_of.isoformat(),'servicing_enabled':enabled,
        'baseline':{'id':plan.pk,'schedule':plan.schedule_id,'digest':plan.schedule_sha256,'policy':plan.policy_version} if plan else None,
        'postings':[{**p,'effective_on':p['effective_on'].isoformat(),'entered_at':p['entered_at'].isoformat()} for p in postings]})
    before=projection_for_book(book,as_of=as_of,recorded_through=captured,postings=postings,plan=plan)
    proposed={'id':-1,'kind':'reversal' if reversal else 'receipt','amount_cents':reversal.amount_cents if reversal else cents(amount),'effective_on':effective_on,'entered_at':captured,'reverses_id':reversal.pk if reversal else None}
    after=projection_for_book(book,as_of=as_of,recorded_through=captured,postings=[*postings,proposed],plan=plan)
    if reversal is not None:
        lost=[{'number':a['number'],'due_on':a['due_on'],'amount':money(b['covered_cents']-a['covered_cents'])}
              for b,a in zip(before['rows'],after['rows']) if b['covered_cents']>a['covered_cents']]
        return state,{'before':display_projection(before),'after':display_projection(after),'reversal':True,
            'amount':money(reversal.amount_cents),'coverage':lost,'shown_coverage':lost[:5],'more_coverage':lost[5:],
            'excess_changed':before['excess_cents']!=after['excess_cents']}
    own=[r for r in after['coverage'] if r['receipt_id']==-1]
    dates={r['number']:r['due_on'] for r in after['rows']}
    allocated=sum(r['coverage_cents'] for r in own)
    existing_after=[r for r in after['coverage'] if r['receipt_id']!=-1]
    coverage=[{'number':r['installment'],'due_on':dates[r['installment']],'amount':money(r['coverage_cents'])} for r in own]
    return state,{'before':display_projection(before),'after':display_projection(after),
        'amount':money(proposed['amount_cents']),'coverage':coverage,'shown_coverage':coverage[:5],'more_coverage':coverage[5:],
        'excess':money(proposed['amount_cents']-allocated),'has_excess':proposed['amount_cents']>allocated,
        'redistributed':existing_after!=before['coverage']}
