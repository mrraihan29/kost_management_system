from django.contrib.auth.models import AbstractUser
from django.db import models

from core.models import KostLocation


# 1. Custom User Model (Pengganti User bawaan)
class User(AbstractUser):
    # Kita bisa tambah field global di sini jika perlu,
    # tapi untuk sekarang default AbstractUser sudah cukup
    # (username, password, email, first_name, last_name, is_staff, is_superuser)
    pass

# 2. Admin Profile (Untuk Admin Kost - Relasi OneToOne)
class AdminProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    # Satu admin hanya mengelola satu lokasi (Sesuai Rules FR-01)
    assigned_location = models.ForeignKey(
        KostLocation, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='admins'
    )
    phone_number = models.CharField(max_length=20, blank=True)

    def __str__(self):
        location_name = self.assigned_location.name if self.assigned_location else "No Location"
        return f"Admin: {self.user.username} ({location_name})"