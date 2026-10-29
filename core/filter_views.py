# SPDX-License-Identifier: MPL-2.0
import json

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from railet.filtersets import SCHEMAS
from .access import member_view, context
from .filtering import FilterState
from .models import Membership, SavedView


def available_schema(resource):
    schema = SCHEMAS.get(resource)
    if schema and schema.enabled_setting and not getattr(settings, schema.enabled_setting, False):
        return None
    return schema


def own_views(request, resource):
    return SavedView.objects.filter(dealership=request.member.dealership, owner=request.user, resource=resource)


def decode_parameters(schema, raw):
    allowed = {"q", "sort", "match", "filter_field", "filter_op", "filter_value", "filter_to", *schema.extras}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValidationError("This view contains unsupported filter settings.")
    params = QueryDict("", mutable=True)
    for key, values in raw.items():
        if not isinstance(values, list) or len(values) > 10 or any(not isinstance(value, str) or len(value) > 200 for value in values):
            raise ValidationError("This view contains invalid filter values.")
        params.setlist(key, values)
    return params


def filter_context(request, schema):
    selected = None
    params = request.GET
    if request.GET.get("view"):
        try:
            pk = forms.IntegerField(min_value=1, max_value=9223372036854775807).clean(request.GET["view"])
        except ValidationError:
            raise Http404("Saved view not found")
        selected = get_object_or_404(own_views(request, schema.resource), pk=pk)
        try:
            params = decode_parameters(schema, selected.parameters)
        except ValidationError:
            state = FilterState(schema, QueryDict(""))
            state.errors.append("This saved view needs to be rebuilt. Choose new filters before applying it.")
            return {"filter_state": state, "filter_schema": schema, "saved_views": own_views(request, schema.resource), "selected_view": selected, "pagination_query": f"view={selected.pk}"}
    state = FilterState(schema, params)
    return {
        "filter_state": state, "filter_schema": schema,
        "saved_views": own_views(request, schema.resource), "selected_view": selected,
        "pagination_query": f"view={selected.pk}" if selected else state.querystring,
    }


class SaveViewForm(forms.Form):
    name = forms.CharField(max_length=60, label="View name")
    parameters = forms.CharField(widget=forms.HiddenInput, max_length=12000)


@member_view
def saved_view_create(request, resource):
    schema = available_schema(resource)
    if schema is None:
        raise Http404("Unknown view")
    if request.method == "POST":
        form = SaveViewForm(request.POST)
        state = None
        if form.is_valid():
            try:
                params = decode_parameters(schema, json.loads(form.cleaned_data["parameters"]))
                state = FilterState(schema, params)
                if state.errors:
                    raise ValidationError(state.errors)
            except (ValidationError, ValueError, TypeError) as error:
                form.add_error(None, "The filters could not be saved. Return to the list and check them.")
            else:
                with transaction.atomic():
                    Membership.objects.select_for_update().get(pk=request.member.pk)
                    views = own_views(request, resource)
                    if views.count() >= 50:
                        form.add_error(None, "Keep up to 50 saved views per list. Remove an old view first.")
                    elif views.filter(name=form.cleaned_data["name"]).exists():
                        form.add_error("name", "You already have a view with this name. Choose another name.")
                    else:
                        saved = SavedView.objects.create(dealership=request.member.dealership, owner=request.user, resource=resource, name=form.cleaned_data["name"], parameters=state.parameters)
                        messages.success(request, "View saved. Only you can see it.")
                        return redirect(reverse(schema.route) + f"?view={saved.pk}")
    else:
        state = FilterState(schema, request.GET)
        form = SaveViewForm(initial={"parameters": json.dumps(state.parameters)})
    return render(request, "core/save_view.html", context(request, form=form, filter_state=state, filter_schema=schema))


@member_view
@require_POST
def saved_view_delete(request, pk):
    saved = get_object_or_404(SavedView, pk=pk, dealership=request.member.dealership, owner=request.user)
    schema = available_schema(saved.resource)
    saved.delete()
    messages.success(request, "Saved view removed.")
    return redirect(schema.route if schema else "today")
