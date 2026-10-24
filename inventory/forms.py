# SPDX-License-Identifier: MPL-2.0
from django import forms
from .models import Vehicle
from .identity import ODOMETER_FIELDS
from .vin_matching import matching_vehicles, normalize_vin


class VehicleChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, vehicle):
        vin = f" · VIN …{vehicle.vin[-6:]}" if vehicle.vin else ""
        return f"{vehicle} · Stock {vehicle.stock_number}{vin}"


class MultiplePhotoInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class PhotoBatchField(forms.FileField):
    widget = MultiplePhotoInput(attrs={"accept": "image/jpeg,image/png,image/webp"})

    def clean(self, data, initial=None):
        from .photos import normalize_photo
        files = data if isinstance(data, (list, tuple)) else [data] if data else []
        if not files:
            raise forms.ValidationError("Choose at least one photo.")
        if len(files) > 8:
            raise forms.ValidationError("Upload up to 8 photos at a time.")
        return [normalize_photo(super(PhotoBatchField, self).clean(file, initial)) for file in files]


class VehiclePhotoForm(forms.Form):
    photos = PhotoBatchField(label="Add vehicle photos", help_text="JPEG, PNG, or WebP · up to 8 MB each. Choose up to 8 photos. Vehicle photos only; avoid customer documents.")

class VehicleForm(forms.ModelForm):
    revision = forms.IntegerField(widget=forms.HiddenInput, min_value=1, required=False)
    duplicate_review_acknowledged = forms.BooleanField(
        required=False,
        label="I reviewed these records and want to save a separate vehicle record",
    )
    duplicate_review_reason = forms.CharField(
        required=False,
        max_length=300,
        strip=True,
        label="Reason for saving a separate vehicle record",
        help_text="For example, this may be a reacquisition or a correction to legacy stock identity. Matching VINs are not always accidental duplicates.",
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": 300}),
    )

    def __init__(self, *args, **kwargs):
        self.dealership = kwargs.pop("dealership", None)
        instance = kwargs.get("instance")
        if instance is None and len(args) > 1:
            instance = args[1]
        self.original_normalized_vin = normalize_vin(getattr(instance, "vin", ""))
        self.duplicate_matches = []
        # Older inventory forms must preserve mileage that they never displayed.
        if args and args[0] is not None:
            data = args[0].copy()
            instance = kwargs.get("instance") or Vehicle()
            for name in ODOMETER_FIELDS:
                if name not in data:
                    value = getattr(instance, name)
                    data[name] = "" if value is None else value
            args = (data, *args[1:])
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["revision"].required = True
            self.initial["revision"] = self.instance.revision

    class Meta:
        model = Vehicle
        fields = ["stock_number", "vin", "year", "make", "model", "status", "title_brand", "title_received", *ODOMETER_FIELDS, "acquisition_cost", "recon_cost", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}
    def clean_stock_number(self):
        return self.cleaned_data["stock_number"].strip().upper()
    def clean_vin(self):
        return self.cleaned_data["vin"].strip().upper()

    def clean(self):
        cleaned = super().clean()
        vin = normalize_vin(cleaned.get("vin"))
        changed_identity = bool(vin) and (
            not self.instance.pk or vin != self.original_normalized_vin
        )
        if self.dealership is not None and changed_identity:
            self.duplicate_matches = list(matching_vehicles(
                dealership=self.dealership,
                vin=vin,
                exclude_vehicle_id=self.instance.pk,
            ))

        if self.duplicate_matches:
            if not cleaned.get("duplicate_review_acknowledged"):
                self.add_error(
                    "duplicate_review_acknowledged",
                    "Review the matching records and check this box before saving a separate vehicle record.",
                )
            if not cleaned.get("duplicate_review_reason") and not self.errors.get("duplicate_review_reason"):
                self.add_error(
                    "duplicate_review_reason",
                    "Enter a reason for keeping this as a separate vehicle record.",
                )
        return cleaned

    @property
    def duplicate_review_metadata(self):
        if not self.duplicate_matches:
            return None
        return {
            "matched_vehicle_ids": [vehicle.pk for vehicle in self.duplicate_matches],
            "reason": self.cleaned_data["duplicate_review_reason"],
        }
