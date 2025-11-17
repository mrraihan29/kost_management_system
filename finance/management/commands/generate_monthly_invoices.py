from django.core.management.base import BaseCommand
from django.utils import timezone
from tenants.models import TenantContract
from finance.models import Invoice
from dateutil.relativedelta import relativedelta # Perlu install library ini

class Command(BaseCommand):
    help = 'Membuat tagihan bulan depan untuk semua kontrak aktif'

    def handle(self, *args, **kwargs):
        self.stdout.write("Daftar Kontrak Aktif:")
        
        # Ambil semua kontrak aktif
        active_contracts = TenantContract.objects.filter(is_active=True)
        created_count = 0
        
        today = timezone.now().date()
        # Asumsi: Kita generate tagihan untuk periode bulan depan
        # (Logic sederhana: Tanggal 1 bulan depan)
        next_month = today + relativedelta(months=1)
        billing_start = next_month.replace(day=1) 
        # Jatuh tempo H+10 dari awal periode
        due_date = billing_start + relativedelta(days=10)

        for contract in active_contracts:
            # Cek apakah sudah ada tagihan untuk bulan tersebut agar tidak duplikat
            exists = Invoice.objects.filter(
                contract=contract,
                billing_period_start=billing_start
            ).exists()
            
            if not exists:
                Invoice.objects.create(
                    contract=contract,
                    billing_period_start=billing_start,
                    due_date=due_date,
                    base_rent_amount=contract.monthly_rent_amount,
                    electricity_bill_amount=0,
                    total_amount=contract.monthly_rent_amount, # Awalnya sama dengan sewa
                    status='BELUM_LUNAS'
                )
                self.stdout.write(f" + Tagihan dibuat untuk: {contract.tenant.full_name}")
                created_count += 1
            else:
                self.stdout.write(f" . Skip (Sudah ada): {contract.tenant.full_name}")

        self.stdout.write(self.style.SUCCESS(f"Selesai. {created_count} tagihan baru berhasil dibuat."))