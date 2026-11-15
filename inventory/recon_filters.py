# SPDX-License-Identifier: MPL-2.0
from django.db.models import F
from core.filtering import FilterField as Field, FilterSchema
from .models import ReconTask, Vehicle

SCHEMA = FilterSchema(
    resource='reconditioning', title='Reconditioning work', route='recon_queue',
    search_hint='Work, details, vendor, assignee, stock number, VIN, make or model',
    enabled_setting='RECON_DEMO_ENABLED', default_sort='oldest',
    fields=(
        Field('status', 'Work status', 'status', 'choice', tuple(ReconTask.Status.choices)),
        Field('vendor', 'Vendor', 'vendor__name'),
        Field('assignee', 'Assigned to', 'assigned_to__username'),
        Field('due', 'Target date', 'due_on', 'date'),
        Field('vehicle_acquired', 'Vehicle acquired on', 'vehicle__acquired_on', 'date'),
        Field('vehicle_status', 'Inventory status', 'vehicle__status', 'choice', tuple(Vehicle.Status.choices)),
        Field('stock', 'Stock number', 'vehicle__stock_number'),
        Field('created', 'Added on', 'created_at__date', 'date'),
        Field('updated', 'Updated on', 'updated_at__date', 'date'),
    ),
    sorts={
        'oldest': ('Oldest work first', ('created_at', 'pk')),
        'due': ('Earliest target date', (F('due_on').asc(nulls_last=True), 'created_at', 'pk')),
        'vehicle_oldest': ('Oldest vehicle acquisition', (F('vehicle__acquired_on').asc(nulls_last=True), 'created_at', 'pk')),
        'recent': ('Recently updated', ('-updated_at', '-pk')),
        'vehicle': ('Vehicle', ('vehicle__make', 'vehicle__model', 'vehicle__stock_number', 'pk')),
    },
    extras={
        'scope': ('open', 'all', 'done'),
        'schedule': ('overdue', 'today', 'upcoming', 'unscheduled'),
        'age': ('0_7', '8_14', '15_30', 'over_30'),
    },
)
