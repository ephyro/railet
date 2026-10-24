# SPDX-License-Identifier: MPL-2.0
import uuid

from django import forms

from .services import MAX_FILE_BYTES, InvalidPdfFile, validate_pdf_bytes


class SupportingFileUploadForm(forms.Form):
    title = forms.CharField(max_length=120, strip=True, label="File title")
    pdf_file = forms.FileField(
        label="PDF file",
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,application/pdf"}),
    )
    upload_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)

    def clean_pdf_file(self):
        uploaded = self.cleaned_data["pdf_file"]
        content = bytearray()
        while len(content) <= MAX_FILE_BYTES:
            remaining = MAX_FILE_BYTES + 1 - len(content)
            chunk = uploaded.read(min(64 * 1024, remaining))
            if not chunk:
                break
            content.extend(chunk)

        if len(content) > MAX_FILE_BYTES:
            raise forms.ValidationError("Choose a PDF no larger than 8 MiB.")

        pdf_bytes = bytes(content)
        try:
            validate_pdf_bytes(pdf_bytes)
        except InvalidPdfFile as error:
            raise forms.ValidationError(str(error)) from error
        return pdf_bytes


class DealFileActionForm(forms.Form):
    ACTION_CHOICES = (("archive", "Archive"), ("restore", "Restore"))

    action = forms.ChoiceField(choices=ACTION_CHOICES, widget=forms.HiddenInput)
    reason = forms.CharField(
        required=False,
        max_length=300,
        strip=True,
        label="Reason for archiving",
        widget=forms.Textarea(attrs={"rows": 2, "maxlength": 300}),
    )

    def __init__(self, *args, expected_action=None, **kwargs):
        self.expected_action = expected_action
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get("action")
        if self.expected_action and action and action != self.expected_action:
            self.add_error("action", "Choose the action shown for this file.")
        if action == "archive" and not cleaned.get("reason"):
            self.add_error("reason", "Enter a reason to archive this file.")
        return cleaned
