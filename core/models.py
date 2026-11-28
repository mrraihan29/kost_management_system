import re
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager

    from tenants.models import TenantContract


OWNER_ONLY_LOCATION_FIELDS: tuple[str, ...] = (
    "billing_mode",
    "bills_electricity",
    "bank_name",
    "bank_account_number",
    "bank_account_holder",
)


def validate_bank_account_number(value: str) -> None:
    """Validate Indonesian bank account numbers (blank or 6-20 digits with optional spaces)."""
    if not value.strip():
        return
    if not re.fullmatch(r"[0-9 ]+", value) or not (6 <= sum(ch.isdigit() for ch in value) <= 20):
        raise ValidationError(
            "Nomor rekening hanya boleh berisi angka dan spasi, sebanyak 6 sampai 20 digit."
        )


# Create your models here.
class KostLocation(models.Model):
    class BillingMode(models.TextChoices):
        PER_ROOM_CYCLE = "per_room_cycle", "Siklus per kamar"
        SIMULTANEOUS = "simultaneous", "Serentak per bulan"

    name = models.CharField(max_length=100)
    address = models.TextField()
    description = models.TextField(blank=True, null=True)  # noqa: DJ001 schema change deferred to EKM-19 (location migration)
    # Tarif Berdasarkan Listrik per lokasi (FR-06)
    electricity_rate_per_kwh = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("1500.00")
    )
    billing_mode = models.CharField(
        max_length=20,
        choices=BillingMode.choices,
        default=BillingMode.SIMULTANEOUS,
    )
    bills_electricity = models.BooleanField(default=False)
    bank_name = models.CharField(max_length=100, blank=True, default="")
    bank_account_number = models.CharField(
        max_length=32,
        blank=True,
        default="",
        validators=[validate_bank_account_number],
    )
    bank_account_holder = models.CharField(max_length=120, blank=True, default="")

    def __str__(self):
        return self.name


class Room(models.Model):
    if TYPE_CHECKING:
        contracts: RelatedManager[TenantContract]
        # set by the dashboard views (prefetch to_attr)
        active_contracts: list[TenantContract]
        active_contract: TenantContract | None

    kost_location = models.ForeignKey(KostLocation, on_delete=models.PROTECT, related_name="rooms")
    room_number = models.CharField(max_length=20)  # Cth: "A-101"
    price_monthly = models.DecimalField(max_digits=12, decimal_places=2)  # Harga dasar kamar
    is_token_electricity = models.BooleanField(
        default=False
    )  # True=Token, False=Meteran Manual (FR-06)
    capacity = models.IntegerField(
        default=1, help_text="Kapasitas kamar (informasi saja, tidak mempengaruhi assignment)"
    )

    class Meta:
        unique_together = ["kost_location", "room_number"]

    def __str__(self):
        return f"{self.kost_location.name} - {self.room_number}"
