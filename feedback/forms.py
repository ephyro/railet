# SPDX-License-Identifier: MPL-2.0
import uuid
from django import forms
from .models import FeedbackReport


class ReportForm(forms.Form):
    submission_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    kind = forms.ChoiceField(label='How can we help?', choices=FeedbackReport.Kind.choices)
    area = forms.ChoiceField(label='Where were you working?', choices=FeedbackReport.Area.choices)
    subject = forms.CharField(label='Short description', max_length=120)
    expected = forms.CharField(label='What were you trying to do?', max_length=2000, widget=forms.Textarea(attrs={'rows': 4}))
    actual = forms.CharField(label='What happened, or what would make it easier?', max_length=2000, widget=forms.Textarea(attrs={'rows': 5}))
    privacy_checked = forms.BooleanField(label='I used invented examples and removed customer information, credentials, and private document details.')

    def clean(self):
        data = super().clean()
        if self.files:
            raise forms.ValidationError('Attachments are not accepted. Describe the problem using invented examples.')
        return data
