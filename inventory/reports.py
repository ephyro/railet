# SPDX-License-Identifier: MPL-2.0
"""Synthetic inventory report; recorded costs are not accounting valuations."""
import csv
import io
from urllib.parse import urlencode
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q, F, Sum, Count, BigIntegerField, DurationField, ExpressionWrapper
from django.db.models.functions import Cast, Round
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from core.access import authorized_private_export, member_view, context
from .models import Vehicle
from .reconditioning import with_cost_totals

MAX_EXPORT_ROWS = 5000


def _csv_cell(value):
    if value is None or value == '':
        return ''
    text = str(value)
    if text.lstrip(' \t\r\n\ufeff').startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')):
        return "'" + text
    return text


def _compute_dates(vehicle, today):
    vehicle.age_days = (today - vehicle.acquired_on).days if vehicle.acquired_on and vehicle.acquired_on <= today else None
    vehicle.time_to_sale_days = None
    vehicle.sale_date_status = 'not_applicable' if vehicle.status != Vehicle.Status.SOLD else 'not_entered'
    if vehicle.status == Vehicle.Status.SOLD or vehicle.sold_on:
        if vehicle.sold_on is None:
            vehicle.sale_date_status = 'not_entered'
        elif vehicle.sold_on > today:
            vehicle.sale_date_status = 'future_sale_date_review'
        elif vehicle.acquired_on is None:
            vehicle.sale_date_status = 'missing_acquisition_date'
        elif vehicle.acquired_on > today:
            vehicle.sale_date_status = 'future_acquisition_date_review'
        elif vehicle.sold_on < vehicle.acquired_on:
            vehicle.sale_date_status = 'non_chronological_review'
        else:
            vehicle.time_to_sale_days = (vehicle.sold_on - vehicle.acquired_on).days
            vehicle.sale_date_status = 'chronological'


def _tts_queryset(queryset, tts, today):
    if tts == 'all':
        return queryset
    queryset = queryset.annotate(
        tts_span=ExpressionWrapper(F('sold_on') - F('acquired_on'), output_field=DurationField())
    )
    chronological = Q(
        acquired_on__isnull=False,
        sold_on__isnull=False,
        acquired_on__lte=today,
        sold_on__lte=today,
        sold_on__gte=F('acquired_on'),
    )
    if tts == 'unknown':
        return queryset.filter(~chronological)
    buckets = {
        '0_30': Q(tts_span__gte=timedelta(days=0), tts_span__lte=timedelta(days=30)),
        '31_60': Q(tts_span__gte=timedelta(days=31), tts_span__lte=timedelta(days=60)),
        '61_90': Q(tts_span__gte=timedelta(days=61), tts_span__lte=timedelta(days=90)),
        'over_90': Q(tts_span__gt=timedelta(days=90)),
    }
    return queryset.filter(chronological & buckets[tts])


def _filtered_vehicles(request):
    if not getattr(settings, 'RECON_DEMO_ENABLED', False):
        raise Http404
    status = request.GET.get('status', 'active')
    if status not in ('active', 'acquired', 'available', 'recon', 'sold', 'all'):
        status = 'active'
    vehicles = Vehicle.objects.filter(dealership=request.member.dealership)
    if status == 'active':
        vehicles = vehicles.exclude(status=Vehicle.Status.SOLD)
    elif status != 'all':
        vehicles = vehicles.filter(status=status)
    today = timezone.localdate()
    age = request.GET.get('age', 'all')
    if age not in ('all', '0_30', '31_60', '61_90', 'over_90', 'unknown'):
        age = 'all'
    age_filters = {
        '0_30': Q(acquired_on__range=(today - timedelta(days=30), today)),
        '31_60': Q(acquired_on__range=(today - timedelta(days=60), today - timedelta(days=31))),
        '61_90': Q(acquired_on__range=(today - timedelta(days=90), today - timedelta(days=61))),
        'over_90': Q(acquired_on__lt=today - timedelta(days=90)),
        'unknown': Q(acquired_on__isnull=True) | Q(acquired_on__gt=today),
    }
    if age != 'all':
        vehicles = vehicles.filter(age_filters[age])
    tts = request.GET.get('tts', 'all')
    if tts not in ('all', '0_30', '31_60', '61_90', 'over_90', 'unknown'):
        tts = 'all'
    vehicles = _tts_queryset(vehicles, tts, today)
    query = request.GET.get('q', '').strip()[:200]
    for word in query.split():
        match = Q(stock_number__icontains=word) | Q(vin__icontains=word) | Q(make__icontains=word) | Q(model__icontains=word)
        if word.isascii() and word.isdecimal() and len(word) <= 4:
            match |= Q(year=int(word))
        vehicles = vehicles.filter(match)
    sorts = {'stock': ('stock_number', 'pk'), 'cost_high': ('-report_cost_cents', 'pk'), 'cost_low': ('report_cost_cents', 'pk'), 'price_high': (F('asking_price').desc(nulls_last=True), 'pk'), 'oldest': (F('acquired_on').asc(nulls_last=True), 'pk'), 'sold_recent': (F('sold_on').desc(nulls_last=True), 'pk')}
    sort = request.GET.get('sort', 'stock')
    if sort not in sorts:
        sort = 'stock'
    vehicles = with_cost_totals(vehicles).annotate(report_cost_cents=Cast(Round(F('acquisition_cost') * 100), BigIntegerField()) + Cast(Round(F('recon_cost') * 100), BigIntegerField()) + F('registered_cost_cents')).order_by(*sorts[sort])
    return vehicles, today, status, age, tts, query, sort


@never_cache
@member_view
@require_safe
def investment_report(request):
    vehicles, today, status, age, tts, query, sort = _filtered_vehicles(request)
    summary = vehicles.aggregate(count=Count('pk'), cost_cents=Sum('report_cost_cents'), priced_count=Count('asking_price'), asking=Sum('asking_price'))
    summary['cost'] = Decimal(summary['cost_cents'] or 0) / 100
    page = Paginator(vehicles, 25).get_page(request.GET.get('page'))
    for vehicle in page:
        _compute_dates(vehicle, today)
    params = {'status': status, 'q': query, 'sort': sort, 'age': age, **({'tts': tts} if tts != 'all' else {})}
    filter_query = urlencode(params)
    tabs = [{'label': label, 'url': '?' + urlencode({**params, 'status': key}), 'active': status == key}
            for key, label in [('active', 'Active'), ('acquired', 'Acquired'), ('available', 'Available'), ('recon', 'In reconditioning'), ('sold', 'Sold'), ('all', 'All')]]
    return render(request, 'inventory/investment_report.html', context(request, vehicles=page, page_obj=page,
                  tabs=tabs, status=status, query=query, sort=sort, age=age, tts=tts, summary=summary, pagination_query=filter_query))


@never_cache
@member_view
@require_safe
@authorized_private_export
def investment_report_export(request):
    vehicles, today, status, age, tts, query, sort = _filtered_vehicles(request)
    rows = list(vehicles[:MAX_EXPORT_ROWS + 1])
    if len(rows) > MAX_EXPORT_ROWS:
        return HttpResponse(
            f'This export is limited to {MAX_EXPORT_ROWS} vehicles per download. Narrow your filters before exporting.',
            status=409,
            content_type='text/plain; charset=utf-8',
        )
    if request.method == 'HEAD':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
    else:
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow([
            'stock_number', 'year', 'make', 'model', 'vin', 'status', 'title_brand',
            'acquired_on', 'days_since_acquisition', 'acquisition_date_status',
            'sold_on', 'time_to_sale_days', 'sale_date_status',
            'acquisition_cost_usd', 'unitemized_recon_cost_usd', 'net_itemized_cost_usd',
            'recorded_investment_usd', 'asking_price_usd', 'asking_less_recorded_cost_usd',
            'report_note',
        ])
        note = 'DEMO ONLY: staff-entered dates and internal recorded costs (not verified ownership/sale proof, accounting valuation, or net profit); not a complete dealership export.'
        for v in rows:
            _compute_dates(v, today)
            if v.acquired_on is None:
                acq_date, age_days, acq_status = '', '', 'not_entered'
            elif v.acquired_on > today:
                acq_date, age_days, acq_status = v.acquired_on.isoformat(), '', 'future_date_review'
            else:
                acq_date, age_days, acq_status = v.acquired_on.isoformat(), str(v.age_days), 'recorded'
            sold_date = v.sold_on.isoformat() if v.sold_on else ''
            tts_days = str(v.time_to_sale_days) if v.time_to_sale_days is not None else ''
            writer.writerow([
                _csv_cell(v.stock_number),
                _csv_cell(v.year),
                _csv_cell(v.make),
                _csv_cell(v.model),
                _csv_cell(v.vin),
                _csv_cell(v.status),
                _csv_cell(v.title_brand),
                _csv_cell(acq_date),
                _csv_cell(age_days),
                _csv_cell(acq_status),
                _csv_cell(sold_date),
                _csv_cell(tts_days),
                _csv_cell(v.sale_date_status),
                format(v.acquisition_cost, '.2f'),
                format(v.recon_cost, '.2f'),
                format(v.itemized_cost, '.2f'),
                format(v.total_cost, '.2f'),
                format(v.asking_price, '.2f') if v.asking_price is not None else '',
                _csv_cell(format(v.asking_less_cost, '.2f')) if v.asking_less_cost is not None else '',
                note,
            ])
        data = output.getvalue().encode('utf-8-sig')
        response = HttpResponse(data, content_type='text/csv; charset=utf-8')
        response['Content-Length'] = str(len(data))
    response['Content-Disposition'] = f'attachment; filename="DEMO-inventory-investment-{status}.csv"'
    response['Content-Security-Policy'] = 'sandbox'
    return response
