import random
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from faker import Faker

# Import yang sudah diperbaiki
from core.models import KostLocation, Room
from finance.models import Invoice
from tenants.models import Tenant, TenantContract

User = get_user_model()
fake = Faker(['id_ID']) 

class Command(BaseCommand):
    help = 'Mengisi database dengan data dummy AKURAT (Ancol=40, Kana=6, UNS=22)'

    def handle(self, *args, **kwargs):
        self.stdout.write("Memulai Seeding Data Akurat...")

        # SEC-15: TIDAK lagi auto-create superuser dengan password hardcoded.
        # Buat superuser secara manual: python manage.py createsuperuser
        if not User.objects.filter(is_superuser=True).exists():
            self.stdout.write(self.style.WARNING(
                "   ! Belum ada superuser. Buat manual: python manage.py createsuperuser"
            ))

        # 2. Definisi Data Real (Nama, Alamat, Tarif, JUMLAH KAMAR)
        locations_config = [
            {
                'name': 'Kost Ancol', 
                'addr': 'Jl. Pasir Putih, Ancol', 
                'rate': 1500, 
                'room_count': 40  # Sesuai Realita
            },
            {
                'name': 'Kost Kana', 
                'addr': 'Jl. Dago Pakar, Bandung', 
                'rate': 1700, 
                'room_count': 6   # Sesuai Realita
            },
            {
                'name': 'Kost UNS', 
                'addr': 'Jl. Ir Sutami, Solo', 
                'rate': 1300, 
                'room_count': 22  # Sesuai Realita
            },
        ]
        
        # 3. Loop per Lokasi Konfigurasi
        for config in locations_config:
            # Buat Lokasi
            loc_obj, created = KostLocation.objects.get_or_create(
                name=config['name'],
                defaults={
                    'address': config['addr'], 
                    'electricity_rate_per_kwh': config['rate']
                }
            )
            self.stdout.write(f"   Processing Lokasi: {loc_obj.name} ({config['room_count']} Kamar)...")

            # Buat Kamar Sesuai Jumlah (room_count)
            for i in range(1, config['room_count'] + 1):
                # Format Nomor Kamar: Huruf Depan + Nomor (A-101, K-101, U-101)
                prefix = config['name'][5] # Ambil huruf setelah "Kost "
                room_num = f"{prefix}-{100+i}" 
                
                Room.objects.get_or_create(
                    kost_location=loc_obj,
                    room_number=room_num,
                    defaults={'price_monthly': Decimal(random.choice([1000000, 1500000, 2000000]))}
                )

        self.stdout.write("   + Semua Kamar berhasil dibuat sesuai jumlah real.")

        # 4. Buat Penghuni & Kontrak (Isi 80% dari total kamar yang ada)
        # C-DB-03: Hanya kamar yang belum punya kontrak (idempotent)
        all_rooms = list(Room.objects.filter(contracts__isnull=True))
        total_rooms = Room.objects.count()
        
        if not all_rooms:
            self.stdout.write(self.style.WARNING("   Semua kamar sudah terisi. Skip pembuatan tenant."))
            self.stdout.write(self.style.SUCCESS(f"SEEDING AKURAT SELESAI! Total {total_rooms} Kamar, 0 Penghuni baru."))
            return
        
        target_tenants = min(int(total_rooms * 0.8), len(all_rooms))
        occupied_rooms = random.sample(all_rooms, target_tenants)

        self.stdout.write(f"   + Mengisi {target_tenants} penghuni ke dalam kamar...")

        for room in occupied_rooms:
            # Buat Tenant
            tenant = Tenant.objects.create(
                full_name=fake.name(),
                phone_number=fake.phone_number(),
                emergency_contact_phone=fake.phone_number()
            )

            # Buat Kontrak
            months_ago = random.randint(1, 5)
            start_date = timezone.now().date() - relativedelta(months=months_ago)
            
            contract = TenantContract.objects.create(
                tenant=tenant,
                room=room,
                start_date=start_date,
                monthly_rent_amount=room.price_monthly
            )

            # 5. Buat Tagihan Bulan Ini
            today = timezone.now().date()
            billing_start = today.replace(day=start_date.day) 
            
            # Handle tanggal invalid (misal tgl 31 di bulan Feb)
            # (Simple logic: jika error, majukan ke tgl 1 atau 28)
            try:
                billing_start = today.replace(day=start_date.day)
            except ValueError:
                billing_start = today.replace(day=28)

            due_date = billing_start + relativedelta(days=10)

            # Random Status
            status_pilihan = ['BELUM_LUNAS', 'MENUNGGU_VERIFIKASI', 'LUNAS', 'TELAT_BAYAR']
            chosen_status = random.choices(status_pilihan, weights=[30, 10, 50, 10], k=1)[0]
            
            # Jika tanggal tagihan > hari ini (belum mulai), status pasti BELUM_LUNAS
            if billing_start > today:
                chosen_status = 'BELUM_LUNAS'

            Invoice.objects.create(
                contract=contract,
                billing_period_start=billing_start,
                due_date=due_date,
                base_rent_amount=contract.monthly_rent_amount,
                total_amount=contract.monthly_rent_amount,
                status=chosen_status
            )

        self.stdout.write(self.style.SUCCESS(f"SEEDING AKURAT SELESAI! Total {total_rooms} Kamar, {target_tenants} Penghuni."))