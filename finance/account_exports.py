# SPDX-License-Identifier: MPL-2.0
"""Private portable account records, never legal statements or a full backup."""
import csv
import hashlib
import io
import json
import zipfile
from decimal import Decimal
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods
from core.access import member_view, context
from customers.records import address_snapshot
from .models import DemoAccountContext, DemoAccountExport
from .views import demo_page, scoped_book
from .services import reconcile
from .schedule_services import result_digest

VERSION = 'demo-account-export-v4'
MAX_POSTINGS = 10000
MAX_SCHEDULES = 200
MAX_BYTES = 16 * 1024 * 1024


class AccountExportError(Exception):
    pass


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode('utf-8')


def csv_cell(value):
    text = str(value)
    # JSON retains exact raw values; CSV is a spreadsheet-safe presentation.
    if text.lstrip(' \t\r\n\ufeff').startswith(('=', '+', '-', '@')) or text.startswith(('\t','\r','\n')):
        return "'"+text
    return text


def build_bundle(book, *, actor, captured_at):
    postings = list(book.postings.order_by('entered_at','pk')[:MAX_POSTINGS+1])
    schedules = list(book.schedule_illustrations.order_by('created_at','pk')[:MAX_SCHEDULES+1])
    if len(postings)>MAX_POSTINGS or len(schedules)>MAX_SCHEDULES:
        raise AccountExportError('This account exceeds the portable export limit. Ask your administrator for a complete export; no partial ZIP was prepared.')
    linked = DemoAccountContext.objects.filter(book=book).first()
    if linked and result_digest(linked.snapshot)!=linked.snapshot_sha256:
        raise AccountExportError('Saved draft context failed its integrity check. Contact your administrator.')
    for schedule in schedules:
        if result_digest(schedule.result)!=schedule.result_sha256:
            raise AccountExportError('A saved schedule failed its integrity check. Contact your administrator.')
    totals=reconcile(dealership_id=book.dealership_id, book_id=book.pk)
    if not totals['balanced']:
        raise AccountExportError('The account journal did not reconcile. Contact your administrator before exporting.')
    journal=[{'id':p.pk,'kind':p.kind,'amount_cents':p.amount_cents,
              'payment_method':p.payment_method,'amount_usd':format(Decimal(p.amount_cents)/100,'.2f'),
              'debit':p.debit,'credit':p.credit,'reverses_id':p.reverses_id,
              'actor_id':p.actor_id,'effective_on':p.effective_on.isoformat(),
              'entered_at':p.entered_at.isoformat(),'reason':p.reason,
              'request_key':str(p.request_key),'posting_version':p.posting_version} for p in postings]
    facts={'format':VERSION,'demonstration_only':True,'captured_at':captured_at.isoformat(),
        'exported_by_user_id':actor.pk,'account':{
            'id':book.pk,'dealership_id':book.dealership_id,'customer_id':book.customer_id,
            'label':book.label,'currency':book.currency,'opening_on':book.opening_on.isoformat(),
            'source_reference':book.source_reference,'created_at':book.created_at.isoformat(),
            'created_by_id':book.created_by_id,'creation_key':str(book.creation_key)},
        'current_customer':{'id':book.customer_id,'first_name':book.customer.first_name,
            'last_name':book.customer.last_name,'phone':book.customer.phone,'email':book.customer.email,
            'address':address_snapshot(book.customer)},
        'reconciliation':totals,
        'linked_context':{'id':linked.pk,'deal_id':linked.deal_id,'snapshot':linked.snapshot,
            'snapshot_sha256':linked.snapshot_sha256,'created_at':linked.created_at.isoformat(),
            'created_by_id':linked.created_by_id} if linked else None}
    from .models import DemoServicingPlan
    plan=DemoServicingPlan.objects.filter(book=book).first()
    facts['servicing_simulation']={'id':plan.pk,'schedule_id':plan.schedule_id,'schedule_sha256':plan.schedule_sha256,
        'policy_version':plan.policy_version,'reason':plan.reason,'created_by_id':plan.created_by_id,
        'created_at':plan.created_at.isoformat(),'creation_key':str(plan.creation_key)} if plan else None
    forecasts=[{'id':s.pk,'method':s.method,'calculation_version':s.calculation_version,
                'inputs':s.inputs,'result':s.result,'result_sha256':s.result_sha256,
                'created_at':s.created_at.isoformat(),'created_by_id':s.created_by_id,
                'creation_key':str(s.creation_key)} for s in schedules]
    output=io.StringIO(newline='');writer=csv.writer(output)
    columns=['id','kind','amount_cents','amount_usd','debit','credit','reverses_id','actor_id','effective_on','entered_at','reason','request_key','posting_version','payment_method']
    writer.writerow(columns)
    for row in journal:writer.writerow([csv_cell(row[name]) if row[name] is not None else '' for name in columns])
    parts={'account.json':json_bytes(facts),'journal.json':json_bytes(journal),
           'journal.csv':output.getvalue().encode('utf-8-sig'),'schedules.json':json_bytes(forecasts),
           'README.txt':('RAILET SYNTHETIC ACCOUNT EXPORT\n\n'
            'Invented evaluation records only. Not a contract, legal statement, payoff quote or bank settlement.\n'
            'account.json includes current customer contact data, opening metadata, frozen linked context and reconciliation.\n'
            'journal.json retains exact raw posting values; journal.csv prefixes dangerous spreadsheet text with an apostrophe.\n'
            'amount_cents is an integer; amount_usd is a decimal string. Reversals link to their original entries.\n'
            'schedules.json preserves alternative illustrations and calculation versions; it does not select a contract.\n'
            'payment_method is manually recorded; unspecified means not recorded, not cash. Reversals retain the original method.\n'
            'Payments remain unapplied. No interest, payoff or payment allocation is recalculated by export.\n'
            'manifest.json gives each included file size and SHA-256 hash. Hashes are not signatures or proof of authorship.\n\n'
            'PRIVATE: this ZIP includes customer contact and financial details and is not encrypted. Store it securely.\n'
            'This is one account, not a complete dealership export or restorable database/media backup.\n'
            'Photos, uploaded files, demo document packets, full draft/customer histories and previous export events are excluded.\n'
            'No import, restore, legal readiness, or delivery confirmation is provided.\n').encode('utf-8')}
    if sum(map(len,parts.values()))>MAX_BYTES:
        raise AccountExportError('This account exceeds the portable export size limit. No partial ZIP was prepared.')
    parts['manifest.json']=json_bytes({'format':VERSION,'account_id':book.pk,'demonstration_only':True,
        'posting_count':len(postings),'schedule_count':len(schedules),
        'files':{name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in parts.items()}})
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in parts.items():
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.create_system=3;info.external_attr=0o100600 << 16
            archive.writestr(info,data)
    return buffer.getvalue(),len(postings),len(schedules)


@demo_page
@member_view
@require_GET
def review(request,pk):
    book=scoped_book(request,pk)
    return render(request,'finance/account_export.html',context(request,book=book,
        posting_count=book.postings.count(),schedule_count=book.schedule_illustrations.count(),
        exports=book.export_events.select_related('actor')[:5]))


@demo_page
@member_view
@require_http_methods(['GET','HEAD'])
@transaction.atomic
def download(request,pk):
    book=scoped_book(request,pk,locked=True)
    if request.method=='HEAD':
        response=HttpResponse(content_type='application/zip')
    else:
        try:bundle,postings,schedules=build_bundle(book,actor=request.user,captured_at=timezone.now())
        except AccountExportError as error:
            return HttpResponse(str(error),status=409,content_type='text/plain; charset=utf-8')
        DemoAccountExport.objects.create(book=book,actor=request.user,format_version=VERSION,
            bundle_sha256=hashlib.sha256(bundle).hexdigest(),bundle_bytes=len(bundle),
            posting_count=postings,schedule_count=schedules)
        response=HttpResponse(bundle,content_type='application/zip')
        response['Content-Length']=str(len(bundle))
    response['Content-Disposition']=f'attachment; filename="DEMO-account-{book.pk}.zip"'
    response['Content-Security-Policy']='sandbox'
    return response
