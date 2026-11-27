from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager

    from tenants.models import TenantContract


# Create your models here.
class KostLocation(models.Model):
    name = models.CharField(max_length=100)
    address = models.TextField()
    description = models.TextField(blank=True, null=True)  # noqa: DJ001 schema change deferred to EKM-19 (location migration)
    # Tarif Berdasarkan Listrik per lokasi (FR-06)
    electricity_rate_per_kwh = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("1500.00")
    )

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
