# SPDX-License-Identifier: MPL-2.0
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from core.access import context, member_view, require_editor
from core.models import Dealership, Membership
from .models import DraftDeal
from .services import persist_draft


class LifecycleForm(forms.Form):
    revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    action = forms.ChoiceField(choices=[('archive','Archive'),('restore','Restore')], widget=forms.HiddenInput)
    reason = forms.CharField(label='Reason', max_length=300, widget=forms.Textarea(attrs={'rows':3}))


@never_cache
@member_view
@require_http_methods(['GET','POST'])
def change_state(request, pk):
    require_editor(request)
    with transaction.atomic():
        if request.method == "POST":
            Dealership.objects.select_for_update().get(pk=request.member.dealership_id)
        choices = DraftDeal.objects.filter(dealership=request.member.dealership)
        deal = get_object_or_404(choices.select_for_update() if request.method == "POST" else choices, pk=pk)
        related = [deal.vehicle, deal.buyer] + ([deal.co_buyer] if deal.co_buyer_id else [])
        if any(record.dealership_id != request.member.dealership_id for record in related):
            raise Http404
        action = 'restore' if deal.archived_at else 'archive'
        form = LifecycleForm(request.POST if request.method=='POST' else None, initial={'revision':deal.revision,'action':action})
        status = 200
        if request.method=='POST' and form.is_valid():
            if form.cleaned_data['revision'] != deal.revision or form.cleaned_data['action'] != action:
                form.add_error(None,'This draft changed. Your reason is preserved; open the latest draft in another tab and review its state before trying again.')
                status = 409
            else:
                # Recheck membership inside the write transaction.
                if not Membership.objects.filter(user=request.user,dealership=deal.dealership,role__in=[Membership.Role.OWNER,Membership.Role.STAFF]).exists():
                    raise PermissionDenied
                reason = form.cleaned_data['reason']
                deal.archived_at = timezone.now() if action=='archive' else None
                deal.archived_by = request.user if action=='archive' else None
                deal.archive_reason = reason if action=='archive' else ''
                deal.revision += 1
                persist_draft(deal,actor=request.user,action='draft_archived' if action=='archive' else 'draft_restored',reason=reason)
                messages.success(request,'Draft archived. Its history and saved packets are retained.' if action=='archive' else 'Draft restored to active drafts.')
                return redirect('deal_detail',pk=deal.pk)
    return render(request,'deals/lifecycle.html',context(request,deal=deal,form=form,action=action),status=status)
