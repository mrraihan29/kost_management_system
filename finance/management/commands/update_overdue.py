from django.core.management.base import BaseCommand
from django.utils import timezone
from finance.models import Invoice

class Command(BaseCommand):
    help = 'Mengecek tagihan yang jatuh tempo dan mengubah status menjadi TELAT_BAYAR'

    def handle(self, *args, **kwargs):
        self.stdout.write("Task Automation Pengecek Tagihan dimulai...")
        
        today = timezone.now().date()
        
        # 1. Cari invoice yang:
        #    - Statusnya 'BELUM_LUNAS'
        #    - Tanggal jatuh tempo (due_date) < Hari ini
        overdue_invoices = Invoice.objects.filter(
            status='BELUM_LUNAS',
            due_date__lt=today
        )
        
        count = overdue_invoices.count()
        
        if count > 0:
            self.stdout.write(f"   Ditemukan {count} tagihan telat.")
            
            # 2. Update Status Massal (Bulk Update) - Efisien untuk ratusan data
            #    Kita tidak pakai loop save() satu-satu agar cepat.
            rows_updated = overdue_invoices.update(status='TELAT_BAYAR')
            
            self.stdout.write(self.style.SUCCESS(f"Berhasil mengubah {rows_updated} tagihan menjadi TELAT_BAYAR."))
        else:
            self.stdout.write(self.style.SUCCESS("Tidak ada tagihan yang telat hari ini."))