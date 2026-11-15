# SPDX-License-Identifier: MPL-2.0
import uuid
from django import forms
from django.contrib.auth import get_user_model
from django.conf import settings
from django.http import Http404
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST
from core.access import member_view, context, require_editor
from core.models import Membership
from .models import Customer, CustomerActivity, CustomerEvent, phone_key


class ActivityForm(forms.Form):
    kind = forms.ChoiceField(choices=CustomerActivity.Kind.choices, label='Type')
    detail = forms.CharField(max_length=2000, label='Details', widget=forms.Textarea(attrs={'rows': 4}), help_text='Use invented information in this test workspace.')
    due_at = forms.DateTimeField(required=False, label='Date and time (optional)', widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'), input_formats=['%Y-%m-%dT%H:%M'])
    creation_key = forms.UUIDField(initial=uuid.uuid4, widget=forms.HiddenInput)
    assigned_to = forms.ModelChoiceField(queryset=get_user_model().objects.none(), required=False, label='Assigned to', empty_label='Unassigned')

    def __init__(self, *args, dealership, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = get_user_model().objects.filter(is_active=True, membership__dealership=dealership, membership__role__in=['owner','staff']).order_by('username')

    def clean(self):
        data = super().clean()
        if data.get('kind') == 'note' and data.get('assigned_to'):
            self.add_error('assigned_to', 'Assign follow-ups or appointments, not conversation notes.')
        if data.get('kind') == 'note' and data.get('due_at'):
            self.add_error('due_at', 'Dates belong to follow-ups or appointments.')
        return data


@never_cache
@member_view
@require_http_methods(['GET', 'POST'])
def create(request, pk):
    if not getattr(settings, 'CUSTOMER_ACTIVITY_DEMO_ENABLED', False): raise Http404
    require_editor(request)
    customer = get_object_or_404(Customer, pk=pk, dealership=request.member.dealership)
    form = ActivityForm(request.POST if request.method == 'POST' else None, dealership=request.member.dealership)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            customer = get_object_or_404(Customer.objects.select_for_update(), pk=pk, dealership=request.member.dealership)
            if not Membership.objects.filter(user=request.user, dealership=customer.dealership, role__in=['owner','staff']).exists():
                raise PermissionDenied
            data = form.cleaned_data
            if data['assigned_to'] and not Membership.objects.filter(user=data['assigned_to'], user__is_active=True, dealership=customer.dealership, role__in=['owner','staff']).exists():
                form.add_error('assigned_to', 'Choose a current staff member from this dealership.')
                return render(request, 'customers/activity_form.html', context(request, customer=customer, form=form), status=409)
            prior = CustomerActivity.objects.filter(customer=customer, creation_key=data['creation_key']).first()
            if prior:
                if prior.created_by_id != request.user.pk or (prior.kind, prior.detail, prior.due_at, prior.assigned_to_id) != (data['kind'], data['detail'], data['due_at'], data['assigned_to'].pk if data['assigned_to'] else None):
                    form.add_error(None, 'This form was already used for another activity. Open a new form.')
                else:
                    return redirect('customer_detail', pk=pk)
            else:
                activity = CustomerActivity(customer=customer, created_by=request.user, **data)
                activity.full_clean()
                activity.save()
                CustomerEvent.objects.create(customer=customer, actor=request.user, changes={'action':'activity_created', 'activity_id':activity.pk, 'kind':activity.kind, 'detail':activity.detail, 'due_at':activity.due_at.isoformat() if activity.due_at else None, 'assigned_to_id':activity.assigned_to_id, 'revision':activity.revision})
                messages.success(request, 'Activity saved.')
                return redirect('customer_detail', pk=pk)
    return render(request, 'customers/activity_form.html', context(request, customer=customer, form=form))


@never_cache
@member_view
@require_POST
def complete(request, pk, activity_pk):
    if not getattr(settings, 'CUSTOMER_ACTIVITY_DEMO_ENABLED', False): raise Http404
    require_editor(request)
    with transaction.atomic():
        customer=get_object_or_404(Customer.objects.select_for_update(), pk=pk, dealership=request.member.dealership)
        if not Membership.objects.filter(user=request.user, dealership=customer.dealership, role__in=['owner','staff']).exists():
            raise PermissionDenied
        activity=get_object_or_404(CustomerActivity, pk=activity_pk, customer=customer, kind__in=['follow_up','appointment'])
        action=request.POST.get('action', 'complete')
        if action not in ('complete','reopen'):
            raise Http404
        try:
            revision=int(request.POST.get('revision', ''))
        except ValueError:
            revision=0
        if revision != activity.revision:
            return render(request, 'customers/activity_conflict.html', context(request, customer=customer, activity=activity), status=409)
        changed = (action == 'complete' and not activity.completed_at) or (action == 'reopen' and bool(activity.completed_at))
        if changed:
            activity.completed_at=timezone.now() if action == 'complete' else None
            activity.completed_by=request.user if action == 'complete' else None
            activity.revision += 1
            activity.save(update_fields=['completed_at','completed_by','revision'])
            CustomerEvent.objects.create(customer=customer,actor=request.user,changes={'action':'activity_completed' if action == 'complete' else 'activity_reopened','activity_id':activity.pk,'revision':activity.revision})
            messages.success(request,'Activity marked done.' if action == 'complete' else 'Activity reopened.')
    if request.POST.get('return_to') == 'queue':
        from urllib.parse import urlencode
        from django.urls import reverse
        status = request.POST.get('status', 'open')
        if status not in ('open', 'done', 'all'):
            status = 'open'
        query = request.POST.get('q', '').strip()[:200]
        page = request.POST.get('page', '1')
        if not page.isascii() or not page.isdecimal() or len(page) > 6:
            page = '1'
        return redirect(reverse('customer_activity_queue') + '?' + urlencode({'status': status, 'q': query, 'page': page}))
    return redirect('customer_detail', pk=pk)


@never_cache
@member_view
@require_http_methods(['GET', 'HEAD'])
def queue(request):
    if not getattr(settings, 'CUSTOMER_ACTIVITY_DEMO_ENABLED', False):
        raise Http404
    from django.core.paginator import Paginator
    from django.db.models import F, Q
    from urllib.parse import urlencode
    from deals.models import DraftDeal
    state = request.GET.get('status', 'open')
    if state not in ('open', 'done', 'all'):
        state = 'open'
    stage = request.GET.get('stage', '')
    valid_stages = {'unspecified', *(k for k, _ in Customer.LeadStage.choices if k)}
    if stage not in valid_stages:
        stage = ''
    query = request.GET.get('q', '').strip()[:200]
    activities = CustomerActivity.objects.filter(customer__dealership=request.member.dealership, kind__in=['follow_up', 'appointment']).select_related('customer', 'created_by', 'assigned_to')
    if state == 'open':
        activities = activities.filter(completed_at__isnull=True)
    elif state == 'done':
        activities = activities.filter(completed_at__isnull=False)
    if stage == 'unspecified':
        activities = activities.filter(customer__lead_stage='')
    elif stage:
        activities = activities.filter(customer__lead_stage=stage)
    for word in query.split():
        match = (
            Q(customer__first_name__icontains=word)
            | Q(customer__last_name__icontains=word)
            | Q(customer__email__icontains=word)
            | Q(detail__icontains=word)
            | Q(assigned_to__username__icontains=word)
            | Q(created_by__username__icontains=word)
        )
        digits = phone_key(word)
        if digits and not any(c.isalpha() for c in word):
            match |= Q(customer__phone_normalized__contains=digits)
        activities = activities.filter(match)
    activities = activities.order_by(F('due_at').asc(nulls_last=True), '-created_at', '-pk')
    page = Paginator(activities, 25).get_page(request.GET.get('page'))
    customer_ids = {item.customer_id for item in page}
    deals_by_customer = {cid: [] for cid in customer_ids}
    if customer_ids:
        dealership_id = request.member.dealership_id
        for deal in DraftDeal.objects.filter(dealership_id=dealership_id).filter(Q(buyer_id__in=customer_ids) | Q(co_buyer_id__in=customer_ids)).select_related('vehicle', 'demo_completion').order_by('-updated_at', '-pk'):
            for cid in (deal.buyer_id, deal.co_buyer_id):
                if cid in deals_by_customer and deal not in deals_by_customer[cid]:
                    deals_by_customer[cid].append(deal)
    for item in page:
        item.customer_deals = deals_by_customer.get(item.customer_id, [])
    base_params = {'q': query, **({'stage': stage} if stage else {})}
    tabs = [{'label': label, 'url': '?' + urlencode({'status': value, **base_params}), 'active': state == value}
            for value, label in [('open', 'Open'), ('done', 'Done'), ('all', 'All')]]
    return render(request, 'customers/activity_queue.html', context(request, page_obj=page, activities=page, tabs=tabs, query=query, status=state, stage=stage, now=timezone.now(), pagination_query=urlencode({'status': state, **base_params})))


class EditActivityForm(forms.Form):
    detail = forms.CharField(max_length=2000, label='Details', widget=forms.Textarea(attrs={'rows': 4}))
    due_at = forms.DateTimeField(required=False, label='Date and time (optional)', widget=forms.DateTimeInput(attrs={'type':'datetime-local'}, format='%Y-%m-%dT%H:%M'), input_formats=['%Y-%m-%dT%H:%M'])
    assigned_to = forms.ModelChoiceField(queryset=get_user_model().objects.none(), required=False, label='Assigned to', empty_label='Unassigned')
    revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)

    def __init__(self, *args, dealership, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = get_user_model().objects.filter(is_active=True, membership__dealership=dealership, membership__role__in=['owner','staff']).order_by('username')


@never_cache
@member_view
@require_http_methods(['GET', 'POST'])
def edit(request, pk, activity_pk):
    if not getattr(settings, 'CUSTOMER_ACTIVITY_DEMO_ENABLED', False):
        raise Http404
    require_editor(request)
    status = 200
    with transaction.atomic():
        choices = Customer.objects.filter(dealership=request.member.dealership)
        if request.method == 'POST': choices = choices.select_for_update()
        customer = get_object_or_404(choices, pk=pk)
        activity = get_object_or_404(CustomerActivity, customer=customer, pk=activity_pk, kind__in=['follow_up','appointment'])
        initial = {'detail':activity.detail, 'due_at':activity.due_at, 'assigned_to':activity.assigned_to_id, 'revision':activity.revision}
        form = EditActivityForm(request.POST if request.method == 'POST' else None, dealership=customer.dealership, initial=initial)
        if request.method == 'POST' and form.is_valid():
            if not Membership.objects.filter(user=request.user, dealership=customer.dealership, role__in=['owner','staff']).exists():
                raise PermissionDenied
            data=form.cleaned_data
            if data['revision'] != activity.revision:
                form.add_error(None, 'This activity changed while you were editing. Your entries are kept; compare the current activity before trying again.')
                status=409
            elif data['assigned_to'] and not Membership.objects.filter(user=data['assigned_to'], user__is_active=True, dealership=customer.dealership, role__in=['owner','staff']).exists():
                form.add_error('assigned_to', 'Choose a current staff member from this dealership.')
                status=409
            else:
                before={'detail':activity.detail, 'due_at':activity.due_at.isoformat() if activity.due_at else None, 'assigned_to_id':activity.assigned_to_id}
                after={'detail':data['detail'], 'due_at':data['due_at'].isoformat() if data['due_at'] else None, 'assigned_to_id':data['assigned_to'].pk if data['assigned_to'] else None}
                if before != after:
                    activity.detail=data['detail']; activity.due_at=data['due_at']; activity.assigned_to=data['assigned_to']; activity.revision+=1
                    activity.full_clean();activity.save(update_fields=['detail','due_at','assigned_to','revision'])
                    CustomerEvent.objects.create(customer=customer,actor=request.user,changes={'action':'activity_updated','activity_id':activity.pk,'before':before,'after':after,'revision':activity.revision})
                messages.success(request,'Activity saved.')
                return redirect('customer_detail',pk=pk)
    return render(request,'customers/activity_form.html',context(request,customer=customer,activity=activity,form=form,editing=True),status=status)


@never_cache
@member_view
@require_http_methods(['GET', 'HEAD'])
def history(request, pk):
    if not getattr(settings, 'CUSTOMER_ACTIVITY_DEMO_ENABLED', False):
        raise Http404
    from django.core.paginator import Paginator
    from django.db.models import Q
    from urllib.parse import urlencode
    customer = get_object_or_404(Customer, pk=pk, dealership=request.member.dealership)
    kind = request.GET.get('kind', 'all')
    if kind not in ('all', 'note', 'follow_up', 'appointment'):
        kind = 'all'
    query = request.GET.get('q', '').strip()[:200]
    activities = customer.activities.select_related('created_by', 'completed_by', 'assigned_to')
    if kind != 'all':
        activities = activities.filter(kind=kind)
    for word in query.split():
        activities = activities.filter(Q(detail__icontains=word) | Q(assigned_to__username__icontains=word) | Q(created_by__username__icontains=word))
    page = Paginator(activities, 25).get_page(request.GET.get('page'))
    drafts = (customer.buyer_drafts.filter(dealership=request.member.dealership) | customer.co_buyer_drafts.filter(dealership=request.member.dealership)).select_related('vehicle', 'demo_completion').distinct()
    tabs = [{'label': label, 'url': '?' + urlencode({'kind': value, 'q': query}), 'active': kind == value}
            for value, label in [('all', 'All activity'), ('note', 'Notes'), ('follow_up', 'Follow-ups'), ('appointment', 'Appointments')]]
    return render(request, 'customers/activity_history.html', context(request, customer=customer, activities=page, page_obj=page, drafts=drafts, query=query, kind=kind, tabs=tabs, pagination_query=urlencode({'kind': kind, 'q': query})))
