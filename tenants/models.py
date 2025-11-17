import uuid
import os
from django.db import models
from core.models import Room

# Fungsi utilitas untuk merename file KTP agar unik (Security NFR-02)
def ktp_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    # Simpan di: media/ktp_private/UUID.jpg
    return os.path.join('ktp_private', filename)

class Tenant(models.Model):
    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=20)
    emergency_contact_phone = models.CharField(max_length=20)
    
    # Upload KTP (Opsional sesuai FR-05)
    ktp_photo = models.ImageField(upload_to=ktp_upload_path, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name

class TenantContract(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='contracts')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='contracts')
    
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True) # Opsional, jika sewa berakhir
    
    monthly_rent_amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    # PIN Pembayaran (FR-02) - Unik per kontrak
    payment_pin = models.CharField(max_length=6, unique=True, help_text="PIN 6 digit unik untuk upload bukti bayar")
    
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Kontrak: {self.tenant.full_name} - {self.room.room_number}"