# SPDX-License-Identifier: MPL-2.0
import uuid
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_GET
from core.access import context, member_view, require_editor
from core.models import Membership
from .models import DraftDeal, DealFollowUp, FollowUpEvent


class FollowUpForm(forms.Form):
    title = forms.CharField(label='What needs to happen?', max_length=120)
    detail = forms.CharField(label='Details (optional)', max_length=2000, required=False, widget=forms.Textarea(attrs={'rows':4}))
    assigned_to = forms.ModelChoiceField(label='Owner (optional)', queryset=get_user_model().objects.none(), required=False, empty_label='Unassigned')
    due_on = forms.DateField(label='Due date (optional)', required=False, input_formats=['%Y-%m-%d'], widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))
    completed = forms.BooleanField(label='Mark this follow-up complete', required=False)
    revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    creation_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)

    def __init__(self,*args,dealership,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['assigned_to'].queryset=get_user_model().objects.filter(is_active=True,membership__dealership=dealership,membership__role__in=[Membership.Role.OWNER,Membership.Role.STAFF]).order_by('username')


def records(request):
    return DealFollowUp.objects.filter(deal__dealership=request.member.dealership)


def snapshot(task):
    return {'schema_version':1,'title':task.title,'detail':task.detail,'assigned_to_id':task.assigned_to_id,
            'due_on':task.due_on.isoformat() if task.due_on else None,
            'completed_at':task.completed_at.isoformat() if task.completed_at else None,
            'completed_by_id':task.completed_by_id,'revision':task.revision}


def save_form(request,form,deal,task=None):
    """Caller locks the scoped parent; lifecycle uses the same parent lock."""
    if not Membership.objects.filter(user=request.user,dealership=deal.dealership,role__in=[Membership.Role.OWNER,Membership.Role.STAFF]).exists():
        raise PermissionDenied
    data=form.cleaned_data
    if task is None:
        prior=deal.follow_ups.filter(creation_key=data['creation_key']).first()
        if prior:
            same=all(getattr(prior,key)==data[key] for key in ('title','detail','due_on')) and prior.assigned_to_id==(data['assigned_to'].pk if data['assigned_to'] else None) and bool(prior.completed_at)==data['completed']
            if not same or prior.created_by_id!=request.user.pk:
                form.add_error(None,'This form already created a different follow-up. Open that record or start a new form.')
                return None,409
            return prior,200
        task=DealFollowUp(deal=deal,created_by=request.user,creation_key=data['creation_key'])
        action='created'
    else:
        if data['revision']!=task.revision:
            form.add_error(None,'This follow-up changed while you were working. Your entries are preserved; compare with the latest record in another tab.')
            return None,409
        if all(getattr(task,key)==data[key] for key in ('title','detail','due_on')) and task.assigned_to_id==(data['assigned_to'].pk if data['assigned_to'] else None) and bool(task.completed_at)==data['completed']:
            return task,200
        action='completed' if data['completed'] and not task.completed_at else 'reopened' if not data['completed'] and task.completed_at else 'updated'
        task.revision+=1
    assignee=data['assigned_to']
    if assignee and not Membership.objects.filter(user=assignee,user__is_active=True,dealership=deal.dealership,role__in=[Membership.Role.OWNER,Membership.Role.STAFF]).exists():
        form.add_error('assigned_to','Choose a current staff member from this dealership.')
        return None,409
    for key in ('title','detail','assigned_to','due_on'):setattr(task,key,data[key])
    if data['completed'] and not task.completed_at:
        task.completed_at=timezone.now();task.completed_by=request.user
    elif not data['completed']:
        task.completed_at=None;task.completed_by=None
    task.full_clean();task.save()
    FollowUpEvent.objects.create(follow_up=task,actor=request.user,action=action,snapshot=snapshot(task))
    return task,200


@never_cache
@member_view
@require_http_methods(['GET','POST'])
def editor(request,pk,task_pk=None):
    require_editor(request)
    status=200
    with transaction.atomic():
        choices=DraftDeal.objects.filter(dealership=request.member.dealership)
        deal=get_object_or_404(choices.select_for_update() if request.method=='POST' else choices,pk=pk)
        task=get_object_or_404(deal.follow_ups.select_for_update() if request.method=='POST' else deal.follow_ups,pk=task_pk) if task_pk else None
        initial={'revision':1,'assigned_to':request.user.pk,'completed':False}
        if task:
            initial={**snapshot(task),'assigned_to':task.assigned_to_id,'due_on':task.due_on,'completed':bool(task.completed_at),'creation_key':task.creation_key}
        form=FollowUpForm(request.POST if request.method=='POST' else None,dealership=request.member.dealership,initial=initial)
        if request.method=='POST' and form.is_valid():
            saved,status=save_form(request,form,deal,task)
            if saved:
                messages.success(request,'Follow-up saved. No customer message was sent.')
                return redirect('followup_detail',pk=saved.pk)
    return render(request,'deals/followup_form.html',context(request,deal=deal,task=task,form=form),status=status)


@never_cache
@member_view
@require_GET
def detail(request,pk):
    task=get_object_or_404(records(request).select_related('assigned_to','created_by','completed_by'),pk=pk)
    events=Paginator(task.events.select_related('actor'),20).get_page(request.GET.get('page'))
    return render(request,'deals/followup_detail.html',context(request,task=task,events=events))


@never_cache
@member_view
@require_GET
def listing(request):
    scope=request.GET.get('scope','open')
    if scope not in ('open','completed','all'):scope='open'
    mine=request.GET.get('mine')=='1'
    tasks=records(request)
    if scope!='all':tasks=tasks.filter(completed_at__isnull=scope=='open')
    if mine:tasks=tasks.filter(assigned_to=request.user)
    deal_id=request.GET.get('deal','')
    selected_deal=None
    if deal_id:
        if not deal_id.isascii() or not deal_id.isdecimal() or len(deal_id)>19:
            tasks=tasks.none()
        else:
            selected_deal=get_object_or_404(DraftDeal,pk=deal_id,dealership=request.member.dealership)
            tasks=tasks.filter(deal=selected_deal)
    page=Paginator(tasks.select_related('assigned_to','deal').order_by(F('due_on').asc(nulls_last=True),'pk'),25).get_page(request.GET.get('page'))
    return render(request,'deals/followup_list.html',context(request,page=page,scope=scope,mine=mine,selected_deal=selected_deal,today=timezone.localdate()))
