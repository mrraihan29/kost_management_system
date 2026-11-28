from django import forms
from django.http import HttpRequest

from config.security import log_action

from .models import OWNER_ONLY_LOCATION_FIELDS, KostLocation, Room


def audit_location_setting_changes(
    request: HttpRequest,
    location: KostLocation,
    before: dict[str, object],
) -> None:
    """Record one T-013 audit entry for each owner-only setting that changed."""
    for field in OWNER_ONLY_LOCATION_FIELDS:
        old_val = before.get(field)
        new_val = getattr(location, field)
        if old_val != new_val:
            log_action(
                request,
                "LOCATION_SETTING_CHANGED",
                f"Location #{location.pk} ({location.name})",
                f"field={field} old={old_val!r} new={new_val!r}",
            )


class KostLocationForm(forms.ModelForm):
    """Form pengaturan dasar lokasi & tarif yang dapat diedit Staff dan Owner."""

    class Meta:
        model = KostLocation
        fields = ["name", "address", "electricity_rate_per_kwh", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control-clean"}),
            "address": forms.Textarea(attrs={"class": "form-control-clean", "rows": 3}),
            "electricity_rate_per_kwh": forms.NumberInput(attrs={"class": "form-control-clean"}),
            "description": forms.Textarea(attrs={"class": "form-control-clean", "rows": 3}),
        }
        labels = {
            "name": "Nama Kost",
            "address": "Alamat Lengkap",
            "electricity_rate_per_kwh": "Tarif Listrik per KWH (Rp)",
            "description": "Deskripsi / Catatan Tambahan",
        }


class KostLocationOwnerForm(KostLocationForm):
    """Extended location settings form including Owner-only billing & bank fields."""

    class Meta(KostLocationForm.Meta):
        fields = [*KostLocationForm.Meta.fields, *OWNER_ONLY_LOCATION_FIELDS]
        labels = {
            **KostLocationForm.Meta.labels,
            "billing_mode": "Mode penagihan",
            "bills_electricity": "Tagih listrik lewat aplikasi",
            "bank_name": "Nama bank",
            "bank_account_number": "Nomor rekening",
            "bank_account_holder": "Atas nama rekening",
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.fields["billing_mode"].required = False

    def clean_billing_mode(self) -> str:
        val = self.cleaned_data.get("billing_mode")
        if not val:
            return self.instance.billing_mode or KostLocation.BillingMode.SIMULTANEOUS
        return str(val)

    def clean_bank_name(self) -> str:
        return (self.cleaned_data.get("bank_name") or "").strip()

    def clean_bank_account_number(self) -> str:
        val = (self.cleaned_data.get("bank_account_number") or "").strip()
        return val if val else ""

    def clean_bank_account_holder(self) -> str:
        return (self.cleaned_data.get("bank_account_holder") or "").strip()


class RoomForm(forms.ModelForm):
    """
    Form Kelola Kamar (B-CRUD-04)
    """

    class Meta:
        model = Room
        fields = [
            "kost_location",
            "room_number",
            "price_monthly",
            "is_token_electricity",
            "capacity",
        ]
        widgets = {
            "kost_location": forms.Select(
                attrs={"class": "form-select shadow-none border-secondary"}
            ),
            "room_number": forms.TextInput(
                attrs={"class": "form-control-clean", "placeholder": "Contoh: A-101"}
            ),
            "price_monthly": forms.NumberInput(
                attrs={"class": "form-control-clean", "placeholder": "Contoh: 1500000"}
            ),
            "is_token_electricity": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "capacity": forms.NumberInput(
                attrs={"class": "form-control-clean", "placeholder": "1"}
            ),
        }
        labels = {
            "kost_location": "Lokasi Kost",
            "room_number": "Nomor Kamar",
            "price_monthly": "Harga Sewa Bulanan (Rp)",
            "is_token_electricity": "Listrik Token (Prabayar)",
            "capacity": "Kapasitas (Orang)",
        }
