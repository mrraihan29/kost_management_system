import os
import secrets
import string
import uuid
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from core.models import Room

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager

    from finance.models import Invoice


# Fungsi utilitas untuk merename file KTP agar unik (Security NFR-02)
def ktp_upload_path(instance, filename):
    ext = filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    # Simpan di: media/ktp_private/UUID.jpg
    return os.path.join("ktp_private", filename)


class Tenant(models.Model):
    if TYPE_CHECKING:
        contracts: RelatedManager["TenantContract"]

    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=20)
    emergency_contact_phone = models.CharField(max_length=20)

    # Upload KTP (Opsional sesuai FR-05)
    ktp_photo = models.ImageField(upload_to=ktp_upload_path, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name


class TenantContract(models.Model):
    if TYPE_CHECKING:
        id: int
        invoices: RelatedManager["Invoice"]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="contracts")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="contracts")

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # Opsional, jika sewa berakhir

    monthly_rent_amount = models.DecimalField(max_digits=12, decimal_places=2)

    # PIN Pembayaran (FR-02) - Unik per kontrak
    payment_pin = models.CharField(
        max_length=6,
        unique=True,
        blank=True,
        help_text="PIN 6 digit unik. Terisi otomatis jika kosong.",
    )

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room"],
                condition=Q(is_active=True),
                name="uniq_active_contract_per_room",
            ),
            models.UniqueConstraint(
                fields=["tenant"],
                condition=Q(is_active=True),
                name="uniq_active_contract_per_tenant",
            ),
        ]

    def __str__(self):
        return f"Kontrak: {self.tenant.full_name} - {self.room.room_number}"

    # --- OVERRIDE SAVE ---
    def save(self, *args, **kwargs):
        # Jika PIN kosong, generate baru
        if not self.payment_pin:
            self.payment_pin = self.generate_unique_pin()
        self.full_clean()
        # B-08 fix: Handle race condition — jika PIN sudah diambil antara
        # check dan save, retry dengan PIN baru
        from django.db import IntegrityError

        max_retries = 3
        for attempt in range(max_retries):
            try:
                super().save(*args, **kwargs)
                return
            except IntegrityError as e:
                if "payment_pin" in str(e) and attempt < max_retries - 1:
                    self.payment_pin = self.generate_unique_pin()
                else:
                    raise

    def clean(self):
        if not self.is_active:
            return

        room = getattr(self, "room", None)
        tenant = getattr(self, "tenant", None)

        if not room or not tenant:
            return

        if TenantContract.objects.filter(room=room, is_active=True).exclude(pk=self.pk).exists():
            raise ValidationError({"room": "Kamar ini sudah memiliki kontrak aktif."})

        if (
            TenantContract.objects.filter(tenant=tenant, is_active=True)
            .exclude(pk=self.pk)
            .exists()
        ):
            raise ValidationError({"tenant": "Tenant ini sudah memiliki kontrak aktif."})

    def generate_unique_pin(self):
        # Loop sampai menemukan PIN yang belum dipakai (untuk hindari duplikat)
        # W10/BQ-4: gunakan CSPRNG (secrets), bukan random
        while True:
            new_pin = "".join(secrets.choice(string.digits) for _ in range(6))
            if not TenantContract.objects.filter(payment_pin=new_pin).exists():
                return new_pin


def ticket_upload_path(instance, filename):
    ext = filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join("maintenance_tickets", filename)


class MaintenanceTicket(models.Model):
    if TYPE_CHECKING:
        id: int

        def get_status_display(self) -> str: ...

    STATUS_CHOICES = [
        ("PENDING", "Menunggu Respon"),
        ("PROSES", "Sedang Diperbaiki"),
        ("SELESAI", "Selesai"),
        ("DITOLAK", "Ditolak/Batal"),
    ]

    PRIORITY_CHOICES = [
        ("LOW", "Rendah (Tidak Mendesak)"),
        ("MEDIUM", "Sedang"),
        ("HIGH", "Tinggi (Darurat/Bahaya)"),
    ]

    contract = models.ForeignKey(TenantContract, on_delete=models.CASCADE, related_name="tickets")
    title = models.CharField(max_length=200, verbose_name="Judul Laporan")
    description = models.TextField(verbose_name="Detail Kerusakan")
    photo = models.ImageField(
        upload_to=ticket_upload_path, blank=True, null=True, verbose_name="Foto Bukti"
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="MEDIUM")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # Kapan status terakhir berubah

    completion_date = models.DateTimeField(null=True, blank=True, verbose_name="Tanggal Selesai")

    def __str__(self):
        return f"Tiket #{self.id}: {self.title}"
