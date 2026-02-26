from django.db import models

# Create your models here.
class KostLocation(models.Model):
    name = models.CharField(max_length=100)
    address = models.TextField()
    description = models.TextField(blank=True, null=True)
    # Tarif Berdasarkan Listrik per lokasi (FR-06)
    electricity_rate_per_kwh = models.DecimalField(max_digits=10, decimal_places=2, default=1500.00)
    
    def __str__(self):
        return self.name

class Room(models.Model):
    kost_location = models.ForeignKey(KostLocation, on_delete=models.CASCADE, related_name='rooms')
    room_number = models.CharField(max_length=20)  # Cth: "A-101"
    price_monthly = models.DecimalField(max_digits=12, decimal_places=2) # Harga dasar kamar
    is_token_electricity = models.BooleanField(default=False) # True=Token, False=Meteran Manual (FR-06)
    capacity = models.IntegerField(default=1)

    class Meta:
        unique_together = ['kost_location', 'room_number']

    def __str__(self):
        return f"{self.kost_location.name} - {self.room_number}"