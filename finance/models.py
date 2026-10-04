from decimal import Decimal
import uuid
import os
from django.db import models
from django.conf import settings
from core.models import KostLocation
from tenants.models import TenantContract

# --- Fungsi Utilitas Upload Path (Security NFR-02) ---

def payment_proof_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    # Simpan di: media/payment_proofs/UUID.jpg
    return os.path.join('payment_proofs', filename)

def operation_cost_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    # Simpan di: media/operation_costs/UUID.jpg
    return os.path.join('operation_costs', filename)

# --- Model Inti Keuangan ---

class Invoice(models.Model):
    # Mengambil Status dari State Diagram (Phase 2)
    STATUS_CHOICES = [
        ('BELUM_LUNAS', 'Belum Lunas'),
        ('MENUNGGU_VERIFIKASI', 'Menunggu Verifikasi'),
        ('LUNAS', 'Lunas'),
        ('TELAT_BAYAR', 'Telat Bayar'),
    ]

    contract = models.ForeignKey(TenantContract, on_delete=models.CASCADE, related_name='invoices')
    billing_period_start = models.DateField(db_index=True)
    due_date = models.DateField(help_text="Tanggal Jatuh Tempo (H-10)", db_index=True)
    
    base_rent_amount = models.DecimalField(max_digits=12, decimal_places=2)
    electricity_bill_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='BELUM_LUNAS', db_index=True)
    
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, editable=False) 
    
    def save(self, *args, **kwargs):
        # Selalu hitung ulang total saat save (A-DATA-01 fix)
        self.total_amount = self.base_rent_amount + self.electricity_bill_amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Tagihan {self.contract.tenant.full_name} ({self.billing_period_start})"

class ElectricityReading(models.Model):
    # Relasi 1-to-1: 1 Tagihan = 1 Catatan Listrik (Sesuai ERD)
    invoice = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name='electricity_reading')
    meter_reading_start = models.IntegerField()
    meter_reading_end = models.IntegerField()
    rate_per_kwh = models.DecimalField(max_digits=10, decimal_places=2)
    calculated_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True)

    def save(self, *args, **kwargs):
        # 1. Hitung pemakaian
        usage = self.meter_reading_end - self.meter_reading_start
        
        # 2. Safety check jika admin salah input (Akhir < Awal)
        if usage < 0:
            usage = 0 
        
        self.calculated_amount = usage * self.rate_per_kwh
        
        # 3. Simpan data diri sendiri dulu
        super().save(*args, **kwargs)
        
        # 4. UPDATE OTOMATIS KE INVOICE INDUK (A-DATA-01 fix: gunakan update langsung)
        self.invoice.electricity_bill_amount = self.calculated_amount
        self.invoice.save()  # Invoice.save() akan otomatis hitung ulang total

    def __str__(self):
        return f"Listrik Tagihan #{self.invoice.id}"

class Payment(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    payment_proof_file = models.ImageField(upload_to=payment_proof_upload_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    # Siapa admin yang memverifikasi? (Sesuai ERD)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_note = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Pembayaran untuk Tagihan #{self.invoice.id}"

class OperationCost(models.Model):
    CATEGORY_CHOICES = [
        ('LISTRIK', 'Listrik'),
        ('PAM', 'PAM (Air)'),
        ('INTERNET', 'Internet'),
        ('MAINTENANCE', 'Maintenance'),
        ('LAINNYA', 'Lainnya'),
    ]

    kost_location = models.ForeignKey(KostLocation, on_delete=models.PROTECT, related_name='costs')
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField()
    proof_file = models.ImageField(upload_to=operation_cost_upload_path)
    incurred_date = models.DateField(help_text="Tanggal pengeluaran terjadi", db_index=True)

    def __str__(self):
        return f"{self.get_category_display()} - {self.kost_location.name} - {self.amount}"