# SPDX-License-Identifier: MPL-2.0
"""Private synthetic invoices; not payment or accounting records."""
import hashlib
import uuid
from django import forms
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Sum
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from core.access import authorized_private_read, context, member_view, require_editor
from inventory.models import Vehicle, VehicleCostEntry
from .forms import SupportingFileUploadForm
from .models import VehicleInvoice, VehicleInvoiceEvent
from .services import MAX_FILE_BYTES, FileWorkflowError, _delete_new_blobs, _lock_dealership, _require_locked_editor, validate_pdf_bytes
from .views import private_no_store, _set_download_headers, _check_private_reference


class InvoiceForm(SupportingFileUploadForm):
    cost = forms.ModelChoiceField(queryset=VehicleCostEntry.objects.none(), required=False, label='Link to a recorded cost (optional)')

    def __init__(self, *args, vehicle, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cost'].queryset = VehicleCostEntry.objects.filter(vehicle=vehicle, kind='cost').order_by('-entered_at', '-pk')
        self.fields['cost'].label_from_instance = lambda cost: f'#{cost.pk} · {cost.description} · ${cost.amount:.2f}'


def upload_invoice(*, vehicle_id, dealership_id, actor, title, upload_key, pdf_bytes, cost_id):
    if not getattr(settings, 'RECON_DEMO_ENABLED', False) or not getattr(settings, 'DEAL_FILES_DEMO_ENABLED', False):
        raise PermissionDenied
    size = validate_pdf_bytes(pdf_bytes)
    if not title or len(title) > 120 or not isinstance(upload_key, uuid.UUID):
        raise FileWorkflowError('Enter a title and refresh the page if the upload expired.')
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    storage = VehicleInvoice._meta.get_field('blob').storage
    written = []
    try:
        with transaction.atomic(durable=True):
            _lock_dealership(dealership_id)
            vehicle = Vehicle.objects.select_for_update().get(pk=vehicle_id, dealership_id=dealership_id)
            _require_locked_editor(actor, dealership_id)
            if cost_id is not None and not VehicleCostEntry.objects.filter(pk=cost_id, vehicle=vehicle, kind='cost').exists():
                raise FileWorkflowError('Choose a cost recorded for this vehicle.')
            existing = VehicleInvoice.objects.filter(vehicle=vehicle, upload_key=upload_key).first()
            if existing:
                if (existing.sha256, existing.title, existing.cost_id, existing.byte_size) == (digest, title, cost_id, size):
                    return existing
                raise FileWorkflowError('This upload was already used for a different invoice. Start a new upload.')
            invoices = VehicleInvoice.objects.filter(vehicle=vehicle)
            if invoices.count() >= 100 or (invoices.aggregate(total=Sum('byte_size'))['total'] or 0) + size > 100 * 1024 * 1024:
                raise FileWorkflowError('This vehicle has reached its retained invoice storage limit.')
            name = storage.save(f'vehicle-invoices/{uuid.uuid4()}.pdf', ContentFile(pdf_bytes))
            written.append(name)
            invoice = VehicleInvoice.objects.create(vehicle=vehicle, cost_id=cost_id, title=title, blob=name, sha256=digest, byte_size=size, upload_key=upload_key, created_by=actor)
            VehicleInvoiceEvent.objects.create(invoice=invoice, actor=actor, action='upload')
        return invoice
    except BaseException:
        _delete_new_blobs(storage, written)
        raise


def gate():
    if not getattr(settings, 'RECON_DEMO_ENABLED', False):
        raise Http404


@private_no_store
@member_view
def invoices(request, pk):
    gate()
    if request.method not in ('GET', 'POST'):
        return HttpResponseNotAllowed(['GET', 'POST'])
    vehicle = get_object_or_404(Vehicle, pk=pk, dealership_id=request.member.dealership_id)
    if request.method == 'POST':
        require_editor(request)
    form = InvoiceForm(request.POST or None, request.FILES or None, vehicle=vehicle)
    if request.method == 'POST' and form.is_valid():
        try:
            cost = form.cleaned_data['cost']
            upload_invoice(vehicle_id=vehicle.pk, dealership_id=request.member.dealership_id, actor=request.user, title=form.cleaned_data['title'], upload_key=form.cleaned_data['upload_key'], pdf_bytes=form.cleaned_data['pdf_file'], cost_id=cost.pk if cost else None)
        except FileWorkflowError as error:
            form.add_error(None, str(error))
        else:
            return redirect('vehicle_invoices', pk=pk)
    records = vehicle.invoices.select_related('cost', 'created_by')
    return render(request, 'documents/vehicle_invoices.html', context(request, vehicle=vehicle, form=form, invoices=records))


@private_no_store
@member_view
@authorized_private_read
def download(request, pk, invoice_pk):
    gate()
    if request.method not in ('GET', 'HEAD'):
        return HttpResponseNotAllowed(['GET', 'HEAD'])
    invoice = get_object_or_404(VehicleInvoice.objects.select_related('vehicle'), pk=invoice_pk, vehicle_id=pk, vehicle__dealership_id=request.member.dealership_id)
    _check_private_reference(invoice, request.member.dealership_id)
    try:
        with invoice.blob.open('rb') as source:
            data = source.read(MAX_FILE_BYTES + 1)
    except OSError:
        raise Http404
    if len(data) > MAX_FILE_BYTES or len(data) != invoice.byte_size or hashlib.sha256(data).hexdigest() != invoice.sha256:
        return HttpResponse('Invoice integrity check failed. Contact your administrator.', status=409, content_type='text/plain')
    if request.method == 'GET':
        VehicleInvoiceEvent.objects.create(invoice=invoice, actor=request.user, action='download')
    response = HttpResponse(data if request.method == 'GET' else b'')
    return _set_download_headers(response, f'vehicle-invoice-{invoice.pk}.pdf', invoice.byte_size)
