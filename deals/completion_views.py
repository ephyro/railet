# SPDX-License-Identifier: MPL-2.0
import uuid
from django import forms
from django.core import signing
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe
from core.access import member_view, context, require_editor
from .models import DemoDealCompletion, DemoCompletionVoid, DemoFollowOnDraft, DraftDeal
from .completion import check_gate, preview, complete, verified_snapshot, CompletionChanged, preview_void, void_completion, preview_follow_on_draft, create_follow_on_draft

SALT='railet.demo-completion.v1'


class CompletionForm(forms.Form):
    preview_token=forms.CharField(widget=forms.HiddenInput)
    review_notes=forms.CharField(max_length=1000,required=False,label='Review notes',help_text='Explain any remaining reminders. They will stay in the frozen record.',widget=forms.Textarea(attrs={'rows':3}))
    reviewed=forms.BooleanField(label='I reviewed the saved vehicle, buyers, figures, tax entries, and proposed terms.')
    demo_confirmed=forms.BooleanField(label='I understand this only freezes a rehearsal. It does not sell a vehicle, create a contract or loan, or record money.')


@member_view
@never_cache
@require_http_methods(['GET','POST'])
def prepare(request, pk):
    check_gate();require_editor(request)
    deal=get_object_or_404(DraftDeal,pk=pk,dealership=request.member.dealership)
    prior=DemoDealCompletion.objects.filter(deal=deal).first()
    if prior and request.method=='GET':return redirect('deal_completion',pk=pk)
    form=CompletionForm(request.POST if request.method=='POST' else None)
    status=200
    if request.method=='POST' and form.is_valid():
        try:
            payload=signing.loads(form.cleaned_data['preview_token'],salt=SALT,max_age=1800)
            if not isinstance(payload,dict) or not all(key in payload for key in ('key','digest','actor','dealer','deal')):
                raise signing.BadSignature
            creation_key=uuid.UUID(payload['key'])
        except (signing.BadSignature, ValueError, TypeError):
            form.add_error(None,'This review expired or is invalid. Review the refreshed figures and confirm again.');status=400
        else:
            if (payload.get('actor'),payload.get('dealer'),payload.get('deal')) != (request.user.pk,request.member.dealership_id,pk):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied
            try:
                complete(dealership_id=request.member.dealership_id,deal_id=pk,actor=request.user,creation_key=creation_key,expected_review=payload['digest'],review_notes=form.cleaned_data['review_notes'],reviewed=form.cleaned_data['reviewed'],demo_confirmed=form.cleaned_data['demo_confirmed'])
            except CompletionChanged as error:
                form.add_error(None,error);status=409
            else:
                return redirect('deal_completion',pk=pk)
    if prior:return redirect('deal_completion',pk=pk)
    try:
        source=preview(dealership_id=request.member.dealership_id,deal_id=pk)
    except CompletionChanged as error:
        return render(request,'deals/completion_error.html',context(request,deal=deal,error=' '.join(error.messages)),status=409)
    token=signing.dumps({'actor':request.user.pk,'dealer':request.member.dealership_id,'deal':pk,'key':str(uuid.uuid4()),'digest':source['review_sha256']},salt=SALT)
    if form.is_bound:
        # A stale/invalid review must not retain either confirmation checkbox.
        data=request.POST.copy();data['preview_token']=token;data.pop('reviewed',None);data.pop('demo_confirmed',None)
        errors=list(form.non_field_errors());form=CompletionForm(data);form.is_valid()
        for error in errors:form.add_error(None,error)
    else:
        form=CompletionForm(initial={'preview_token':token})
    form.fields['review_notes'].required=bool(source['snapshot']['reminders'])
    response=render(request,'deals/completion_prepare.html',context(request,deal=deal,source=source,snapshot=source['snapshot'],form=form),status=status)
    response['Cache-Control']='private, no-store'
    return response


@member_view
@never_cache
@require_safe
def detail(request, pk):
    check_gate()
    record=get_object_or_404(DemoDealCompletion.objects.select_related('packet','actor'),deal_id=pk,deal__dealership=request.member.dealership)
    try:snapshot=verified_snapshot(record)
    except CompletionChanged as error:
        return HttpResponse(' '.join(error.messages),status=409,content_type='text/plain')
    from finance.account_services import draft_account
    account=draft_account(dealership_id=request.member.dealership_id,deal_id=pk)
    from finance.account_services import completion_has_account
    return render(request,'deals/completion_detail.html',context(request,record=record,snapshot=snapshot,demo_account=account, has_account=completion_has_account(deal_id=pk), void_record=DemoCompletionVoid.objects.filter(completion=record).select_related('actor').first(), follow_on=DemoFollowOnDraft.objects.filter(void_rehearsal__completion=record).first()))


class VoidForm(forms.Form):
    preview_token = forms.CharField(widget=forms.HiddenInput)
    reason = forms.CharField(max_length=1000, label='Reason for this rehearsal', widget=forms.Textarea(attrs={'rows': 3}))
    confirmed = forms.BooleanField(label='I understand this is only an internal rehearsal and does not cancel a sale, contract, payment or balance.')


@member_view
@never_cache
@require_http_methods(['GET', 'POST'])
def void_review(request, pk):
    check_gate(); require_editor(request)
    form = VoidForm(request.POST if request.method == 'POST' else None)
    status = 200
    if request.method == 'POST' and form.is_valid():
        try:
            payload = signing.loads(form.cleaned_data['preview_token'], salt='railet.completion-void.v1', max_age=1800)
            if not isinstance(payload, dict) or (payload['actor'], payload['dealer'], payload['deal']) != (request.user.pk, request.member.dealership_id, pk):
                raise signing.BadSignature
            key = uuid.UUID(payload['key'])
            void_completion(dealership_id=request.member.dealership_id, deal_id=pk, actor=request.user, creation_key=key, expected_review=payload['digest'], reason=form.cleaned_data['reason'])
        except (signing.BadSignature, KeyError, ValueError, TypeError):
            form.add_error(None, 'This review expired or is invalid. Review again.'); status = 400
        except CompletionChanged as error:
            form.add_error(None, error); status = 409
        else:
            return redirect('deal_completion', pk=pk)
    try:
        record, digest, prior = preview_void(dealership_id=request.member.dealership_id, deal_id=pk, actor=request.user)
    except CompletionChanged as error:
        return render(request, 'deals/completion_error.html', context(request, deal=get_object_or_404(DraftDeal, pk=pk, dealership=request.member.dealership), error=' '.join(error.messages)), status=409)
    if prior:
        if request.method == 'POST':
            return render(request, 'deals/completion_error.html', context(request, deal=record.deal, error='This completion already has a void rehearsal.'), status=409)
        return redirect('deal_completion', pk=pk)
    token = signing.dumps({'actor': request.user.pk, 'dealer': request.member.dealership_id, 'deal': pk, 'key': str(uuid.uuid4()), 'digest': digest}, salt='railet.completion-void.v1')
    if form.is_bound:
        data = request.POST.copy(); data['preview_token'] = token; data.pop('confirmed', None)
        errors = list(form.non_field_errors())
        form = VoidForm(data); form.is_valid()
        for error in errors: form.add_error(None, error)
    else:
        form = VoidForm(initial={'preview_token': token})
    return render(request, 'deals/completion_void.html', context(request, record=record, snapshot=verified_snapshot(record), form=form), status=status)


class FollowOnForm(forms.Form):
    preview_token = forms.CharField(widget=forms.HiddenInput)
    reason = forms.CharField(max_length=1000, label='Reason for a new draft', widget=forms.Textarea(attrs={'rows': 3}))
    confirmed = forms.BooleanField(label='I understand this creates a separate synthetic draft, not a legal amendment or sale.')


@member_view
@never_cache
@require_http_methods(['GET', 'POST'])
def follow_on_review(request, pk):
    check_gate(); require_editor(request)
    form = FollowOnForm(request.POST if request.method == 'POST' else None)
    status = 200
    if request.method == 'POST' and form.is_valid():
        try:
            payload = signing.loads(form.cleaned_data['preview_token'], salt='railet.follow-on.v1', max_age=1800)
            if not isinstance(payload, dict) or (payload['actor'], payload['dealer'], payload['deal']) != (request.user.pk, request.member.dealership_id, pk):
                raise signing.BadSignature
            key = uuid.UUID(payload['key'])
            result = create_follow_on_draft(dealership_id=request.member.dealership_id, deal_id=pk, actor=request.user, creation_key=key, expected_review=payload['digest'], reason=form.cleaned_data['reason'], confirmed=form.cleaned_data['confirmed'])
        except (signing.BadSignature, KeyError, ValueError, TypeError):
            form.add_error(None, 'This review expired or is invalid. Review again.'); status = 400
        except CompletionChanged as error:
            form.add_error(None, error); status = 409
        else:
            return redirect('deal_detail', pk=result.draft_id)
    try:
        state = preview_follow_on_draft(dealership_id=request.member.dealership_id, deal_id=pk, actor=request.user)
    except CompletionChanged as error:
        return render(request, 'deals/completion_error.html', context(request, deal=get_object_or_404(DraftDeal, pk=pk, dealership=request.member.dealership), error=' '.join(error.messages)), status=409)
    if state['prior']:
        if request.method == 'POST':
            return render(request, 'deals/completion_error.html', context(request, deal=state['record'].deal, error='A follow-on draft has already been created.'), status=409)
        return redirect('deal_detail', pk=state['prior'].draft_id)
    token = signing.dumps({'actor': request.user.pk, 'dealer': request.member.dealership_id, 'deal': pk, 'key': str(uuid.uuid4()), 'digest': state['review_sha256']}, salt='railet.follow-on.v1')
    if form.is_bound:
        data = request.POST.copy(); data['preview_token'] = token; data.pop('confirmed', None)
        errors = list(form.non_field_errors()); form = FollowOnForm(data); form.is_valid()
        for error in errors: form.add_error(None, error)
    else:
        form = FollowOnForm(initial={'preview_token': token})
    return render(request, 'deals/completion_follow_on.html', context(request, state=state, form=form), status=status)
