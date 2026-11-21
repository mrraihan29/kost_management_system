from dateutil.relativedelta import relativedelta  # Perlu install library ini
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from django.utils import timezone

from finance.models import Invoice
from tenants.models import TenantContract


class Command(BaseCommand):
    help = "Membuat tagihan bulan depan untuk semua kontrak aktif"

    def handle(self, *args, **kwargs):
        self.stdout.write("Daftar Kontrak Aktif:")

        # Ambil semua kontrak aktif
        active_contracts = TenantContract.objects.filter(is_active=True).select_related(
            "tenant", "room"
        )
        created_count = 0

        today = timezone.now().date()
        billing_start_base = (today + relativedelta(months=1)).replace(day=1)

        for contract in active_contracts:
            location_name = (contract.room.kost_location.name or "").strip().lower()
            is_ancol = "ancol" in location_name

            if is_ancol:
                # ANCOL: siklus per-tenant berdasarkan tanggal kontrak
                try:
                    billing_start = billing_start_base.replace(day=contract.start_date.day)
                except ValueError:
                    billing_start = billing_start_base.replace(day=28)
                # W5/BQ-1: jatuh tempo = tanggal tagihan + 10 hari
                due_date = billing_start + relativedelta(days=10)
            else:
                # NON-ANCOL: serentak mengikuti tanggal global sistem
                billing_start = billing_start_base
                due_date = billing_start + relativedelta(days=10)

            # W4/BQ-6: cek periode ternormalisasi (race ditangani lewat IntegrityError)
            exists = Invoice.objects.filter(
                contract=contract,
                billing_period_year=billing_start.year,
                billing_period_month=billing_start.month,
            ).exists()

            if not exists:
                try:
                    Invoice.objects.create(
                        contract=contract,
                        billing_period_start=billing_start,
                        due_date=due_date,
                        base_rent_amount=contract.monthly_rent_amount,
                        electricity_bill_amount=0,
                        total_amount=contract.monthly_rent_amount,
                        status="BELUM_LUNAS",
                    )
                except IntegrityError:
                    self.stdout.write(f" . Skip (race): {contract.tenant.full_name}")
                    continue
                self.stdout.write(
                    f" + Tagihan dibuat untuk: {contract.tenant.full_name} (tgl {billing_start})"
                )
                created_count += 1
            else:
                self.stdout.write(f" . Skip (Sudah ada): {contract.tenant.full_name}")

        self.stdout.write(
            self.style.SUCCESS(f"Selesai. {created_count} tagihan baru berhasil dibuat.")
        )
