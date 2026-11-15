# SPDX-License-Identifier: MPL-2.0
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from core.access import member_view, context, require_editor
from .forms import CustomerForm
from .models import Customer
from .queries import search_customers
from .filters import SCHEMA
from core.filter_views import filter_context
from .services import save_customer

def records(request):
    return Customer.objects.filter(dealership=request.member.dealership)

@member_view
def customer_list(request):
    from django.http import QueryDict
    filters = filter_context(request, SCHEMA)
    state = filters["filter_state"]
    customers = search_customers(request.member.dealership, state.query)
    stage = state.extra.get("stage", "")
    if stage == "unspecified":
        customers = customers.filter(lead_stage="")
    elif stage:
        customers = customers.filter(lead_stage=stage)
    page = Paginator(state.apply(customers), 25).get_page(request.GET.get("page"))
    stage_tabs = []
    options = [("", "All customers"), *( (k, v) for k, v in Customer.LeadStage.choices if k ), ("unspecified", "Stage not set")]
    for value, label in options:
        params = QueryDict(state.querystring, mutable=True)
        if value:
            params["stage"] = value
        else:
            params.pop("stage", None)
        stage_tabs.append({"label": label, "query": params.urlencode(), "active": stage == value})
    from django.conf import settings
    export_enabled = settings.DEBUG and getattr(settings, "CUSTOMER_ACTIVITY_DEMO_ENABLED", False)
    package_flags = ("DEBUG", "CUSTOMER_ACTIVITY_DEMO_ENABLED", "RECON_DEMO_ENABLED", "DEMO_COMPLETION_ENABLED", "DEMO_PACKETS_ENABLED", "DEAL_FILES_DEMO_ENABLED", "DEMO_LEDGER_ENABLED", "DEMO_SERVICING_ENABLED")
    package_enabled = all(getattr(settings, flag, False) for flag in package_flags)
    return render(request, "customers/list.html", context(request, customer_export_enabled=export_enabled, package_export_enabled=package_enabled, **filters, customers=page, page_obj=page, query=state.query, stage=stage, stage_tabs=stage_tabs))

@member_view
def customer_detail(request, pk):
    from finance.account_services import customer_accounts
    customer = get_object_or_404(records(request), pk=pk)
    drafts = (customer.buyer_drafts.filter(dealership=request.member.dealership) | customer.co_buyer_drafts.filter(dealership=request.member.dealership)).select_related("vehicle", "demo_completion").distinct()
    return render(request, "customers/detail.html", context(request, customer=customer, drafts=drafts, accounts=customer_accounts(dealership_id=request.member.dealership_id, customer_id=customer.pk)[:20], activities=customer.activities.select_related("created_by", "completed_by", "assigned_to")[:25], events=customer.events.select_related("actor")[:20]))

def editor(request, pk=None):
    require_editor(request)
    with transaction.atomic():
        customer = get_object_or_404(records(request).select_for_update(), pk=pk) if pk else Customer(dealership=request.member.dealership)
        form = CustomerForm(request.POST if request.method == "POST" else None, instance=customer, dealership=request.member.dealership)
        status = 200
        if request.method == "POST" and form.is_valid():
            if pk and form.cleaned_data["revision"] != customer.revision:
                form.add_error(None, "This customer was updated by someone else. Your entries are preserved; compare with the latest record before reloading.")
                status = 409
            else:
                customer = save_customer(form, actor=request.user, dealership=request.member.dealership)
                messages.success(request, "Customer saved.")
                return redirect("customer_detail", pk=customer.pk)
    return render(request, "customers/form.html", context(request, form=form, customer=customer, editing=bool(pk)), status=status)

@member_view
def customer_create(request):
    return editor(request)

@member_view
def customer_edit(request, pk):
    return editor(request, pk)
