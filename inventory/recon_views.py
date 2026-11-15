# SPDX-License-Identifier: MPL-2.0
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe
from core.access import context, member_view, require_editor
from core.models import Dealership
from .models import Vehicle, VehicleVendor, ReconTask, VehicleCostEntry
from .recon_forms import TaskForm, TaskEditForm, CostForm, TaskStatusForm, CostReversalForm, VendorProfileForm
from .reconditioning import with_cost_totals, add_task, edit_task, change_task, add_cost, reverse_cost, save_vendor


def _vehicle(request, pk):
    if not getattr(settings, 'RECON_DEMO_ENABLED', False):
        raise Http404
    return get_object_or_404(Vehicle.objects.filter(dealership=request.member.dealership), pk=pk)


def _response(request, template, values, status=200):
    response = render(request, template, context(request, **values), status=status)
    response['Cache-Control'] = 'private, no-store'
    return response


MAX_COST_EXPORT_ROWS = 5000


def _export_vehicle_costs(request, vehicle):
    entries = list(
        vehicle.cost_entries.select_related('actor', 'vendor', 'reverses', 'correction', 'task')
        .order_by('-entered_at', '-pk')[:MAX_COST_EXPORT_ROWS + 1]
    )
    if len(entries) > MAX_COST_EXPORT_ROWS:
        response = HttpResponse(
            f'This export is limited to {MAX_COST_EXPORT_ROWS} cost entries per download.',
            status=409,
            content_type='text/plain; charset=utf-8',
        )
        response['Cache-Control'] = 'private, no-store'
        return response
    if request.method == 'HEAD':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
    else:
        import csv
        import io
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow([
            'entry_id', 'kind', 'category', 'description', 'amount_cents',
            'signed_amount_usd', 'debit', 'credit', 'vendor_snapshot_name',
            'task_id', 'task_title', 'reverses_entry_id', 'reversed_by_entry_id',
            'correction_reason', 'effective_on', 'entered_at', 'recorded_by',
            'vehicle_stock_number', 'vehicle_year', 'vehicle_make', 'vehicle_model',
            'vehicle_vin', 'purchase_amount_usd', 'unitemized_recon_usd',
            'net_itemized_cost_usd', 'total_recorded_investment_usd', 'report_note',
        ])
        note = 'DEMO ONLY: internal synthetic vehicle cost register (not accounts payable, vendor payment, tax deduction, accounting profit, or complete dealership backup).'
        for e in entries:
            signed_usd = f'-{format(e.amount, ".2f")}' if e.kind == 'reversal' else format(e.amount, '.2f')
            correction = getattr(e, 'correction', None)
            writer.writerow([
                _csv_cell(e.pk),
                _csv_cell(e.kind),
                _csv_cell(e.category),
                _csv_cell(e.description),
                _csv_cell(-e.amount_cents if e.kind == 'reversal' else e.amount_cents),
                _csv_cell(signed_usd),
                _csv_cell(e.debit),
                _csv_cell(e.credit),
                _csv_cell(e.vendor_name),
                _csv_cell(e.task_id) if e.task_id else '',
                _csv_cell(e.task.title) if e.task else '',
                _csv_cell(e.reverses_id) if e.reverses_id else '',
                _csv_cell(correction.pk) if correction else '',
                _csv_cell(e.reason),
                _csv_cell(e.effective_on.isoformat()),
                _csv_cell(e.entered_at.isoformat()),
                _csv_cell(e.actor.get_username()),
                _csv_cell(vehicle.stock_number),
                _csv_cell(vehicle.year),
                _csv_cell(vehicle.make),
                _csv_cell(vehicle.model),
                _csv_cell(vehicle.vin),
                format(vehicle.acquisition_cost, '.2f'),
                format(vehicle.recon_cost, '.2f'),
                _csv_cell(format(vehicle.itemized_cost, '.2f')),
                _csv_cell(format(vehicle.total_cost, '.2f')),
                note,
            ])
        data = output.getvalue().encode('utf-8-sig')
        response = HttpResponse(data, content_type='text/csv; charset=utf-8')
        response['Content-Length'] = str(len(data))
    response['Cache-Control'] = 'private, no-store'
    response['Content-Disposition'] = f'attachment; filename="DEMO-vehicle-{vehicle.pk}-costs.csv"'
    response['Content-Security-Policy'] = 'sandbox'
    return response


@never_cache
@member_view
@require_safe
def workspace(request, pk):
    vehicle = _vehicle(request, pk)
    # One dealer lock captures a coherent cost journal, baseline and task list.
    with transaction.atomic():
        Dealership.objects.select_for_update().get(pk=request.member.dealership_id)
        vehicle = with_cost_totals(Vehicle.objects.filter(pk=vehicle.pk)).get()
        if request.GET.get('export') == 'costs':
            return _export_vehicle_costs(request, vehicle)
        tasks = list(vehicle.recon_tasks.select_related('vendor', 'assigned_to').order_by('status', 'pk'))
        rows = [{'task': task, 'form': TaskStatusForm(initial={'revision': task.revision, 'status': task.status}, auto_id=f'task-{task.pk}-%s')} for task in tasks]
        entries = vehicle.cost_entries.select_related('actor', 'vendor', 'reverses', 'correction', 'task')
        page = Paginator(entries, 25).get_page(request.GET.get('page'))
        list(page.object_list)
        values = dict(vehicle=vehicle, task_rows=rows, costs=page, page_obj=page, today=timezone.localdate(),
                      open_tasks=sum(t.status != 'done' for t in tasks), completed_tasks=sum(t.status == 'done' for t in tasks))
        return _response(request, 'inventory/recon.html', values)


@member_view
def create(request, pk, kind):
    vehicle = _vehicle(request, pk)
    require_editor(request)
    kwargs = {'dealership': request.member.dealership}
    if kind == 'cost':
        kwargs['vehicle'] = vehicle
    form = (CostForm if kind == 'cost' else TaskForm)(request.POST if request.method == 'POST' else None, **kwargs)
    if request.method == 'POST' and form.is_valid():
        try:
            (add_cost if kind == 'cost' else add_task)(vehicle_id=pk, dealership=request.member.dealership, actor=request.user, data=form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, 'Vehicle cost recorded.' if kind == 'cost' else 'Work added.')
            return redirect('vehicle_recon', pk=pk)
    return _response(request, 'inventory/recon_form.html', dict(vehicle=vehicle, form=form, kind=kind))


@member_view
@require_http_methods(['GET', 'POST'])
def task_edit(request, pk, task_pk):
    vehicle = _vehicle(request, pk)
    require_editor(request)
    task = get_object_or_404(ReconTask.objects.select_related('vendor', 'assigned_to'), vehicle=vehicle, pk=task_pk)
    initial = {
        'revision': task.revision,
        'title': task.title,
        'detail': task.detail,
        'status': task.status,
        'vendor': task.vendor_id,
        'assigned_to': task.assigned_to_id,
        'due_on': task.due_on,
    }
    form = TaskEditForm(request.POST if request.method == 'POST' else None, dealership=request.member.dealership, initial=initial)
    status = 200
    if request.method == 'POST' and form.is_valid():
        try:
            edit_task(vehicle_id=pk, dealership=request.member.dealership, actor=request.user, task_id=task.pk, data=form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
            status = 409
        else:
            messages.success(request, 'Work updated.')
            return redirect('vehicle_recon', pk=pk)
    return _response(request, 'inventory/recon_form.html', dict(vehicle=vehicle, form=form, kind='edit_task', task=task), status=status)


@member_view
@require_POST
def task_status(request, pk, task_pk):
    vehicle = _vehicle(request, pk)
    require_editor(request)
    task = get_object_or_404(ReconTask, vehicle=vehicle, pk=task_pk)
    form = TaskStatusForm(request.POST)
    if form.is_valid():
        try:
            change_task(vehicle_id=pk, dealership=request.member.dealership, actor=request.user, task_id=task.pk, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, 'Work status saved.')
            return redirect('vehicle_recon', pk=pk)
    return _response(request, 'inventory/recon_form.html', dict(vehicle=vehicle, form=form, kind='status', task=task), status=409)


@member_view
def correction(request, pk, entry_pk):
    vehicle = _vehicle(request, pk)
    require_editor(request)
    entry = get_object_or_404(VehicleCostEntry, vehicle=vehicle, pk=entry_pk, kind='cost')
    form = CostReversalForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            reverse_cost(vehicle_id=pk, dealership=request.member.dealership, actor=request.user, entry_id=entry.pk, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, 'Cost reversed. The original entry and correction are retained.')
            return redirect('vehicle_recon', pk=pk)
    return _response(request, 'inventory/recon_form.html', dict(vehicle=vehicle, form=form, kind='reversal', entry=entry))


MAX_QUEUE_EXPORT_ROWS = 5000


def _csv_cell(value):
    if value is None or value == '':
        return ''
    text = str(value)
    if text.lstrip(' \t\r\n\ufeff').startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')):
        return "'" + text
    return text


def _filtered_queue_tasks(request):
    if not getattr(settings, 'RECON_DEMO_ENABLED', False):
        raise Http404
    from datetime import timedelta
    from django.db.models import Q
    from core.filter_views import filter_context
    from .recon_filters import SCHEMA
    filters = filter_context(request, SCHEMA)
    state = filters['filter_state']
    today = timezone.localdate()
    tasks = ReconTask.objects.filter(vehicle__dealership=request.member.dealership)
    scope = state.extra.get('scope') or 'open'
    if scope == 'open':
        tasks = tasks.exclude(status=ReconTask.Status.DONE)
    elif scope == 'done':
        tasks = tasks.filter(status=ReconTask.Status.DONE)
    schedule = state.extra.get('schedule') or ''
    if schedule == 'overdue':
        tasks = tasks.exclude(status=ReconTask.Status.DONE).filter(due_on__lt=today)
    elif schedule == 'today':
        tasks = tasks.filter(due_on=today)
    elif schedule == 'upcoming':
        tasks = tasks.filter(due_on__gt=today)
    elif schedule == 'unscheduled':
        tasks = tasks.filter(due_on__isnull=True)
    age = state.extra.get('age') or ''
    age_filters = {
        '0_7': Q(created_at__date__range=(today - timedelta(days=7), today)),
        '8_14': Q(created_at__date__range=(today - timedelta(days=14), today - timedelta(days=8))),
        '15_30': Q(created_at__date__range=(today - timedelta(days=30), today - timedelta(days=15))),
        'over_30': Q(created_at__date__lt=today - timedelta(days=30)),
    }
    if age in age_filters:
        tasks = tasks.filter(age_filters[age])
    for word in state.query.split():
        match = Q(title__icontains=word) | Q(detail__icontains=word) | Q(vendor__name__icontains=word) | Q(vendor__contact_name__icontains=word) | Q(vendor__phone__icontains=word) | Q(vendor__email__icontains=word) | Q(assigned_to__username__icontains=word) | Q(vehicle__stock_number__icontains=word) | Q(vehicle__vin__icontains=word) | Q(vehicle__make__icontains=word) | Q(vehicle__model__icontains=word)
        if word.isascii() and word.isdecimal() and len(word) <= 4:
            match |= Q(vehicle__year=int(word))
        tasks = tasks.filter(match)
    tasks = state.apply(tasks).select_related('vehicle', 'vendor', 'assigned_to')
    return filters, state, tasks, today, scope, schedule, age


@member_view
def queue(request):
    from django.db.models import Count, Q
    from django.http import QueryDict
    filters, state, tasks, today, scope, schedule, age = _filtered_queue_tasks(request)
    open_work = Q(status__in=[ReconTask.Status.TODO, ReconTask.Status.IN_PROGRESS])
    summary = tasks.order_by().aggregate(
        open=Count('pk', filter=open_work),
        in_progress=Count('pk', filter=Q(status=ReconTask.Status.IN_PROGRESS)),
        done=Count('pk', filter=Q(status=ReconTask.Status.DONE)),
        overdue=Count('pk', filter=open_work & Q(due_on__lt=today)),
        unscheduled=Count('pk', filter=open_work & Q(due_on__isnull=True)),
    )
    page = Paginator(tasks, 25).get_page(request.GET.get('page'))
    for task in page:
        task.age_days = max((today - timezone.localdate(task.created_at)).days, 0) if task.created_at else None
    def _links(param, options, current):
        items = []
        for value, label in options:
            params = QueryDict(state.querystring, mutable=True)
            if value:
                params[param] = value
            else:
                params.pop(param, None)
            items.append({'label': label, 'query': params.urlencode(), 'active': value == current})
        return items
    tabs = _links('scope', [('open', 'Open work'), ('done', 'Completed'), ('all', 'All work')], scope)
    schedule_tabs = _links('schedule', [('', 'All target dates'), ('overdue', 'Overdue'), ('today', 'Due today'), ('upcoming', 'Upcoming'), ('unscheduled', 'No target date')], schedule)
    age_tabs = _links('age', [('', 'All task ages'), ('0_7', '0–7 days'), ('8_14', '8–14 days'), ('15_30', '15–30 days'), ('over_30', 'Over 30 days')], age)
    return _response(request, 'inventory/recon_queue.html', dict(**filters, work=page, page_obj=page, tabs=tabs, schedule_tabs=schedule_tabs, age_tabs=age_tabs, today=today, summary=summary))


@never_cache
@member_view
@require_safe
def queue_export(request):
    filters, state, tasks, today, scope, schedule, age = _filtered_queue_tasks(request)
    if state.errors:
        return HttpResponse(
            'Correct the filter rules before exporting.',
            status=400,
            content_type='text/plain; charset=utf-8',
        )
    rows = list(tasks[:MAX_QUEUE_EXPORT_ROWS + 1])
    if len(rows) > MAX_QUEUE_EXPORT_ROWS:
        return HttpResponse(
            f'This export is limited to {MAX_QUEUE_EXPORT_ROWS} tasks per download. Narrow your filters before exporting.',
            status=409,
            content_type='text/plain; charset=utf-8',
        )
    if request.method == 'HEAD':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
    else:
        import csv
        import io
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow([
            'task_id', 'title', 'detail', 'status', 'assigned_to', 'vendor_name',
            'target_date', 'target_status', 'created_on', 'updated_on', 'task_age_days',
            'vehicle_stock_number', 'vehicle_year', 'vehicle_make', 'vehicle_model',
            'vehicle_vin', 'vehicle_status', 'vehicle_acquired_on', 'report_note',
        ])
        note = 'DEMO ONLY: operational reconditioning work tracking (not a safety inspection, sale approval, or complete dealership export).'
        for t in rows:
            if t.due_on is None:
                due_str, due_status = '', 'unscheduled'
            elif t.status == ReconTask.Status.DONE:
                due_str, due_status = t.due_on.isoformat(), 'completed'
            elif t.due_on < today:
                due_str, due_status = t.due_on.isoformat(), 'overdue'
            elif t.due_on == today:
                due_str, due_status = t.due_on.isoformat(), 'due_today'
            else:
                due_str, due_status = t.due_on.isoformat(), 'upcoming'
            created_date = timezone.localdate(t.created_at) if t.created_at else None
            updated_date = timezone.localdate(t.updated_at) if t.updated_at else None
            age_days = str(max((today - created_date).days, 0)) if created_date else ''
            writer.writerow([
                _csv_cell(t.pk),
                _csv_cell(t.title),
                _csv_cell(t.detail),
                _csv_cell(t.status),
                _csv_cell(t.assigned_to.get_username()) if t.assigned_to else '',
                _csv_cell(t.vendor.name) if t.vendor else '',
                _csv_cell(due_str),
                _csv_cell(due_status),
                _csv_cell(created_date.isoformat()) if created_date else '',
                _csv_cell(updated_date.isoformat()) if updated_date else '',
                _csv_cell(age_days),
                _csv_cell(t.vehicle.stock_number),
                _csv_cell(t.vehicle.year),
                _csv_cell(t.vehicle.make),
                _csv_cell(t.vehicle.model),
                _csv_cell(t.vehicle.vin),
                _csv_cell(t.vehicle.status),
                _csv_cell(t.vehicle.acquired_on.isoformat()) if t.vehicle.acquired_on else '',
                note,
            ])
        data = output.getvalue().encode('utf-8-sig')
        response = HttpResponse(data, content_type='text/csv; charset=utf-8')
        response['Content-Length'] = str(len(data))
    response['Content-Disposition'] = f'attachment; filename="DEMO-reconditioning-work-{scope}.csv"'
    response['Content-Security-Policy'] = 'sandbox'
    return response


@member_view
@require_safe
def vendor_list(request):
    if not getattr(settings, 'RECON_DEMO_ENABLED', False):
        raise Http404
    from django.db.models import Q, Count
    query = request.GET.get('q', '').strip()[:200]
    vendors = VehicleVendor.objects.filter(dealership=request.member.dealership).annotate(
        task_count=Count('recontask', distinct=True),
        cost_count=Count('vehiclecostentry', distinct=True),
    )
    for word in query.split():
        vendors = vendors.filter(
            Q(name__icontains=word)
            | Q(contact_name__icontains=word)
            | Q(phone__icontains=word)
            | Q(email__icontains=word)
            | Q(address__icontains=word)
            | Q(notes__icontains=word)
        )
    page = Paginator(vendors.order_by('name', 'pk'), 25).get_page(request.GET.get('page'))
    return _response(request, 'inventory/vendor_list.html', dict(vendors=page, page_obj=page, query=query))


@member_view
@require_safe
def vendor_detail(request, vendor_pk):
    if not getattr(settings, 'RECON_DEMO_ENABLED', False):
        raise Http404
    vendor = get_object_or_404(VehicleVendor, pk=vendor_pk, dealership=request.member.dealership)
    tasks = ReconTask.objects.filter(vendor=vendor, vehicle__dealership=request.member.dealership).select_related('vehicle', 'assigned_to').order_by('-updated_at', '-pk')[:25]
    costs = VehicleCostEntry.objects.filter(vendor=vendor, vehicle__dealership=request.member.dealership).select_related('vehicle', 'actor', 'correction', 'reverses')[:25]
    events = vendor.events.select_related('actor')[:20]
    return _response(request, 'inventory/vendor_detail.html', dict(vendor=vendor, tasks=tasks, costs=costs, events=events))


@member_view
@require_http_methods(['GET', 'POST'])
def vendor_editor(request, vendor_pk=None):
    if not getattr(settings, 'RECON_DEMO_ENABLED', False):
        raise Http404
    require_editor(request)
    vendor = get_object_or_404(VehicleVendor, pk=vendor_pk, dealership=request.member.dealership) if vendor_pk else None
    initial = {}
    if vendor:
        initial = {
            'revision': vendor.revision,
            'name': vendor.name,
            'contact_name': vendor.contact_name,
            'phone': vendor.phone,
            'email': vendor.email,
            'address': vendor.address,
            'notes': vendor.notes,
        }
    form = VendorProfileForm(request.POST if request.method == 'POST' else None, editing=bool(vendor), initial=initial)
    status = 200
    if request.method == 'POST' and form.is_valid():
        try:
            saved = save_vendor(dealership=request.member.dealership, actor=request.user, data=form.cleaned_data, vendor_id=vendor.pk if vendor else None)
        except ValidationError as error:
            if hasattr(error, 'error_dict'):
                for field, errors in error.error_dict.items():
                    form.add_error(field if field in form.fields else None, errors)
            else:
                form.add_error(None, error)
                status = 409
        else:
            messages.success(request, 'Vendor saved.')
            return redirect('vendor_detail', vendor_pk=saved.pk)
    return _response(request, 'inventory/vendor_form.html', dict(form=form, vendor=vendor, editing=bool(vendor)), status=status)
